package authority

import (
	"bytes"
	"sort"
)

// requestKey is the complete local idempotency namespace. A request ID never
// stands alone: device identity, credential generation, and operation scope it.
type requestKey struct {
	deviceID         [32]byte
	deviceGeneration uint64
	operation        pendingOperation
	id               RequestID
}

type requestRecord struct {
	key           requestKey
	snapshot      RequestSnapshot
	reservationID uint64
	logicalBytes  uint64
}

// The logical charge covers the composite key, two digests, compact state,
// authority generation, expiry, and the reservation link.
const requestRecordLogicalBytes uint64 = 32 + 8 + 1 + 16 + 32 + 32 + 1 + 8 + 8 + 8

func (m *Manager) beginRequest(key requestKey, requestDigest [32]byte, expiresAt uint64) (*requestRecord, error) {
	if m == nil || !validRequestKey(key) || expiresAt == 0 || !validUnixTime(expiresAt) {
		return nil, ErrInvalidAuthority
	}
	now := m.clock.NowUnix()
	if !validUnixTime(now) || now >= expiresAt {
		return nil, ErrExpired
	}
	m.mu.Lock()
	m.expireRequestsLocked(now)
	m.invalidateRequestGenerationsLocked()
	if existing := m.requests[key]; existing != nil {
		if existing.snapshot.RequestDigest != requestDigest {
			m.mu.Unlock()
			return nil, ErrRequestConflict
		}
		if existing.snapshot.Status == RequestAmbiguous {
			m.mu.Unlock()
			return nil, ErrRequestAmbiguous
		}
		m.mu.Unlock()
		return existing, nil
	}
	if len(m.requests) >= m.limits.MaxRequestRecords || m.requestBytes > m.limits.MaxRequestBytes || requestRecordLogicalBytes > m.limits.MaxRequestBytes-m.requestBytes {
		m.mu.Unlock()
		return nil, ErrCacheCapacity
	}
	record := &requestRecord{
		key: key,
		snapshot: RequestSnapshot{
			ID:                  key.id,
			RequestDigest:       requestDigest,
			Status:              RequestPending,
			AuthorityGeneration: m.generation,
			ExpiresAt:           expiresAt,
		},
		logicalBytes: requestRecordLogicalBytes,
	}
	m.requests[key] = record
	m.requestBytes += record.logicalBytes
	m.mu.Unlock()
	return record, nil
}

func (m *Manager) finishRequest(record *requestRecord, resultDigest [32]byte, reservation Reservation) error {
	if m == nil || record == nil || resultDigest == ([32]byte{}) {
		return ErrInvalidAuthority
	}
	now := m.clock.NowUnix()
	if !validUnixTime(now) {
		return ErrInvalidAuthority
	}
	m.mu.Lock()
	m.expireRequestsLocked(now)
	m.invalidateRequestGenerationsLocked()
	if m.requests[record.key] != record {
		m.mu.Unlock()
		return ErrInvalidAuthority
	}
	if record.snapshot.Status != RequestPending {
		m.mu.Unlock()
		return ErrInvalidTransition
	}
	if reservation != (Reservation{}) {
		entry := m.reserved[reservation.id]
		if reservation.id == 0 || entry == nil || entry.reservation != reservation.id || entry.state != cacheReserved || entry.authority.Key() != reservation.key || entry.authority.GrantDigest() != reservation.grant || resultDigest != reservation.grant {
			m.mu.Unlock()
			return ErrInvalidAuthority
		}
		record.reservationID = reservation.id
	}
	record.snapshot.ResultDigest = resultDigest
	record.snapshot.Status = RequestComplete
	m.mu.Unlock()
	return nil
}

// markAmbiguous denies reuse and retires a linked reservation in the same
// critical section, so a timeout cannot expose the resulting grant.
func (m *Manager) markAmbiguous(record *requestRecord) error {
	if m == nil || record == nil {
		return ErrInvalidAuthority
	}
	now := m.clock.NowUnix()
	if !validUnixTime(now) {
		return ErrInvalidAuthority
	}
	m.mu.Lock()
	m.expireRequestsLocked(now)
	m.invalidateRequestGenerationsLocked()
	if m.requests[record.key] != record {
		m.mu.Unlock()
		return ErrInvalidAuthority
	}
	if record.snapshot.Status == RequestAmbiguous {
		m.mu.Unlock()
		return ErrRequestAmbiguous
	}
	var events []Event
	if record.reservationID != 0 {
		entry := m.reserved[record.reservationID]
		if entry == nil || entry.state != cacheReserved || entry.authority.GrantDigest() != record.snapshot.ResultDigest {
			m.mu.Unlock()
			return ErrInvalidAuthority
		}
		grant := entry.authority.GrantDigest()
		m.retireEntryLocked(entry, cacheQuarantined)
		events = append(events, Event{Kind: EventAmbiguousQuarantine, AuthorityGeneration: record.snapshot.AuthorityGeneration, Grant: grant, Request: record.snapshot.ID, Result: CodeRequestAmbiguous})
	}
	record.snapshot.Status = RequestAmbiguous
	m.mu.Unlock()
	m.notify(events)
	return nil
}

func (m *Manager) expireRequests(now uint64) {
	if m == nil || !validUnixTime(now) {
		return
	}
	m.mu.Lock()
	m.expireRequestsLocked(now)
	m.mu.Unlock()
}

// RequestRecordSnapshot is diagnostics-only: it exposes fixed-width digests
// and state, never a canonical request or provider response.
func (m *Manager) RequestRecordSnapshot(id RequestID) (RequestSnapshot, error) {
	if m == nil || id == (RequestID{}) {
		return RequestSnapshot{}, ErrInvalidAuthority
	}
	now := m.clock.NowUnix()
	if !validUnixTime(now) {
		return RequestSnapshot{}, ErrInvalidAuthority
	}
	m.mu.Lock()
	m.expireRequestsLocked(now)
	var found *requestRecord
	stale := false
	for key, record := range m.requests {
		if key.id != id {
			continue
		}
		if record.snapshot.AuthorityGeneration != m.generation {
			m.removeRequestLocked(record)
			stale = true
			continue
		}
		if found != nil {
			m.mu.Unlock()
			return RequestSnapshot{}, ErrRequestConflict
		}
		found = record
	}
	if found == nil {
		m.mu.Unlock()
		if stale {
			return RequestSnapshot{}, ErrStaleGeneration
		}
		return RequestSnapshot{}, ErrInvalidAuthority
	}
	snapshot := found.snapshot
	m.mu.Unlock()
	return snapshot, nil
}

func (m *Manager) expiredRequestKeys(now uint64) []requestKey {
	if m == nil || !validUnixTime(now) {
		return nil
	}
	m.mu.RLock()
	keys := m.expiredRequestKeysLocked(now)
	m.mu.RUnlock()
	return keys
}

func (m *Manager) expireRequestsLocked(now uint64) {
	for _, key := range m.expiredRequestKeysLocked(now) {
		m.removeRequestLocked(m.requests[key])
	}
}

func (m *Manager) expiredRequestKeysLocked(now uint64) []requestKey {
	keys := make([]requestKey, 0)
	for key, record := range m.requests {
		if record != nil && now >= record.snapshot.ExpiresAt {
			keys = append(keys, key)
		}
	}
	sort.Slice(keys, func(left, right int) bool { return requestKeyBefore(keys[left], keys[right]) })
	return keys
}

func (m *Manager) invalidateRequestGenerationsLocked() {
	for _, record := range m.requests {
		if record.snapshot.AuthorityGeneration != m.generation {
			m.removeRequestLocked(record)
		}
	}
}

func (m *Manager) removeRequestLocked(record *requestRecord) {
	if record == nil || m.requests[record.key] != record {
		return
	}
	delete(m.requests, record.key)
	m.requestBytes -= record.logicalBytes
}

func validRequestKey(key requestKey) bool {
	return key.deviceID != ([32]byte{}) && key.deviceGeneration != 0 && key.id != (RequestID{}) && (key.operation == pendingAcquire || key.operation == pendingRenew)
}

func requestKeyBefore(left, right requestKey) bool {
	if compare := bytes.Compare(left.deviceID[:], right.deviceID[:]); compare != 0 {
		return compare < 0
	}
	if left.deviceGeneration != right.deviceGeneration {
		return left.deviceGeneration < right.deviceGeneration
	}
	if left.operation != right.operation {
		return left.operation < right.operation
	}
	return bytes.Compare(left.id[:], right.id[:]) < 0
}
