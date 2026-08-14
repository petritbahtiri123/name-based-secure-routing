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

// authorityLogicalBytes is a representation-independent bound: all fixed-size
// key and sealed-authority fields plus the five variable key strings. It does
// not depend on Go's allocator or map implementation.
func authorityLogicalBytes(authority VerifiedAuthority) (uint64, error) {
	key := authority.Key()
	variable := uint64(len(key.SourceOperator))
	for _, value := range []string{key.SourceEdge, key.TargetOperator, key.Profile, key.Transport} {
		if uint64(len(value)) > math.MaxUint64-variable {
			return 0, ErrAccountingOverflow
		}
		variable += uint64(len(value))
	}
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
	m.mu.Lock()
	reservation, events, err := m.reserveVerifiedLocked(authority)
	m.mu.Unlock()
	m.notify(events)
	return reservation, err
}

func (m *Manager) reserveVerifiedLocked(authority VerifiedAuthority) (Reservation, []Event, error) {
	key, grant := authority.Key(), authority.GrantDigest()
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
	evictions, err := m.planEvictionsLocked(logicalBytes)
	if err != nil {
		return Reservation{}, []Event{{Kind: EventCacheFull, Grant: grant, Result: errorCode(err)}}, err
	}
	for _, entry := range evictions {
		m.removeAvailableLocked(entry)
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

func (m *Manager) planEvictionsLocked(incomingBytes uint64) ([]*cacheEntry, error) {
	bytesAfter, overflow := addUint64(m.cacheBytes, incomingBytes)
	if overflow {
		return nil, ErrAccountingOverflow
	}
	entriesAfter := len(m.cache) + 1
	if entriesAfter <= m.limits.MaxCacheEntries && bytesAfter <= m.limits.MaxCacheBytes {
		return nil, nil
	}
	candidates := make([]*cacheEntry, 0, len(m.cache))
	for _, entry := range m.cache {
		if entry.state == cacheAvailable {
			candidates = append(candidates, entry)
		}
	}
	for len(candidates) > 0 && (entriesAfter > m.limits.MaxCacheEntries || bytesAfter > m.limits.MaxCacheBytes) {
		best := 0
		for index := 1; index < len(candidates); index++ {
			if evictsBefore(candidates[index], candidates[best]) {
				best = index
			}
		}
		entry := candidates[best]
		candidates = append(candidates[:best], candidates[best+1:]...)
		if entry.logicalBytes > bytesAfter {
			return nil, ErrAccountingOverflow
		}
		bytesAfter -= entry.logicalBytes
		entriesAfter--
	}
	if entriesAfter > m.limits.MaxCacheEntries || bytesAfter > m.limits.MaxCacheBytes {
		return nil, ErrCacheCapacity
	}
	// Recompute the deterministic prefix instead of retaining a separate plan
	// while selecting candidates above; no mutation has happened yet.
	neededEntries := len(m.cache) + 1
	neededBytes, _ := addUint64(m.cacheBytes, incomingBytes)
	selected := make([]*cacheEntry, 0)
	all := make([]*cacheEntry, 0, len(m.cache))
	for _, entry := range m.cache {
		if entry.state == cacheAvailable {
			all = append(all, entry)
		}
	}
	for neededEntries > m.limits.MaxCacheEntries || neededBytes > m.limits.MaxCacheBytes {
		best := 0
		for index := 1; index < len(all); index++ {
			if evictsBefore(all[index], all[best]) {
				best = index
			}
		}
		entry := all[best]
		all = append(all[:best], all[best+1:]...)
		selected = append(selected, entry)
		neededEntries--
		neededBytes -= entry.logicalBytes
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

func (m *Manager) removeAvailableLocked(entry *cacheEntry) {
	delete(m.cache, entry.authority.Key())
	delete(m.grants, entry.authority.GrantDigest())
	m.cacheBytes -= entry.logicalBytes
}

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
			entry.state = cacheConsumed
			entry.reservation = 0
			delete(m.reserved, reservation.id)
			handle := AuthorityHandle{key: entry.authority.Key(), grant: entry.authority.GrantDigest(), generation: entry.authority.AuthorityGeneration(), expiresAt: entry.authority.ExpiresAt(), checkpoint: entry.authority.Checkpoint()}
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
		if cached := m.cache[reservation.key]; cached != nil && cached.authority.GrantDigest() == reservation.grant {
			if cached.state == cacheInvalid {
				return nil, ErrInvalidAuthority
			}
			return nil, ErrInvalidTransition
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
	if snapshot.generation == 0 || snapshot.generation != m.generation || entry.authority.AuthorityGeneration() != m.generation || reservation.key.AuthorityGeneration != m.generation || entry.authority.Checkpoint() != m.checkpoint.claims.Digest {
		m.invalidateEntryLocked(entry)
		return append(events, invalidationEvent(entry)), ErrStaleGeneration
	}
	if !entry.authority.valid() {
		m.invalidateEntryLocked(entry)
		return append(events, invalidationEvent(entry)), ErrInvalidAuthority
	}
	if now >= entry.authority.ExpiresAt() {
		m.invalidateEntryLocked(entry)
		return append(events, invalidationEvent(entry)), ErrExpired
	}
	for _, revoked := range m.checkpoint.revoked {
		if revoked == entry.authority.GrantDigest() {
			m.invalidateEntryLocked(entry)
			return append(events, invalidationEvent(entry)), ErrRevoked
		}
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
		terminal := false
		if cached := m.cache[reservation.key]; cached != nil && cached.authority.GrantDigest() == reservation.grant {
			terminal = true
		}
		m.mu.Unlock()
		if terminal {
			return ErrInvalidTransition
		}
		return ErrInvalidAuthority
	}
	if reservation.id == 0 || entry.reservation != reservation.id || entry.authority.Key() != reservation.key || entry.authority.GrantDigest() != reservation.grant || entry.state != cacheReserved {
		m.mu.Unlock()
		return ErrInvalidAuthority
	}
	entry.state = cacheAvailable
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
		terminal := false
		if cached := m.cache[reservation.key]; cached != nil && cached.authority.GrantDigest() == reservation.grant {
			terminal = true
		}
		m.mu.Unlock()
		if terminal {
			return ErrInvalidTransition
		}
		return ErrInvalidAuthority
	}
	if reservation.id == 0 || entry.reservation != reservation.id || entry.authority.Key() != reservation.key || entry.authority.GrantDigest() != reservation.grant || entry.state != cacheReserved {
		m.mu.Unlock()
		return ErrInvalidAuthority
	}
	entry.state = cacheQuarantined
	entry.reservation = 0
	delete(m.reserved, reservation.id)
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
	if entry != nil && (entry.state == cacheAvailable || entry.state == cacheReserved) {
		m.invalidateEntryLocked(entry)
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
		if entry.authority.AuthorityGeneration() < generation && (entry.state == cacheAvailable || entry.state == cacheReserved) {
			m.invalidateEntryLocked(entry)
			count++
			events = append(events, invalidationEvent(entry))
		}
	}
	m.mu.Unlock()
	m.notify(events)
	return count, nil
}

func (m *Manager) invalidateEntryLocked(entry *cacheEntry) {
	if entry.reservation != 0 {
		delete(m.reserved, entry.reservation)
		entry.reservation = 0
	}
	entry.state = cacheInvalid
}

func invalidationEvent(entry *cacheEntry) Event {
	return Event{Kind: EventAuthorityInvalidated, AuthorityGeneration: entry.authority.AuthorityGeneration(), Grant: entry.authority.GrantDigest(), Result: CodeInvalidAuthority}
}

func (m *Manager) Usage() Usage {
	if m == nil {
		return Usage{}
	}
	m.mu.RLock()
	usage := Usage{CacheEntries: len(m.cache), CacheBytes: m.cacheBytes, PendingCalls: len(m.pending), RequestRecords: len(m.requests)}
	m.mu.RUnlock()
	return usage
}

func (m *Manager) ValidateInvariants() error {
	if m == nil {
		return ErrInvalidAuthority
	}
	m.mu.RLock()
	defer m.mu.RUnlock()
	if len(m.cache) > m.limits.MaxCacheEntries || m.cacheBytes > m.limits.MaxCacheBytes || len(m.reserved) > len(m.cache) || len(m.grants) != len(m.cache) {
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
		case cacheConsumed, cacheQuarantined, cacheInvalid:
			if entry.reservation != 0 {
				return ErrInvalidAuthority
			}
		default:
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
	return nil
}

func addUint64(left, right uint64) (uint64, bool) {
	if right > math.MaxUint64-left {
		return 0, true
	}
	return left + right, false
}
