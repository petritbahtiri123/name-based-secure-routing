package authority

import (
	"errors"
	"math"
	"reflect"
	"testing"
)

func TestConsumedGrantNeverReturnsAvailable(t *testing.T) {
	m, r, snapshot := reservedGrant(t)
	if _, err := m.Consume(r, AdmissionOwner{TSGeneration: r.key.TSGeneration, ChannelID: id16(1)}, snapshot, 99); err != nil {
		t.Fatal(err)
	}
	if err := m.Release(r); !errors.Is(err, ErrInvalidTransition) {
		t.Fatalf("Release = %v, want ErrInvalidTransition", err)
	}
	if _, err := m.reserveVerified(testAuthority(r.key, r.grant, 200)); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("reserve consumed grant = %v, want ErrInvalidAuthority", err)
	}
}

func TestCacheLogicalByteCapsAreExact(t *testing.T) {
	key := testKey(1)
	authority := testAuthority(key, testGrant(1), 200)
	logical := testLogicalBytes(key)
	for _, tt := range []struct {
		name    string
		limit   uint64
		wantErr error
	}{
		{"below", logical - 1, ErrCacheCapacity},
		{"exact", logical, nil},
		{"above", logical + 1, nil},
	} {
		t.Run(tt.name, func(t *testing.T) {
			m := testManager(t, 99, 1, tt.limit)
			_, err := m.reserveVerified(authority)
			if !errors.Is(err, tt.wantErr) {
				t.Fatalf("reserve error = %v, want %v", err, tt.wantErr)
			}
			usage := m.Usage()
			if tt.wantErr != nil {
				if usage.CacheEntries != 0 || usage.CacheBytes != 0 {
					t.Fatalf("failed insertion changed usage: %+v", usage)
				}
				return
			}
			if usage.CacheEntries != 1 || usage.CacheBytes != logical {
				t.Fatalf("usage = %+v, want one entry and %d bytes", usage, logical)
			}
		})
	}
}

func TestCacheEntryCapsAreExact(t *testing.T) {
	m := testManager(t, 99, 2, 1<<20)
	first, err := m.reserveVerified(testAuthority(testKey(1), testGrant(1), 200))
	if err != nil {
		t.Fatal(err)
	}
	if err := m.Release(first); err != nil {
		t.Fatal(err)
	}
	if got := m.Usage().CacheEntries; got != 1 {
		t.Fatalf("below cap entries = %d, want 1", got)
	}
	if _, err := m.reserveVerified(testAuthority(testKey(2), testGrant(2), 200)); err != nil {
		t.Fatalf("exact cap insertion = %v", err)
	}
	if got := m.Usage().CacheEntries; got != 2 {
		t.Fatalf("exact cap entries = %d, want 2", got)
	}
	if _, err := m.reserveVerified(testAuthority(testKey(1), testGrant(1), 200)); err != nil {
		t.Fatalf("reserve available entry = %v", err)
	}
	before := m.Usage()
	if _, err := m.reserveVerified(testAuthority(testKey(3), testGrant(3), 200)); !errors.Is(err, ErrCacheCapacity) {
		t.Fatalf("above cap insertion = %v, want ErrCacheCapacity", err)
	}
	if got := m.Usage(); got != before {
		t.Fatalf("above-cap failure changed usage: got %+v, want %+v", got, before)
	}
}

func TestCacheFailedInsertionIsAtomicAndDetectsAccountingOverflow(t *testing.T) {
	key := testKey(1)
	first := testAuthority(key, testGrant(1), 200)
	logical := testLogicalBytes(key)
	m := testManager(t, 99, 1, logical*2)
	if _, err := m.reserveVerified(first); err != nil {
		t.Fatal(err)
	}
	before := m.Usage()
	if _, err := m.reserveVerified(testAuthority(testKey(2), testGrant(2), 200)); !errors.Is(err, ErrCacheCapacity) {
		t.Fatalf("second reserved insertion = %v, want ErrCacheCapacity", err)
	}
	if got := m.Usage(); got != before {
		t.Fatalf("failed insertion changed usage: got %+v, want %+v", got, before)
	}

	m.mu.Lock()
	m.cacheBytes = math.MaxUint64
	m.mu.Unlock()
	if _, err := m.reserveVerified(testAuthority(testKey(3), testGrant(3), 200)); !errors.Is(err, ErrAccountingOverflow) {
		t.Fatalf("overflow insertion = %v, want ErrAccountingOverflow", err)
	}
}

func TestCacheReservationIDOverflowIsAtomic(t *testing.T) {
	m := testManager(t, 99, 1, 1<<20)
	m.mu.Lock()
	m.nextReservation = math.MaxUint64
	m.mu.Unlock()
	before := m.Usage()
	if _, err := m.reserveVerified(testAuthority(testKey(1), testGrant(1), 200)); !errors.Is(err, ErrAccountingOverflow) {
		t.Fatalf("reservation ID overflow = %v, want ErrAccountingOverflow", err)
	}
	if got := m.Usage(); got != before {
		t.Fatalf("reservation ID overflow changed usage: got %+v, want %+v", got, before)
	}
	if err := m.ValidateInvariants(); err != nil {
		t.Fatalf("reservation ID overflow corrupted cache: %v", err)
	}
}

func TestAuthorityKeyUsesEveryDimension(t *testing.T) {
	base := testKey(1)
	mutations := []struct {
		name string
		mut  func(*AuthorityKey)
	}{
		{"canonical intent digest", func(key *AuthorityKey) { key.IntentDigest[0]++ }},
		{"service", func(key *AuthorityKey) { key.ServiceDigest[0]++ }},
		{"source operator", func(key *AuthorityKey) { key.SourceOperator = "other-source" }},
		{"source edge", func(key *AuthorityKey) { key.SourceEdge = "other-source-edge" }},
		{"target operator", func(key *AuthorityKey) { key.TargetOperator = "other-target" }},
		{"target edge set", func(key *AuthorityKey) { key.TargetEdgeSetDigest[0]++ }},
		{"profile", func(key *AuthorityKey) { key.Profile = "other-profile" }},
		{"transport", func(key *AuthorityKey) { key.Transport = "tcp" }},
		{"port", func(key *AuthorityKey) { key.Port++ }},
		{"device", func(key *AuthorityKey) { key.DeviceID[0]++ }},
		{"device generation", func(key *AuthorityKey) { key.DeviceGeneration++ }},
		{"workload", func(key *AuthorityKey) { key.WorkloadDigest = nonZero32(20); key.WorkloadGeneration = 2 }},
		{"workload generation", func(key *AuthorityKey) { key.WorkloadDigest = nonZero32(21); key.WorkloadGeneration = 2 }},
		{"TS generation", func(key *AuthorityKey) { key.TSGeneration++ }},
		{"proof thumbprint", func(key *AuthorityKey) { key.ProofThumbprint[0]++ }},
		{"policy", func(key *AuthorityKey) { key.PolicyHash[0]++ }},
		{"policy generation", func(key *AuthorityKey) { key.PolicyGeneration++ }},
		{"authority generation", func(key *AuthorityKey) { key.AuthorityGeneration++ }},
	}
	m := testManager(t, 99, len(mutations)+1, 1<<20)
	if _, err := m.reserveVerified(testAuthority(base, testGrant(1), 200)); err != nil {
		t.Fatal(err)
	}
	for index, tt := range mutations {
		t.Run(tt.name, func(t *testing.T) {
			key := base
			tt.mut(&key)
			if _, err := m.reserveVerified(testAuthority(key, testGrant(byte(index+2)), 200)); err != nil {
				t.Fatalf("distinct key rejected: %v", err)
			}
		})
	}
	if got := m.Usage().CacheEntries; got != len(mutations)+1 {
		t.Fatalf("cache entries = %d, want %d", got, len(mutations)+1)
	}
}

func TestCacheEvictsOnlyAvailableEntriesInDeterministicOrder(t *testing.T) {
	m := testManager(t, 99, 2, 1<<20)
	firstKey, secondKey, thirdKey := testKey(1), testKey(2), testKey(3)
	first := testAuthority(firstKey, testGrant(2), 150)
	second := testAuthority(secondKey, testGrant(1), 150)
	for _, authority := range []VerifiedAuthority{first, second} {
		reservation, err := m.reserveVerified(authority)
		if err != nil {
			t.Fatal(err)
		}
		if err := m.Release(reservation); err != nil {
			t.Fatal(err)
		}
	}
	if _, err := m.reserveVerified(testAuthority(thirdKey, testGrant(3), 200)); err != nil {
		t.Fatal(err)
	}
	m.mu.RLock()
	_, firstPresent := m.cache[firstKey]
	_, secondPresent := m.cache[secondKey]
	_, thirdPresent := m.cache[thirdKey]
	m.mu.RUnlock()
	if !firstPresent || secondPresent || !thirdPresent {
		t.Fatalf("eviction = first:%v second:%v third:%v, want true/false/true", firstPresent, secondPresent, thirdPresent)
	}
}

func TestCacheNeverEvictsReservedAuthority(t *testing.T) {
	m := testManager(t, 99, 1, 1<<20)
	if _, err := m.reserveVerified(testAuthority(testKey(1), testGrant(1), 200)); err != nil {
		t.Fatal(err)
	}
	if _, err := m.reserveVerified(testAuthority(testKey(2), testGrant(2), 200)); !errors.Is(err, ErrCacheCapacity) {
		t.Fatalf("reserved entry was evicted: %v", err)
	}
}

func TestQuarantinedGrantNeverReturnsAvailable(t *testing.T) {
	m, reservation, _ := reservedGrant(t)
	if err := m.Quarantine(reservation, RequestID{9}); err != nil {
		t.Fatal(err)
	}
	if err := m.Quarantine(reservation, RequestID{9}); !errors.Is(err, ErrInvalidTransition) {
		t.Fatalf("double quarantine = %v, want ErrInvalidTransition", err)
	}
	if err := m.Release(reservation); !errors.Is(err, ErrInvalidTransition) {
		t.Fatalf("release quarantined reservation = %v, want ErrInvalidTransition", err)
	}
	if _, err := m.reserveVerified(testAuthority(reservation.key, reservation.grant, 200)); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("reserve quarantined grant = %v, want ErrInvalidAuthority", err)
	}
}

func TestConsumeChecksOwnerAndTerminalTransitions(t *testing.T) {
	m, reservation, snapshot := reservedGrant(t)
	wrongTS := AdmissionOwner{TSGeneration: reservation.key.TSGeneration + 1, ChannelID: id16(1)}
	if _, err := m.Consume(reservation, wrongTS, snapshot, 99); !errors.Is(err, ErrBindingMismatch) {
		t.Fatalf("wrong TS = %v, want ErrBindingMismatch", err)
	}
	if _, err := m.Consume(reservation, AdmissionOwner{TSGeneration: reservation.key.TSGeneration}, snapshot, 99); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("zero channel = %v, want ErrInvalidAuthority", err)
	}
	if _, err := m.Consume(reservation, AdmissionOwner{TSGeneration: reservation.key.TSGeneration, ChannelID: id16(1)}, snapshot, 99); err != nil {
		t.Fatal(err)
	}
	if _, err := m.Consume(reservation, AdmissionOwner{TSGeneration: reservation.key.TSGeneration, ChannelID: id16(1)}, snapshot, 99); !errors.Is(err, ErrInvalidTransition) {
		t.Fatalf("double consume = %v, want ErrInvalidTransition", err)
	}
	if err := m.Quarantine(reservation, RequestID{1}); !errors.Is(err, ErrInvalidTransition) {
		t.Fatalf("quarantine consumed = %v, want ErrInvalidTransition", err)
	}
}

func TestReleaseRejectsDoubleReleaseAndForeignReservation(t *testing.T) {
	m, reservation, _ := reservedGrant(t)
	foreign := reservation
	foreign.key.ServiceDigest[0]++
	if err := m.Release(foreign); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("foreign reservation release = %v, want ErrInvalidAuthority", err)
	}
	if err := m.Release(reservation); err != nil {
		t.Fatal(err)
	}
	if err := m.Release(reservation); !errors.Is(err, ErrInvalidTransition) {
		t.Fatalf("double release = %v, want ErrInvalidTransition", err)
	}
}

func TestFinalCheckRejectsExpiryRevocationAndGeneration(t *testing.T) {
	t.Run("expiry is end exclusive", func(t *testing.T) {
		m, reservation, snapshot := reservedGrant(t)
		if err := m.ValidateForNewWork(reservation, snapshot, 200); !errors.Is(err, ErrExpired) {
			t.Fatalf("validation at expiry = %v, want ErrExpired", err)
		}
	})
	t.Run("checkpoint revocation", func(t *testing.T) {
		m, reservation, snapshot := reservedGrant(t)
		m.mu.Lock()
		m.checkpoint.revoked = []RouteGrantDigest{reservation.grant}
		m.mu.Unlock()
		if _, err := m.Consume(reservation, AdmissionOwner{TSGeneration: reservation.key.TSGeneration, ChannelID: id16(1)}, snapshot, 99); !errors.Is(err, ErrRevoked) {
			t.Fatalf("revoked consume = %v, want ErrRevoked", err)
		}
	})
	t.Run("generation", func(t *testing.T) {
		m, reservation, snapshot := reservedGrant(t)
		m.mu.Lock()
		m.generation++
		m.checkpoint.claims.Generation++
		m.mu.Unlock()
		if err := m.ValidateForNewWork(reservation, snapshot, 99); !errors.Is(err, ErrStaleGeneration) {
			t.Fatalf("generation advance = %v, want ErrStaleGeneration", err)
		}
	})
	t.Run("freshness", func(t *testing.T) {
		m, reservation, snapshot := reservedGrant(t)
		if err := m.ValidateForNewWork(reservation, snapshot, 300); !errors.Is(err, ErrStaleFreshness) {
			t.Fatalf("validation at freshness boundary = %v, want ErrStaleFreshness", err)
		}
	})
	t.Run("credential policy integrity", func(t *testing.T) {
		m, reservation, snapshot := reservedGrant(t)
		m.mu.Lock()
		m.cache[reservation.key].authority.seal.key.PolicyGeneration = 0
		m.mu.Unlock()
		if err := m.ValidateForNewWork(reservation, snapshot, 99); !errors.Is(err, ErrInvalidAuthority) {
			t.Fatalf("corrupt policy binding = %v, want ErrInvalidAuthority", err)
		}
	})
}

func TestGrantInvalidationAndOlderGenerationAreTerminal(t *testing.T) {
	m, reservation, snapshot := reservedGrant(t)
	if err := m.InvalidateGrant(reservation.grant); err != nil {
		t.Fatal(err)
	}
	if err := m.ValidateForNewWork(reservation, snapshot, 99); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("invalidated grant validated: %v", err)
	}
	if _, err := m.reserveVerified(testAuthority(reservation.key, reservation.grant, 200)); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("invalidated grant reused: %v", err)
	}

	m, reservation, _ = reservedGrant(t)
	count, err := m.InvalidateOlderThan(reservation.key.AuthorityGeneration + 1)
	if err != nil || count != 1 {
		t.Fatalf("InvalidateOlderThan = %d, %v; want 1, nil", count, err)
	}
	if err := m.Release(reservation); !errors.Is(err, ErrInvalidTransition) {
		t.Fatalf("release old generation = %v, want ErrInvalidTransition", err)
	}
}

func TestAuthorityHandleIsImmutableValue(t *testing.T) {
	m, reservation, snapshot := reservedGrant(t)
	handle, err := m.Consume(reservation, AdmissionOwner{TSGeneration: reservation.key.TSGeneration, ChannelID: id16(1)}, snapshot, 99)
	if err != nil {
		t.Fatal(err)
	}
	for index := 0; index < reflect.TypeOf(handle).NumField(); index++ {
		field := reflect.TypeOf(handle).Field(index)
		if field.IsExported() {
			t.Fatalf("AuthorityHandle exposes mutable field %q", field.Name)
		}
	}
	copy := handle
	copy.key.SourceOperator = "mutated"
	if handle.key.SourceOperator == copy.key.SourceOperator {
		t.Fatal("handle copy aliases mutable authority state")
	}
}

func TestCacheInvariantValidationDetectsCorruption(t *testing.T) {
	m, _, _ := reservedGrant(t)
	if err := m.ValidateInvariants(); err != nil {
		t.Fatalf("healthy cache invariants = %v", err)
	}
	m.mu.Lock()
	m.cacheBytes++
	m.mu.Unlock()
	if err := m.ValidateInvariants(); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("corrupt accounting = %v, want ErrInvalidAuthority", err)
	}
}

func reservedGrant(t *testing.T) (*Manager, Reservation, GenerationSnapshot) {
	t.Helper()
	m := testManager(t, 99, 2, 1<<20)
	key := testKey(1)
	reservation, err := m.reserveVerified(testAuthority(key, testGrant(1), 200))
	if err != nil {
		t.Fatal(err)
	}
	return m, reservation, GenerationSnapshot{generation: key.AuthorityGeneration}
}

func testManager(t *testing.T, now uint64, entries int, bytes uint64) *Manager {
	t.Helper()
	limits := validLimits()
	limits.MaxCacheEntries = entries
	limits.MaxCacheBytes = bytes
	m, err := NewManager(limits, fakeClock{}, fakeProvider{}, &Verifier{}, fakeCheckpointVerifier{}, fakeFloorStore{}, noopObserver{})
	if err != nil {
		t.Fatal(err)
	}
	m.mu.Lock()
	m.checkpoint = checkpointState{claims: CheckpointClaims{SourceOperator: "source-operator", Profile: "profile", Generation: 7, FreshUntil: 300, Digest: nonZeroCheckpoint()}}
	m.generation = 7
	m.hasCheckpoint = true
	m.mu.Unlock()
	_ = now
	return m
}

func testKey(seed byte) AuthorityKey {
	key := validAcquireRequest().Key
	key.IntentDigest[0] = seed
	key.ServiceDigest[0] = seed
	key.TargetEdgeSetDigest[0] = seed
	key.DeviceID[0] = seed
	key.ProofThumbprint[0] = seed
	key.PolicyHash[0] = seed
	key.AuthorityGeneration = 7
	return key
}

func testAuthority(key AuthorityKey, grant RouteGrantDigest, expiresAt uint64) VerifiedAuthority {
	return sealAuthority(key, grant, expiresAt, nonZeroCheckpoint(), key.AuthorityGeneration)
}

func testGrant(seed byte) RouteGrantDigest { return RouteGrantDigest(nonZero32(seed)) }
func id16(value byte) [16]byte             { return [16]byte{value} }

// This must stay independent of cache.go so a changed accounting formula is
// caught at its observable capacity boundary.
func testLogicalBytes(key AuthorityKey) uint64 {
	return 346 + uint64(len(key.SourceOperator)+len(key.SourceEdge)+len(key.TargetOperator)+len(key.Profile)+len(key.Transport))
}
