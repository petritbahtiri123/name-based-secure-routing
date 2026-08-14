package authority

import (
	"bytes"
	"errors"
	"math"
	"testing"
)

func TestRequestRecordRejectsConflictingRequestIDReuse(t *testing.T) {
	m := idempotencyManager(t)
	id := requestID(1)
	mustBeginRequest(t, m, id, digest(1), 10)
	if _, err := m.beginRequestForTest(id, digest(2), 10); !errors.Is(err, ErrRequestConflict) {
		t.Fatalf("conflicting request ID reuse = %v, want ErrRequestConflict", err)
	}
}

func TestRequestRecordRequiresNonZero128BitID(t *testing.T) {
	m := idempotencyManager(t)
	if _, err := m.beginRequestForTest(RequestID{}, digest(1), 10); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("zero request ID = %v, want ErrInvalidAuthority", err)
	}
	if got := requestID(1); len(got) != 16 {
		t.Fatalf("request ID length = %d, want 16", len(got))
	}
}

func TestRequestRecordExactDuplicateJoinsSamePendingIdentity(t *testing.T) {
	m := idempotencyManager(t)
	id := requestID(1)
	first := mustBeginRequest(t, m, id, digest(1), 10)
	joined := mustBeginRequest(t, m, id, digest(1), 10)
	if first != joined {
		t.Fatal("exact duplicate did not join the same pending request identity")
	}
}

func TestRequestRecordOperationDiscriminatorPreventsCrossOperationJoin(t *testing.T) {
	m := idempotencyManager(t)
	id := requestID(1)
	key := requestKeyForTest(id, pendingAcquire)
	if _, err := m.beginRequest(key, digest(1), 10); err != nil {
		t.Fatalf("begin acquire: %v", err)
	}
	key.operation = pendingRenew
	if _, err := m.beginRequest(key, digest(2), 10); err != nil {
		t.Fatalf("begin renew: %v", err)
	}
	if got := m.Usage(); got.RequestRecords != 2 {
		t.Fatalf("request records = %d, want 2", got.RequestRecords)
	}
}

func TestRequestRecordRetentionCapsAreExact(t *testing.T) {
	for _, tt := range []struct {
		name    string
		entries int
		bytes   uint64
		count   int
		wantErr error
	}{
		{"below entries", 2, math.MaxUint64, 1, nil},
		{"exact entries", 2, math.MaxUint64, 2, nil},
		{"above entries", 2, math.MaxUint64, 3, ErrCacheCapacity},
		{"below bytes", 2, requestRecordLogicalBytes - 1, 1, ErrCacheCapacity},
		{"exact bytes", 2, requestRecordLogicalBytes, 1, nil},
		{"above bytes", 2, requestRecordLogicalBytes * 2, 2, nil},
	} {
		t.Run(tt.name, func(t *testing.T) {
			m := idempotencyManagerWithLimits(t, tt.entries, tt.bytes)
			for index := 0; index < tt.count; index++ {
				_, err := m.beginRequestForTest(requestID(byte(index+1)), digest(byte(index+1)), 10)
				if index == tt.count-1 && tt.wantErr != nil {
					if !errors.Is(err, tt.wantErr) {
						t.Fatalf("request %d = %v, want %v", index, err, tt.wantErr)
					}
					return
				}
				if err != nil {
					t.Fatalf("request %d: %v", index, err)
				}
			}
			if got := m.Usage().RequestRecords; got != tt.count {
				t.Fatalf("request records = %d, want %d", got, tt.count)
			}
		})
	}
}

func TestRequestRecordExpiryIsDeterministicAndNeverReusesResult(t *testing.T) {
	clock := &mutableClock{now: 1}
	m := idempotencyManagerWithClock(t, clock, 3, requestRecordLogicalBytes*3)
	first := mustBeginRequest(t, m, requestID(1), digest(1), 2)
	if err := m.finishRequest(first, digest(9), Reservation{}); err != nil {
		t.Fatalf("finish request: %v", err)
	}
	clock.set(2)
	m.expireRequests(clock.NowUnix())
	second := mustBeginRequest(t, m, requestID(1), digest(1), 3)
	if second == first {
		t.Fatal("expired completed result was reused")
	}
	if second.snapshot.ResultDigest != ([32]byte{}) || second.snapshot.Status != RequestPending {
		t.Fatal("new request reused expired response state")
	}
}

func TestRequestRecordSameExpiryOrderingIsByCompositeKey(t *testing.T) {
	clock := &mutableClock{now: 1}
	m := idempotencyManagerWithClock(t, clock, 3, requestRecordLogicalBytes*3)
	for _, id := range []RequestID{requestID(3), requestID(1), requestID(2)} {
		mustBeginRequest(t, m, id, digest(id[0]), 2)
	}
	clock.set(2)
	if got := m.expiredRequestKeys(clock.NowUnix()); len(got) != 3 || got[0].id != requestID(1) || got[1].id != requestID(2) || got[2].id != requestID(3) {
		t.Fatalf("expired ordering = %#v, want request IDs 1, 2, 3", got)
	}
}

func TestRequestRecordCompletedSnapshotCopiesOnlyDigestState(t *testing.T) {
	m := idempotencyManager(t)
	id := requestID(1)
	record := mustBeginRequest(t, m, id, digest(1), 10)
	result := digest(2)
	if err := m.finishRequest(record, result, Reservation{}); err != nil {
		t.Fatalf("finish request: %v", err)
	}
	snapshot, err := m.RequestRecordSnapshot(id)
	if err != nil {
		t.Fatalf("RequestRecordSnapshot: %v", err)
	}
	if snapshot.ResultDigest != result || snapshot.Status != RequestComplete || snapshot.ID != id {
		t.Fatalf("snapshot = %#v, want completed digest-only state", snapshot)
	}
	if len(bytes.Join([][]byte{snapshot.RequestDigest[:], snapshot.ResultDigest[:]}, nil)) != 64 {
		t.Fatal("snapshot digest widths changed")
	}
}

func TestAmbiguousRequestQuarantinesLinkedReservationAtomically(t *testing.T) {
	m, reservation, _ := reservedGrant(t)
	m.mu.Lock()
	m.limits.MaxRequestRecords = 1
	m.limits.MaxRequestBytes = requestRecordLogicalBytes
	m.mu.Unlock()
	record := mustBeginRequest(t, m, requestID(1), digest(1), 10)
	if err := m.finishRequest(record, reservation.grant, reservation); err != nil {
		t.Fatalf("finish request: %v", err)
	}
	if err := m.markAmbiguous(record); err != nil {
		t.Fatalf("mark ambiguous: %v", err)
	}
	if err := m.ValidateForNewWork(reservation, GenerationSnapshot{generation: 7}, 1); !errors.Is(err, ErrInvalidTransition) {
		t.Fatalf("quarantined reservation validation = %v, want ErrInvalidTransition", err)
	}
	if _, err := m.beginRequestForTest(requestID(1), digest(1), 10); !errors.Is(err, ErrRequestAmbiguous) {
		t.Fatalf("ambiguous duplicate = %v, want ErrRequestAmbiguous", err)
	}
}

func TestRequestRecordGenerationInvalidation(t *testing.T) {
	m := idempotencyManager(t)
	record := mustBeginRequest(t, m, requestID(1), digest(1), 10)
	m.mu.Lock()
	m.generation++
	m.mu.Unlock()
	if _, err := m.RequestRecordSnapshot(record.snapshot.ID); !errors.Is(err, ErrStaleGeneration) {
		t.Fatalf("old generation snapshot = %v, want ErrStaleGeneration", err)
	}
	if got := m.Usage().RequestRecords; got != 0 {
		t.Fatalf("request records after generation invalidation = %d, want 0", got)
	}
}

func TestRequestRecordHistoryRemainsBoundedAcross4096ExpiryCycles(t *testing.T) {
	clock := &mutableClock{now: 1}
	m := idempotencyManagerWithClock(t, clock, 1, requestRecordLogicalBytes)
	for cycle := 1; cycle <= 4096; cycle++ {
		clock.set(uint64(cycle * 2))
		m.expireRequests(clock.NowUnix())
		if _, err := m.beginRequestForTest(requestID(1), digest(byte(cycle)), clock.NowUnix()+1); err != nil {
			t.Fatalf("cycle %d: %v", cycle, err)
		}
		if got := m.Usage(); got.RequestRecords != 1 || m.requestBytes != requestRecordLogicalBytes {
			t.Fatalf("cycle %d usage = %#v request bytes = %d, want one bounded record", cycle, got, m.requestBytes)
		}
	}
}

func idempotencyManager(t *testing.T) *Manager {
	t.Helper()
	return idempotencyManagerWithClock(t, &mutableClock{now: 1}, 4, requestRecordLogicalBytes*4)
}

func idempotencyManagerWithLimits(t *testing.T, entries int, bytes uint64) *Manager {
	t.Helper()
	return idempotencyManagerWithClock(t, &mutableClock{now: 1}, entries, bytes)
}

func idempotencyManagerWithClock(t *testing.T, clock Clock, entries int, bytes uint64) *Manager {
	t.Helper()
	m := testManagerWithClock(t, clock, 4, 1<<20)
	m.mu.Lock()
	m.limits.MaxRequestRecords = entries
	m.limits.MaxRequestBytes = bytes
	m.mu.Unlock()
	return m
}

func mustBeginRequest(t *testing.T, m *Manager, id RequestID, requestDigest [32]byte, expiresAt uint64) *requestRecord {
	t.Helper()
	record, err := m.beginRequestForTest(id, requestDigest, expiresAt)
	if err != nil {
		t.Fatalf("begin request: %v", err)
	}
	return record
}

func (m *Manager) beginRequestForTest(id RequestID, requestDigest [32]byte, expiresAt uint64) (*requestRecord, error) {
	return m.beginRequest(requestKeyForTest(id, pendingAcquire), requestDigest, expiresAt)
}

func requestKeyForTest(id RequestID, operation pendingOperation) requestKey {
	return requestKey{deviceID: nonZero32(1), deviceGeneration: 1, operation: operation, id: id}
}

func requestID(value byte) RequestID { return RequestID{value} }
func digest(value byte) [32]byte     { return [32]byte{value} }
