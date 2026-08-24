package authority

import (
	"bytes"
	"math"
)

type cacheLifecycle uint8

const (
	cacheAvailable cacheLifecycle = iota + 1
	cacheReserved
	cacheConsumed
	cacheQuarantined
	cacheInvalid
)

type cacheEntry struct {
	authority    VerifiedAuthority
	state        cacheLifecycle
	reservation  uint64
	logicalBytes uint64
}

// A tombstone retains only the replay-relevant digest, terminal reason, and
// end-exclusive authority expiry. It is charged to the same cache limits as a
// live entry and may be evicted only after that expiry.
type tombstone struct {
	grant        RouteGrantDigest
	expiresAt    uint64
	state        cacheLifecycle
	logicalBytes uint64
}

const tombstoneLogicalBytes uint64 = 40 // grant digest plus end-exclusive expiry.

// authorityLogicalBytes is a representation-independent bound: all fixed-size
// key and sealed-authority fields plus variable binding strings and the exact
// verified RouteGrant bytes required by ROUTE_OPEN. It does not depend on Go's
// allocator or map implementation.
func authorityLogicalBytes(authority VerifiedAuthority) (uint64, error) {
	key := authority.Key()
	variable := uint64(len(key.SourceOperator))
	for _, value := range []string{key.SourceEdge, key.TargetOperator, key.Profile, key.Transport} {
		if uint64(len(value)) > math.MaxUint64-variable {
			return 0, ErrAccountingOverflow
		}
		variable += uint64(len(value))
	}
	if uint64(len(authority.seal.serviceIdentity)) > math.MaxUint64-variable {
		return 0, ErrAccountingOverflow
	}
	variable += uint64(len(authority.seal.serviceIdentity))
	if uint64(len(authority.seal.exactRouteGrant)) > math.MaxUint64-variable {
		return 0, ErrAccountingOverflow
	}
	variable += uint64(len(authority.seal.exactRouteGrant))
	const fixed = uint64(346) // 9 digests, five uint64s, and one uint16.
	if variable > math.MaxUint64-fixed {
		return 0, ErrAccountingOverflow
	}
	return fixed + variable, nil
}

// reserveVerified is the only cache insertion path. It accepts the sealed
// verifier result, performs no provider work, and reserves its entry before
// exposing the reservation to the caller.
func (m *Manager) reserveVerified(authority VerifiedAuthority) (Reservation, error) {
	if m == nil || !authority.valid() {
		return Reservation{}, ErrInvalidAuthority
	}
	now := m.clock.NowUnix()
	if !validUnixTime(now) || now >= authority.ExpiresAt() {
		return Reservation{}, ErrExpired
	}
	m.mu.Lock()
	reservation, events, err := m.reserveVerifiedLocked(authority, now)
	m.mu.Unlock()
	m.notify(events)
	return reservation, err
}

func (m *Manager) reserveVerifiedLocked(authority VerifiedAuthority, now uint64) (Reservation, []Event, error) {
	key, grant := authority.Key(), authority.GrantDigest()
	if _, found := m.tombstones[grant]; found {
		return Reservation{}, nil, ErrInvalidAuthority
	}
	if entry, found := m.grants[grant]; found {
		if entry.authority.Key() != key {
			return Reservation{}, nil, ErrInvalidAuthority
		}
		return m.reserveExistingLocked(entry)
	}
	if _, found := m.cache[key]; found {
		return Reservation{}, nil, ErrInvalidAuthority
	}
	// A fresh cache entry is useful only when it can be reserved immediately.
	// Check this before selecting evictions or changing logical accounting.
	if m.nextReservation == math.MaxUint64 {
		return Reservation{}, nil, ErrAccountingOverflow
	}
	logicalBytes, err := authorityLogicalBytes(authority)
	if err != nil {
		return Reservation{}, nil, err
	}
	if _, overflow := addUint64(m.cacheBytes, logicalBytes); overflow {
		return Reservation{}, nil, ErrAccountingOverflow
	}
	evictions, err := m.planEvictionsLocked(logicalBytes, now)
	if err != nil {
		return Reservation{}, []Event{{Kind: EventCacheFull, Grant: grant, Result: errorCode(err)}}, err
	}
	for _, eviction := range evictions {
		if eviction.entry != nil {
			m.removeAvailableLocked(eviction.entry)
		} else {
			m.removeTombstoneLocked(eviction.tombstone)
		}
	}
	entry := &cacheEntry{authority: authority, state: cacheAvailable, logicalBytes: logicalBytes}
	m.cache[key] = entry
	m.grants[grant] = entry
	m.cacheBytes += logicalBytes
	return m.reserveExistingLocked(entry)
}

func (m *Manager) reserveExistingLocked(entry *cacheEntry) (Reservation, []Event, error) {
	if entry.state != cacheAvailable {
		if entry.state == cacheReserved {
			return Reservation{}, []Event{{Kind: EventCacheHit, Grant: entry.authority.GrantDigest(), Result: CodeInvalidTransition}}, ErrInvalidTransition
		}
		return Reservation{}, []Event{{Kind: EventCacheHit, Grant: entry.authority.GrantDigest(), Result: CodeInvalidAuthority}}, ErrInvalidAuthority
	}
	if m.nextReservation == math.MaxUint64 {
		return Reservation{}, nil, ErrAccountingOverflow
	}
	m.nextReservation++
	entry.state = cacheReserved
	entry.reservation = m.nextReservation
	m.reserved[entry.reservation] = entry
	return Reservation{id: entry.reservation, key: entry.authority.Key(), grant: entry.authority.GrantDigest()}, []Event{{Kind: EventCacheHit, Grant: entry.authority.GrantDigest()}}, nil
}

// validateAvailableLocked is the pre-reservation barrier for cache hits and
// renewal predecessors.  It retires an authority as soon as it cannot be used
// under the current local checkpoint, rather than allowing a stale
// reservation to escape for a later final check.
func (m *Manager) validateAvailableLocked(entry *cacheEntry, now uint64) ([]Event, error) {
	if entry == nil || entry.state != cacheAvailable {
		return nil, ErrInvalidTransition
	}
	if !entry.authority.valid() {
		m.retireEntryLocked(entry, cacheInvalid)
		return []Event{invalidationEvent(entry)}, ErrInvalidAuthority
	}
	if entry.authority.AuthorityGeneration() != m.generation || entry.authority.Key().AuthorityGeneration != m.generation || entry.authority.Checkpoint() != m.checkpoint.Digest() {
		m.retireEntryLocked(entry, cacheInvalid)
		return []Event{invalidationEvent(entry)}, ErrStaleGeneration
	}
	if now >= entry.authority.ExpiresAt() {
		m.retireEntryLocked(entry, cacheInvalid)
		return []Event{invalidationEvent(entry)}, ErrExpired
	}
	if m.checkpoint.hasRevoked(entry.authority.GrantDigest()) {
		m.retireEntryLocked(entry, cacheInvalid)
		return []Event{invalidationEvent(entry)}, ErrRevoked
	}
	return nil, nil
}

// replaceRenewedLocked atomically turns an eligible, still-unconsumed
// predecessor into a replay tombstone and reserves the distinct replacement.
// A renewal never makes the predecessor available again.
func (m *Manager) replaceRenewedLocked(previous RouteGrantDigest, authority VerifiedAuthority, now uint64) (Reservation, []Event, error) {
	if previous == (RouteGrantDigest{}) || !authority.valid() || now >= authority.ExpiresAt() || authority.GrantDigest() == previous {
		return Reservation{}, nil, ErrInvalidAuthority
	}
	predecessor := m.grants[previous]
	if predecessor == nil {
		if _, terminal := m.tombstones[previous]; terminal {
			return Reservation{}, nil, ErrInvalidTransition
		}
		return Reservation{}, nil, ErrInvalidAuthority
	}
	if predecessor.authority.Key() != authority.Key() {
		return Reservation{}, nil, ErrBindingMismatch
	}
	events, err := m.validateAvailableLocked(predecessor, now)
	if err != nil {
		return Reservation{}, events, err
	}
	if _, terminal := m.tombstones[authority.GrantDigest()]; terminal {
		return Reservation{}, events, ErrInvalidAuthority
	}
	if _, existing := m.grants[authority.GrantDigest()]; existing {
		return Reservation{}, events, ErrInvalidAuthority
	}
	if m.cache[authority.Key()] != predecessor {
		return Reservation{}, events, ErrInvalidAuthority
	}
	if m.nextReservation == math.MaxUint64 {
		return Reservation{}, events, ErrAccountingOverflow
	}
	logicalBytes, err := authorityLogicalBytes(authority)
	if err != nil {
		return Reservation{}, events, err
	}
	evictions, err := m.planRenewalEvictionsLocked(predecessor, logicalBytes, now)
	if err != nil {
		return Reservation{}, append(events, Event{Kind: EventCacheFull, Grant: authority.GrantDigest(), Result: errorCode(err)}), err
	}
	for _, eviction := range evictions {
		if eviction.entry != nil {
			m.removeAvailableLocked(eviction.entry)
		} else {
			m.removeTombstoneLocked(eviction.tombstone)
		}
	}
	m.retireEntryLocked(predecessor, cacheConsumed)
	replacement := &cacheEntry{authority: authority, state: cacheAvailable, logicalBytes: logicalBytes}
	m.cache[authority.Key()] = replacement
	m.grants[authority.GrantDigest()] = replacement
	m.cacheBytes += logicalBytes
	reservation, reserveEvents, err := m.reserveExistingLocked(replacement)
	return reservation, append(events, reserveEvents...), err
}

func (m *Manager) planRenewalEvictionsLocked(predecessor *cacheEntry, incomingBytes, now uint64) ([]evictionCandidate, error) {
	if predecessor == nil || m.cacheBytes < predecessor.logicalBytes {
		return nil, ErrInvalidAuthority
	}
	bytesAfter := m.cacheBytes - predecessor.logicalBytes
	var overflow bool
	bytesAfter, overflow = addUint64(bytesAfter, tombstoneLogicalBytes)
	if overflow {
		return nil, ErrAccountingOverflow
	}
	bytesAfter, overflow = addUint64(bytesAfter, incomingBytes)
	if overflow {
		return nil, ErrAccountingOverflow
	}
	entriesAfter := m.cacheEntriesLocked() + 1 // predecessor becomes a tombstone, plus replacement.
	candidates := make([]evictionCandidate, 0, m.cacheEntriesLocked())
	for _, entry := range m.cache {
		if entry != predecessor && entry.state == cacheAvailable {
			candidates = append(candidates, evictionCandidate{entry: entry})
		}
	}
	for _, terminal := range m.tombstones {
		if now >= terminal.expiresAt {
			terminal := terminal
			candidates = append(candidates, evictionCandidate{tombstone: &terminal})
		}
	}
	selected := make([]evictionCandidate, 0)
	for len(candidates) > 0 && (entriesAfter > m.limits.MaxCacheEntries || bytesAfter > m.limits.MaxCacheBytes) {
		best := 0
		for index := 1; index < len(candidates); index++ {
			if evictionBefore(candidates[index], candidates[best]) {
				best = index
			}
		}
		candidate := candidates[best]
		candidates = append(candidates[:best], candidates[best+1:]...)
		if candidate.logicalBytes() > bytesAfter {
			return nil, ErrAccountingOverflow
		}
		bytesAfter -= candidate.logicalBytes()
		entriesAfter--
		selected = append(selected, candidate)
	}
	if entriesAfter > m.limits.MaxCacheEntries || bytesAfter > m.limits.MaxCacheBytes {
		return nil, ErrCacheCapacity
	}
	return selected, nil
}

type evictionCandidate struct {
	entry     *cacheEntry
	tombstone *tombstone
}

func (m *Manager) planEvictionsLocked(incomingBytes, now uint64) ([]evictionCandidate, error) {
	bytesAfter, overflow := addUint64(m.cacheBytes, incomingBytes)
	if overflow {
		return nil, ErrAccountingOverflow
	}
	entriesAfter := m.cacheEntriesLocked() + 1
	if entriesAfter <= m.limits.MaxCacheEntries && bytesAfter <= m.limits.MaxCacheBytes {
		return nil, nil
	}
	candidates := make([]evictionCandidate, 0, m.cacheEntriesLocked())
	for _, entry := range m.cache {
		if entry.state == cacheAvailable {
			candidates = append(candidates, evictionCandidate{entry: entry})
		}
	}
	for _, terminal := range m.tombstones {
		if now >= terminal.expiresAt {
			terminal := terminal
			candidates = append(candidates, evictionCandidate{tombstone: &terminal})
		}
	}
	selected := make([]evictionCandidate, 0)
	for len(candidates) > 0 && (entriesAfter > m.limits.MaxCacheEntries || bytesAfter > m.limits.MaxCacheBytes) {
		best := 0
		for index := 1; index < len(candidates); index++ {
			if evictionBefore(candidates[index], candidates[best]) {
				best = index
			}
		}
		candidate := candidates[best]
		candidates = append(candidates[:best], candidates[best+1:]...)
		if candidate.logicalBytes() > bytesAfter {
			return nil, ErrAccountingOverflow
		}
		bytesAfter -= candidate.logicalBytes()
		entriesAfter--
		selected = append(selected, candidate)
	}
	if entriesAfter > m.limits.MaxCacheEntries || bytesAfter > m.limits.MaxCacheBytes {
		return nil, ErrCacheCapacity
	}
	return selected, nil
}

func evictsBefore(left, right *cacheEntry) bool {
	if left.authority.ExpiresAt() != right.authority.ExpiresAt() {
		return left.authority.ExpiresAt() < right.authority.ExpiresAt()
	}
	leftGrant, rightGrant := left.authority.GrantDigest(), right.authority.GrantDigest()
	return bytes.Compare(leftGrant[:], rightGrant[:]) < 0
}

func (candidate evictionCandidate) logicalBytes() uint64 {
	if candidate.entry != nil {
		return candidate.entry.logicalBytes
	}
	return candidate.tombstone.logicalBytes
}

func (candidate evictionCandidate) expiresAt() uint64 {
	if candidate.entry != nil {
		return candidate.entry.authority.ExpiresAt()
	}
	return candidate.tombstone.expiresAt
}

func (candidate evictionCandidate) grant() RouteGrantDigest {
	if candidate.entry != nil {
		return candidate.entry.authority.GrantDigest()
	}
	return candidate.tombstone.grant
}

func evictionBefore(left, right evictionCandidate) bool {
	if left.expiresAt() != right.expiresAt() {
		return left.expiresAt() < right.expiresAt()
	}
	leftGrant, rightGrant := left.grant(), right.grant()
	return bytes.Compare(leftGrant[:], rightGrant[:]) < 0
}

func (m *Manager) removeAvailableLocked(entry *cacheEntry) {
	delete(m.cache, entry.authority.Key())
	delete(m.grants, entry.authority.GrantDigest())
	m.cacheBytes -= entry.logicalBytes
}

func (m *Manager) removeTombstoneLocked(terminal *tombstone) {
	delete(m.tombstones, terminal.grant)
	m.cacheBytes -= terminal.logicalBytes
}

func (m *Manager) cacheEntriesLocked() int { return len(m.cache) + len(m.tombstones) }

func (m *Manager) ValidateForNewWork(reservation Reservation, snapshot GenerationSnapshot, now uint64) error {
	if m == nil || !validUnixTime(now) {
		return ErrInvalidAuthority
	}
	m.mu.Lock()
	events, err := m.validateReservedLocked(reservation, snapshot, now)
	m.mu.Unlock()
	m.notify(events)
	return err
}

func (m *Manager) Consume(reservation Reservation, owner AdmissionOwner, snapshot GenerationSnapshot, now uint64) (AuthorityHandle, error) {
	if m == nil || !validUnixTime(now) {
		return AuthorityHandle{}, ErrInvalidAuthority
	}
	m.mu.Lock()
	events, err := m.validateReservedLocked(reservation, snapshot, now)
	if err == nil {
		entry := m.reserved[reservation.id]
		if owner.TSGeneration != reservation.key.TSGeneration {
			err = ErrBindingMismatch
		} else if owner.ChannelID == ([16]byte{}) {
			err = ErrInvalidAuthority
		} else {
			handle := AuthorityHandle{key: entry.authority.Key(), grant: entry.authority.GrantDigest(), generation: entry.authority.AuthorityGeneration(), expiresAt: entry.authority.ExpiresAt(), checkpoint: entry.authority.Checkpoint()}
			m.retireEntryLocked(entry, cacheConsumed)
			m.mu.Unlock()
			m.notify(events)
			return handle, nil
		}
	}
	m.mu.Unlock()
	m.notify(events)
	return AuthorityHandle{}, err
}

func (m *Manager) validateReservedLocked(reservation Reservation, snapshot GenerationSnapshot, now uint64) ([]Event, error) {
	entry, found := m.reserved[reservation.id]
	if !found {
		if terminal, found := m.tombstones[reservation.grant]; found {
			return nil, terminalReservationError(terminal)
		}
		return nil, ErrInvalidAuthority
	}
	if reservation.id == 0 || entry.reservation != reservation.id || entry.authority.Key() != reservation.key || entry.authority.GrantDigest() != reservation.grant || entry.state != cacheReserved {
		return nil, ErrInvalidAuthority
	}
	events, err := m.requireFreshLocked(now)
	if err != nil {
		return events, err
	}
	if snapshot.generation == 0 || snapshot.generation != m.generation || entry.authority.AuthorityGeneration() != m.generation || reservation.key.AuthorityGeneration != m.generation || entry.authority.Checkpoint() != m.checkpoint.Digest() {
		m.retireEntryLocked(entry, cacheInvalid)
		return append(events, invalidationEvent(entry)), ErrStaleGeneration
	}
	if !entry.authority.valid() {
		m.retireEntryLocked(entry, cacheInvalid)
		return append(events, invalidationEvent(entry)), ErrInvalidAuthority
	}
	if now >= entry.authority.ExpiresAt() {
		m.retireEntryLocked(entry, cacheInvalid)
		return append(events, invalidationEvent(entry)), ErrExpired
	}
	if m.checkpoint.hasRevoked(entry.authority.GrantDigest()) {
		m.retireEntryLocked(entry, cacheInvalid)
		return append(events, invalidationEvent(entry)), ErrRevoked
	}
	return events, nil
}

func (m *Manager) Release(reservation Reservation) error {
	if m == nil {
		return ErrInvalidAuthority
	}
	m.mu.Lock()
	entry, found := m.reserved[reservation.id]
	if !found {
		_, terminal := m.tombstones[reservation.grant]
		cached := m.cache[reservation.key]
		released := cached != nil && cached.authority.GrantDigest() == reservation.grant
		m.mu.Unlock()
		if terminal || released {
			return ErrInvalidTransition
		}
		return ErrInvalidAuthority
	}
	if reservation.id == 0 || entry.reservation != reservation.id || entry.authority.Key() != reservation.key || entry.authority.GrantDigest() != reservation.grant || entry.state != cacheReserved {
		m.mu.Unlock()
		return ErrInvalidAuthority
	}
	entry.state = cacheAvailable
	m.terminalizeReservationRecordsLocked(entry.reservation, entry.authority.GrantDigest())
	entry.reservation = 0
	delete(m.reserved, reservation.id)
	m.mu.Unlock()
	return nil
}

func (m *Manager) Quarantine(reservation Reservation, request RequestID) error {
	if m == nil || request == (RequestID{}) {
		return ErrInvalidAuthority
	}
	m.mu.Lock()
	entry, found := m.reserved[reservation.id]
	if !found {
		_, terminal := m.tombstones[reservation.grant]
		cached := m.cache[reservation.key]
		released := cached != nil && cached.authority.GrantDigest() == reservation.grant
		m.mu.Unlock()
		if terminal || released {
			return ErrInvalidTransition
		}
		return ErrInvalidAuthority
	}
	if reservation.id == 0 || entry.reservation != reservation.id || entry.authority.Key() != reservation.key || entry.authority.GrantDigest() != reservation.grant || entry.state != cacheReserved {
		m.mu.Unlock()
		return ErrInvalidAuthority
	}
	m.retireEntryLocked(entry, cacheQuarantined)
	m.mu.Unlock()
	m.notify([]Event{{Kind: EventAmbiguousQuarantine, Grant: reservation.grant, Request: request, Result: CodeRequestAmbiguous}})
	return nil
}

func (m *Manager) InvalidateGrant(grant RouteGrantDigest) error {
	if m == nil || grant == (RouteGrantDigest{}) {
		return ErrInvalidAuthority
	}
	m.mu.Lock()
	entry := m.grants[grant]
	var events []Event
	if entry != nil {
		m.retireEntryLocked(entry, cacheInvalid)
		events = []Event{invalidationEvent(entry)}
	}
	m.mu.Unlock()
	m.notify(events)
	return nil
}

func (m *Manager) InvalidateOlderThan(generation AuthorityGeneration) (int, error) {
	if m == nil || generation == 0 {
		return 0, ErrInvalidAuthority
	}
	m.mu.Lock()
	count := 0
	events := make([]Event, 0)
	for _, entry := range m.cache {
		if entry.authority.AuthorityGeneration() < generation {
			m.retireEntryLocked(entry, cacheInvalid)
			count++
			events = append(events, invalidationEvent(entry))
		}
	}
	m.mu.Unlock()
	m.notify(events)
	return count, nil
}

func (m *Manager) retireEntryLocked(entry *cacheEntry, state cacheLifecycle) {
	if entry.reservation != 0 {
		m.terminalizeReservationRecordsLocked(entry.reservation, entry.authority.GrantDigest())
		delete(m.reserved, entry.reservation)
	}
	delete(m.cache, entry.authority.Key())
	delete(m.grants, entry.authority.GrantDigest())
	m.cacheBytes -= entry.logicalBytes
	m.tombstones[entry.authority.GrantDigest()] = tombstone{grant: entry.authority.GrantDigest(), expiresAt: entry.authority.ExpiresAt(), state: state, logicalBytes: tombstoneLogicalBytes}
	m.cacheBytes += tombstoneLogicalBytes
}

func terminalReservationError(terminal tombstone) error {
	if terminal.state == cacheInvalid {
		return ErrInvalidAuthority
	}
	return ErrInvalidTransition
}

func invalidationEvent(entry *cacheEntry) Event {
	return Event{Kind: EventAuthorityInvalidated, AuthorityGeneration: entry.authority.AuthorityGeneration(), Grant: entry.authority.GrantDigest(), Result: CodeInvalidAuthority}
}

func (m *Manager) Usage() Usage {
	if m == nil {
		return Usage{}
	}
	m.mu.RLock()
	usage := Usage{CacheEntries: m.cacheEntriesLocked(), CacheBytes: m.cacheBytes, PendingCalls: len(m.pending), PendingBytes: m.pendingBytes, RequestRecords: len(m.requests), RequestBytes: m.requestBytes}
	for _, call := range m.pending {
		usage.PendingWaiters += call.waiters
	}
	m.mu.RUnlock()
	return usage
}

func (m *Manager) ValidateInvariants() error {
	if m == nil {
		return ErrInvalidAuthority
	}
	m.mu.RLock()
	defer m.mu.RUnlock()
	if m.cacheEntriesLocked() > m.limits.MaxCacheEntries || m.cacheBytes > m.limits.MaxCacheBytes || len(m.reserved) > len(m.cache) || len(m.grants) != len(m.cache) || len(m.pending) > m.limits.MaxPending || m.pendingBytes > m.limits.MaxPendingBytes || len(m.requests) > m.limits.MaxRequestRecords || m.requestBytes > m.limits.MaxRequestBytes {
		return ErrInvalidAuthority
	}
	var bytesUsed uint64
	for key, entry := range m.cache {
		if entry == nil || entry.authority.Key() != key || !entry.authority.valid() || m.grants[entry.authority.GrantDigest()] != entry {
			return ErrInvalidAuthority
		}
		logical, err := authorityLogicalBytes(entry.authority)
		if err != nil || logical != entry.logicalBytes {
			return ErrInvalidAuthority
		}
		var overflow bool
		bytesUsed, overflow = addUint64(bytesUsed, logical)
		if overflow {
			return ErrInvalidAuthority
		}
		switch entry.state {
		case cacheAvailable:
			if entry.reservation != 0 {
				return ErrInvalidAuthority
			}
		case cacheReserved:
			if entry.reservation == 0 || m.reserved[entry.reservation] != entry {
				return ErrInvalidAuthority
			}
		default:
			return ErrInvalidAuthority
		}
	}
	for grant, terminal := range m.tombstones {
		if grant == (RouteGrantDigest{}) || terminal.grant != grant || terminal.expiresAt == 0 || terminal.logicalBytes != tombstoneLogicalBytes || (terminal.state != cacheConsumed && terminal.state != cacheQuarantined && terminal.state != cacheInvalid) || m.grants[grant] != nil {
			return ErrInvalidAuthority
		}
		var overflow bool
		bytesUsed, overflow = addUint64(bytesUsed, terminal.logicalBytes)
		if overflow {
			return ErrInvalidAuthority
		}
	}
	if bytesUsed != m.cacheBytes {
		return ErrInvalidAuthority
	}
	for id, entry := range m.reserved {
		if id == 0 || entry == nil || entry.state != cacheReserved || entry.reservation != id || m.cache[entry.authority.Key()] != entry {
			return ErrInvalidAuthority
		}
	}
	var pendingBytes uint64
	for key, call := range m.pending {
		if call == nil || call.key != key || call.finished || call.waiters < 1 || call.waiters > m.limits.MaxWaitersPerPending || call.done == nil || call.providerContext == nil || call.cancel == nil {
			return ErrInvalidAuthority
		}
		logical, err := pendingLogicalBytes(key, call.acquire)
		if err != nil || logical != call.logicalBytes {
			return ErrInvalidAuthority
		}
		if key.operation == pendingRenew {
			if call.renew.PreviousGrant != key.previous || call.renew.AcquireRequest.Key != key.authority {
				return ErrInvalidAuthority
			}
		} else if key.operation != pendingAcquire {
			return ErrInvalidAuthority
		}
		var overflow bool
		pendingBytes, overflow = addUint64(pendingBytes, logical)
		if overflow {
			return ErrInvalidAuthority
		}
	}
	if pendingBytes != m.pendingBytes {
		return ErrInvalidAuthority
	}
	var requestBytes uint64
	for key, record := range m.requests {
		if record == nil || record.key != key || !validRequestKey(key) || record.logicalBytes != requestRecordLogicalBytes || record.snapshot.ID != key.id || record.snapshot.AuthorityGeneration == 0 || record.snapshot.ExpiresAt == 0 || record.snapshot.Status < RequestPending || record.snapshot.Status > RequestAmbiguous {
			return ErrInvalidAuthority
		}
		if record.snapshot.Status == RequestPending && (record.snapshot.ResultDigest != ([32]byte{}) || record.reservationID != 0 || record.link != requestLinkNone) {
			return ErrInvalidAuthority
		}
		if record.snapshot.Status == RequestComplete && (record.snapshot.ResultDigest == ([32]byte{}) || record.link < requestLinkReserved || record.link > requestLinkTerminal) {
			return ErrInvalidAuthority
		}
		if record.snapshot.Status == RequestComplete && record.link == requestLinkReserved {
			if record.reservationID == 0 {
				return ErrInvalidAuthority
			}
			entry := m.reserved[record.reservationID]
			if entry == nil || entry.state != cacheReserved || entry.authority.GrantDigest() != record.snapshot.ResultDigest {
				return ErrInvalidAuthority
			}
		}
		if (record.snapshot.Status == RequestComplete && record.link == requestLinkTerminal) || record.snapshot.Status == RequestAmbiguous {
			if record.reservationID != 0 || record.link != requestLinkTerminal {
				return ErrInvalidAuthority
			}
		}
		var overflow bool
		requestBytes, overflow = addUint64(requestBytes, record.logicalBytes)
		if overflow {
			return ErrInvalidAuthority
		}
	}
	if requestBytes != m.requestBytes {
		return ErrInvalidAuthority
	}
	return nil
}

func addUint64(left, right uint64) (uint64, bool) {
	if right > math.MaxUint64-left {
		return 0, true
	}
	return left + right, false
}
