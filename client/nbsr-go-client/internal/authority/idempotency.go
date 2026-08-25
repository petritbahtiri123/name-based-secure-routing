package authority

import (
	"bytes"
	"crypto/sha256"
	"encoding/binary"
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
	link          requestResultLink
	logicalBytes  uint64
}

// requestResultLink is private state that distinguishes a still-reserved
// result from a terminal result. A completed request never points at a
// reservation after that reservation has been consumed, released,
// quarantined, or invalidated.
type requestResultLink uint8

const (
	requestLinkNone requestResultLink = iota
	requestLinkReserved
	requestLinkTerminal
)

// The logical charge covers the composite key, two digests, compact state,
// authority generation, expiry, and the reservation link.
const requestRecordLogicalBytes uint64 = 32 + 8 + 1 + 16 + 32 + 32 + 1 + 1 + 8 + 8 + 8

// canonicalRequestDigest is local-only binding for retry/idempotency state. It
// is domain-separated and length-prefixes variable values so no two distinct
// immutable authorization inputs can share an encoding by concatenation.
func canonicalRequestDigest(key pendingKey, request AcquireRequest, renew RenewRequest) [32]byte {
	hash := sha256.New()
	_, _ = hash.Write([]byte("NBSR-GO-CLIENT-IDEMPOTENCY-v1\x00"))
	writeBytes := func(value []byte) {
		var length [8]byte
		binary.BigEndian.PutUint64(length[:], uint64(len(value)))
		_, _ = hash.Write(length[:])
		_, _ = hash.Write(value)
	}
	writeText := func(value string) { writeBytes([]byte(value)) }
	writeUint := func(value uint64) {
		var encoded [8]byte
		binary.BigEndian.PutUint64(encoded[:], value)
		_, _ = hash.Write(encoded[:])
	}
	writeUint16 := func(value uint16) {
		var encoded [2]byte
		binary.BigEndian.PutUint16(encoded[:], value)
		_, _ = hash.Write(encoded[:])
	}
	writeByte := func(value byte) { _, _ = hash.Write([]byte{value}) }
	writeKey := func(value AuthorityKey) {
		writeBytes(value.IntentDigest[:])
		writeBytes(value.ServiceDigest[:])
		writeText(value.SourceOperator)
		writeText(value.SourceEdge)
		writeText(value.TargetOperator)
		writeBytes(value.TargetEdgeSetDigest[:])
		writeText(value.Profile)
		writeText(value.Transport)
		writeUint16(value.Port)
		writeBytes(value.DeviceID[:])
		writeUint(value.DeviceGeneration)
		writeBytes(value.WorkloadDigest[:])
		writeUint(value.WorkloadGeneration)
		writeUint(uint64(value.TSGeneration))
		writeBytes(value.ProofThumbprint[:])
		writeBytes(value.PolicyHash[:])
		writeUint(value.PolicyGeneration)
		writeUint(uint64(value.AuthorityGeneration))
	}
	writeByte(byte(key.operation))
	writeBytes(key.previous[:])
	writeKey(key.authority)
	intent := request.Intent
	writeBytes(intent.Canonical)
	writeBytes(intent.Digest[:])
	writeText(intent.ServiceIdentity)
	writeText(intent.SourceOperator)
	writeText(intent.SourceEdge)
	writeText(intent.TargetOperator)
	writeUint(uint64(len(intent.TargetEdges)))
	for _, edge := range intent.TargetEdges {
		writeText(edge)
	}
	writeText(intent.Transport)
	writeUint16(intent.Port)
	writeUint(intent.RecordSequence)
	writeBytes(intent.PolicyHash[:])
	writeBytes(intent.RouteID[:])
	writeBytes(intent.LeaseID[:])
	writeUint(intent.ExpiresAt)
	device := request.Device
	writeBytes(device.ID[:])
	writeText(device.SourceOperatorID)
	writeUint(device.CredentialGeneration)
	writeUint(device.CredentialNotBefore)
	writeUint(device.CredentialExpiresAt)
	writeBytes(device.SigningKey.ID[:])
	writeByte(byte(device.SigningKey.Purpose))
	writeUint(device.SigningKey.Generation)
	writeBytes(device.SigningKey.Thumbprint[:])
	if request.Workload == nil {
		writeByte(0)
	} else {
		writeByte(1)
		writeBytes(request.Workload.SubjectDigest[:])
		writeUint(request.Workload.PolicyGeneration)
		writeUint(request.Workload.CredentialExpiresAt)
		writeUint(request.Workload.PolicyExpiresAt)
	}
	writeUint(request.DeadlineUnix)
	var digest [32]byte
	copy(digest[:], hash.Sum(nil))
	return digest
}

func (m *Manager) beginRequest(key requestKey, requestDigest [32]byte, expiresAt uint64) (*requestRecord, error) {
	if m == nil || !validRequestKey(key) || expiresAt == 0 || !validUnixTime(expiresAt) {
		return nil, ErrInvalidAuthority
	}
	now := m.clock.NowUnix()
	if !validUnixTime(now) || now >= expiresAt {
		return nil, ErrExpired
	}
	m.mu.Lock()
	record, _, err := m.beginRequestLocked(key, requestDigest, expiresAt, now)
	m.mu.Unlock()
	return record, err
}

func (m *Manager) beginRequestLocked(key requestKey, requestDigest [32]byte, expiresAt, now uint64) (*requestRecord, bool, error) {
	m.expireRequestsLocked(now)
	m.invalidateRequestGenerationsLocked()
	if existing := m.requests[key]; existing != nil {
		if existing.snapshot.RequestDigest != requestDigest {
			return nil, false, ErrRequestConflict
		}
		if existing.snapshot.Status == RequestAmbiguous {
			return nil, false, ErrRequestAmbiguous
		}
		return existing, false, nil
	}
	for otherKey, other := range m.requests {
		if otherKey.deviceID == key.deviceID && otherKey.deviceGeneration == key.deviceGeneration && otherKey.id == key.id && (otherKey.operation != key.operation || other.snapshot.RequestDigest != requestDigest) {
			return nil, false, ErrRequestConflict
		}
	}
	if len(m.requests) >= m.limits.MaxRequestRecords || m.requestBytes > m.limits.MaxRequestBytes || requestRecordLogicalBytes > m.limits.MaxRequestBytes-m.requestBytes {
		return nil, false, ErrCacheCapacity
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
	return record, true, nil
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
	if err := m.finishRequestLocked(record, resultDigest, reservation); err != nil {
		m.mu.Unlock()
		return err
	}
	m.mu.Unlock()
	return nil
}

func (m *Manager) finishRequestLocked(record *requestRecord, resultDigest [32]byte, reservation Reservation) error {
	if record == nil || m.requests[record.key] != record || record.snapshot.Status != RequestPending || resultDigest == ([32]byte{}) {
		return ErrInvalidAuthority
	}
	if reservation != (Reservation{}) {
		entry := m.reserved[reservation.id]
		if reservation.id == 0 || entry == nil || entry.reservation != reservation.id || entry.state != cacheReserved || entry.authority.Key() != reservation.key || entry.authority.GrantDigest() != reservation.grant || resultDigest != reservation.grant {
			return ErrInvalidAuthority
		}
		record.reservationID = reservation.id
		record.link = requestLinkReserved
	} else {
		record.link = requestLinkTerminal
	}
	record.snapshot.ResultDigest = resultDigest
	record.snapshot.Status = RequestComplete
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
	events, err := m.markAmbiguousLocked(record)
	m.mu.Unlock()
	m.notify(events)
	return err
}

func (m *Manager) markAmbiguousLocked(record *requestRecord) ([]Event, error) {
	if record == nil || m.requests[record.key] != record {
		return nil, ErrInvalidAuthority
	}
	if record.snapshot.Status == RequestAmbiguous {
		return nil, ErrRequestAmbiguous
	}
	var events []Event
	if record.reservationID != 0 {
		entry := m.reserved[record.reservationID]
		if entry == nil || entry.state != cacheReserved || entry.authority.GrantDigest() != record.snapshot.ResultDigest {
			return nil, ErrInvalidAuthority
		}
		m.retireEntryLocked(entry, cacheQuarantined)
		events = append(events, Event{Kind: EventAmbiguousQuarantine, Result: CodeRequestAmbiguous})
	}
	record.reservationID = 0
	record.link = requestLinkTerminal
	record.snapshot.Status = RequestAmbiguous
	return events, nil
}

func (m *Manager) completedReservationLocked(record *requestRecord) (Reservation, error) {
	if record == nil || m.requests[record.key] != record || record.snapshot.Status != RequestComplete {
		return Reservation{}, ErrInvalidAuthority
	}
	if record.link == requestLinkTerminal {
		return Reservation{}, ErrInvalidTransition
	}
	if record.link != requestLinkReserved || record.reservationID == 0 {
		return Reservation{}, ErrInvalidAuthority
	}
	entry := m.reserved[record.reservationID]
	if entry == nil || entry.state != cacheReserved || entry.authority.GrantDigest() != record.snapshot.ResultDigest {
		record.reservationID = 0
		record.link = requestLinkTerminal
		return Reservation{}, ErrInvalidTransition
	}
	return Reservation{id: entry.reservation, key: entry.authority.Key(), grant: entry.authority.GrantDigest()}, nil
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

// terminalizeReservationRecordsLocked preserves bounded duplicate-request
// replay protection while severing every completed record from an authority
// reservation that is no longer live. Callers hold m.mu.
func (m *Manager) terminalizeReservationRecordsLocked(reservationID uint64, grant RouteGrantDigest) {
	if reservationID == 0 || grant == (RouteGrantDigest{}) {
		return
	}
	for _, record := range m.requests {
		if record.snapshot.Status == RequestComplete && record.link == requestLinkReserved && record.reservationID == reservationID && record.snapshot.ResultDigest == grant {
			record.reservationID = 0
			record.link = requestLinkTerminal
		}
	}
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
