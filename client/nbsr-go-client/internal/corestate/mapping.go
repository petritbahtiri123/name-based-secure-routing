package corestate

import (
	"math"
	"strings"
)

type mappingEntry struct {
	snapshot MappingSnapshot
}

func (s *Store) AddMapping(spec MappingSpec) (MappingSnapshot, error) {
	s.mu.Lock()

	if spec.ServiceIdentity == "" || spec.ExpiresAtUnix == 0 {
		s.mu.Unlock()
		return MappingSnapshot{}, &StateError{Code: CodeInvalidTransition, Resource: "mapping specification"}
	}
	if len(spec.ServiceIdentity) > s.limits.MaxServiceIdentityBytes || len(spec.PolicyContext) > s.limits.MaxPolicyContextBytes {
		s.mu.Unlock()
		return MappingSnapshot{}, &StateError{Code: CodeByteCapacityExceeded, Resource: "mapping fields"}
	}
	cost, err := mappingCost(spec)
	if err != nil {
		s.mu.Unlock()
		return MappingSnapshot{}, err
	}
	if s.highestMappingID == MappingID(math.MaxUint64) {
		s.mu.Unlock()
		return MappingSnapshot{}, &StateError{Code: CodeMappingIDExhausted, Resource: "mapping ID"}
	}
	if len(s.mappings) >= s.limits.MaxMappings {
		s.mu.Unlock()
		return MappingSnapshot{}, &StateError{Code: CodeCapacityExceeded, Resource: "mappings"}
	}
	if s.usage.MappingBytes > s.limits.MaxMappingBytes || cost > s.limits.MaxMappingBytes-s.usage.MappingBytes {
		s.mu.Unlock()
		return MappingSnapshot{}, &StateError{Code: CodeByteCapacityExceeded, Resource: "mapping bytes"}
	}

	id := s.highestMappingID + 1
	owned := MappingSpec{
		ServiceIdentity: strings.Clone(spec.ServiceIdentity),
		ExpiresAtUnix:   spec.ExpiresAtUnix,
		PolicyContext:   PolicyContext(strings.Clone(string(spec.PolicyContext))),
	}
	if err := s.insertMappingWithIDLocked(id, owned, cost); err != nil {
		s.mu.Unlock()
		return MappingSnapshot{}, err
	}
	s.highestMappingID = id
	snapshot := copyMappingSnapshot(s.mappings[id].snapshot)
	s.mu.Unlock()

	s.observer.Observe(Event{Kind: EventMappingInserted, MappingID: id})
	return snapshot, nil
}

func (s *Store) insertMappingWithIDLocked(id MappingID, spec MappingSpec, cost uint64) error {
	if current, ok := s.mappings[id]; ok {
		if current.snapshot.MappingSpec != spec {
			return &StateError{Code: CodeMappingConflict, Resource: "mapping ID"}
		}
		return nil
	}
	s.mappings[id] = mappingEntry{snapshot: MappingSnapshot{
		MappingSpec:    spec,
		ID:             id,
		AccountedBytes: cost,
	}}
	s.usage.Mappings++
	s.usage.MappingBytes += cost
	return nil
}

func (s *Store) LookupMapping(id MappingID) (MappingSnapshot, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	entry, ok := s.mappings[id]
	if !ok {
		return MappingSnapshot{}, &StateError{Code: CodeUnknownMapping, Resource: "mapping"}
	}
	if s.clock.NowUnix() >= entry.snapshot.ExpiresAtUnix {
		return MappingSnapshot{}, &StateError{Code: CodeExpiredMapping, Resource: "mapping"}
	}
	return copyMappingSnapshot(entry.snapshot), nil
}

func (s *Store) AcquireMapping(id MappingID) (MappingSnapshot, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	entry, ok := s.mappings[id]
	if !ok {
		return MappingSnapshot{}, &StateError{Code: CodeUnknownMapping, Resource: "mapping"}
	}
	if s.clock.NowUnix() >= entry.snapshot.ExpiresAtUnix {
		return MappingSnapshot{}, &StateError{Code: CodeExpiredMapping, Resource: "mapping"}
	}
	if entry.snapshot.ActiveReferences == math.MaxUint64 {
		return MappingSnapshot{}, &StateError{Code: CodeAccountingOverflow, Resource: "mapping references"}
	}
	entry.snapshot.ActiveReferences++
	s.mappings[id] = entry
	return copyMappingSnapshot(entry.snapshot), nil
}

func (s *Store) ReleaseMapping(id MappingID) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	entry, ok := s.mappings[id]
	if !ok {
		return &StateError{Code: CodeUnknownMapping, Resource: "mapping"}
	}
	if entry.snapshot.ActiveReferences == 0 {
		return &StateError{Code: CodeInvalidTransition, Resource: "mapping reference underflow"}
	}
	entry.snapshot.ActiveReferences--
	s.mappings[id] = entry
	return nil
}

func (s *Store) RemoveMapping(id MappingID) error {
	s.mu.Lock()
	entry, ok := s.mappings[id]
	if !ok {
		s.mu.Unlock()
		return &StateError{Code: CodeUnknownMapping, Resource: "mapping"}
	}
	if entry.snapshot.ActiveReferences != 0 {
		s.mu.Unlock()
		return &StateError{Code: CodeInvalidTransition, Resource: "referenced mapping"}
	}
	s.removeMappingLocked(id, entry)
	s.mu.Unlock()

	s.observer.Observe(Event{Kind: EventMappingRemoved, MappingID: id})
	return nil
}

func (s *Store) ExpireMappings() (int, error) {
	now := s.clock.NowUnix()
	s.mu.Lock()
	removedIDs := make([]MappingID, 0)
	referenced := false
	for id, entry := range s.mappings {
		if now < entry.snapshot.ExpiresAtUnix {
			continue
		}
		if entry.snapshot.ActiveReferences != 0 {
			referenced = true
			continue
		}
		s.removeMappingLocked(id, entry)
		removedIDs = append(removedIDs, id)
	}
	s.mu.Unlock()

	var firstObserverPanic any
	for _, id := range removedIDs {
		func() {
			defer func() {
				if recovered := recover(); recovered != nil && firstObserverPanic == nil {
					firstObserverPanic = recovered
				}
			}()
			s.observer.Observe(Event{Kind: EventMappingRemoved, MappingID: id})
		}()
	}
	if firstObserverPanic != nil {
		panic(firstObserverPanic)
	}
	if referenced {
		return len(removedIDs), &StateError{Code: CodeInvalidTransition, Resource: "referenced expired mapping"}
	}
	return len(removedIDs), nil
}

func (s *Store) removeMappingLocked(id MappingID, entry mappingEntry) {
	delete(s.mappings, id)
	s.usage.Mappings--
	s.usage.MappingBytes -= entry.snapshot.AccountedBytes
}

func copyMappingSnapshot(snapshot MappingSnapshot) MappingSnapshot {
	snapshot.ServiceIdentity = strings.Clone(snapshot.ServiceIdentity)
	snapshot.PolicyContext = PolicyContext(strings.Clone(string(snapshot.PolicyContext)))
	return snapshot
}
