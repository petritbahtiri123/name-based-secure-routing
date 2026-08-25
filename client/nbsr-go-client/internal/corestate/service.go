package corestate

import (
	"math"
	"strings"
)

type channelKey struct {
	generation TSGeneration
	channelID  ChannelID
}

func (s *Store) AddService(spec ServiceSpec) (ServiceSnapshot, error) {
	s.mu.Lock()

	if spec.Generation == 0 || spec.ChannelID == (ChannelID{}) || spec.ChannelGeneration == 0 ||
		spec.ServiceIdentity == "" || spec.RouteGrantDigest == (RouteGrantDigest{}) ||
		spec.AuthorityGeneration == 0 || spec.CreditState == 0 {
		s.mu.Unlock()
		return ServiceSnapshot{}, &StateError{Code: CodeInvalidTransition, Resource: "service specification"}
	}
	if len(spec.ServiceIdentity) > s.limits.MaxServiceIdentityBytes {
		s.mu.Unlock()
		return ServiceSnapshot{}, &StateError{Code: CodeByteCapacityExceeded, Resource: "service identity"}
	}
	if _, ok := s.generations[spec.Generation]; !ok {
		s.mu.Unlock()
		return ServiceSnapshot{}, &StateError{Code: CodeGenerationClosed, Resource: "generation"}
	}
	channel := channelKey{generation: spec.Generation, channelID: spec.ChannelID}
	if _, ok := s.servicesByChannel[channel]; ok {
		s.mu.Unlock()
		return ServiceSnapshot{}, &StateError{Code: CodeDuplicateService, Resource: "channel"}
	}
	cost, err := serviceCost(spec)
	if err != nil {
		s.mu.Unlock()
		return ServiceSnapshot{}, err
	}
	if len(s.services) >= s.limits.MaxServices {
		s.mu.Unlock()
		return ServiceSnapshot{}, &StateError{Code: CodeCapacityExceeded, Resource: "services"}
	}
	if s.usage.ServiceBytes > s.limits.MaxServiceBytes || cost > s.limits.MaxServiceBytes-s.usage.ServiceBytes {
		s.mu.Unlock()
		return ServiceSnapshot{}, &StateError{Code: CodeByteCapacityExceeded, Resource: "service bytes"}
	}
	handle, err := s.allocateHandleLocked(spec.Generation)
	if err != nil {
		s.mu.Unlock()
		return ServiceSnapshot{}, err
	}

	owned := spec
	owned.ServiceIdentity = strings.Clone(spec.ServiceIdentity)
	snapshot := ServiceSnapshot{
		ServiceSpec:    owned,
		Handle:         handle,
		State:          ServiceActive,
		AccountedBytes: cost,
	}
	key := serviceKey{generation: spec.Generation, handle: handle}
	s.services[key] = snapshot
	s.servicesByChannel[channel] = key
	s.usage.Services++
	s.usage.ServiceBytes += cost
	if err := s.commitHandleLocked(spec.Generation, handle); err != nil {
		delete(s.services, key)
		delete(s.servicesByChannel, channel)
		s.usage.Services--
		s.usage.ServiceBytes -= cost
		s.mu.Unlock()
		return ServiceSnapshot{}, err
	}
	result := copyServiceSnapshot(snapshot)
	s.mu.Unlock()

	s.observer.Observe(Event{Kind: EventServiceInserted})
	return result, nil
}

func (s *Store) LookupService(generation TSGeneration, handle ServiceHandle) (ServiceSnapshot, error) {
	if handle == InvalidServiceHandle {
		return ServiceSnapshot{}, &StateError{Code: CodeInvalidHandle, Resource: "service handle"}
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	entry, ok := s.services[serviceKey{generation: generation, handle: handle}]
	if !ok {
		return ServiceSnapshot{}, &StateError{Code: CodeUnknownService, Resource: "service"}
	}
	return copyServiceSnapshot(entry), nil
}

func (s *Store) CloseService(generation TSGeneration, handle ServiceHandle) error {
	if handle == InvalidServiceHandle {
		return &StateError{Code: CodeInvalidHandle, Resource: "service handle"}
	}
	key := serviceKey{generation: generation, handle: handle}
	s.mu.Lock()
	err := s.closeServiceLocked(key)
	s.mu.Unlock()
	if err != nil {
		return err
	}

	s.observer.Observe(Event{Kind: EventServiceClosed})
	return nil
}

func (s *Store) RemoveService(generation TSGeneration, handle ServiceHandle) error {
	if handle == InvalidServiceHandle {
		return &StateError{Code: CodeInvalidHandle, Resource: "service handle"}
	}
	key := serviceKey{generation: generation, handle: handle}
	s.mu.Lock()
	err := s.removeServiceLocked(key)
	s.mu.Unlock()
	if err != nil {
		return err
	}

	s.observer.Observe(Event{Kind: EventServiceRemoved})
	return nil
}

func (s *Store) closeServiceLocked(key serviceKey) error {
	entry, ok := s.services[key]
	if !ok {
		return &StateError{Code: CodeUnknownService, Resource: "service"}
	}
	if entry.State != ServiceActive {
		return &StateError{Code: CodeServiceClosed, Resource: "service"}
	}
	entry.State = ServiceClosed
	s.services[key] = entry
	return nil
}

func (s *Store) removeServiceLocked(key serviceKey) error {
	entry, ok := s.services[key]
	if !ok {
		return &StateError{Code: CodeUnknownService, Resource: "service"}
	}
	if entry.State != ServiceClosed || entry.ActiveStreams != 0 {
		return &StateError{Code: CodeInvalidTransition, Resource: "service removal"}
	}
	delete(s.services, key)
	delete(s.servicesByChannel, channelKey{generation: key.generation, channelID: entry.ChannelID})
	s.usage.Services--
	s.usage.ServiceBytes -= entry.AccountedBytes
	return nil
}

func (s *Store) teardownServiceLocked(key serviceKey, entry ServiceSnapshot) {
	delete(s.services, key)
	delete(s.servicesByChannel, channelKey{generation: key.generation, channelID: entry.ChannelID})
	s.usage.Services--
	s.usage.ServiceBytes -= entry.AccountedBytes
}

func (s *Store) incrementStreamsLocked(generation TSGeneration, handle ServiceHandle) error {
	if handle == InvalidServiceHandle {
		return &StateError{Code: CodeInvalidHandle, Resource: "service handle"}
	}
	key := serviceKey{generation: generation, handle: handle}
	entry, ok := s.services[key]
	if !ok {
		return &StateError{Code: CodeUnknownService, Resource: "service"}
	}
	if entry.State != ServiceActive {
		return &StateError{Code: CodeServiceClosed, Resource: "service"}
	}
	if entry.ActiveStreams == math.MaxUint64 {
		return &StateError{Code: CodeAccountingOverflow, Resource: "service stream count"}
	}
	entry.ActiveStreams++
	s.services[key] = entry
	return nil
}

func (s *Store) decrementStreamsLocked(generation TSGeneration, handle ServiceHandle) error {
	if handle == InvalidServiceHandle {
		return &StateError{Code: CodeInvalidHandle, Resource: "service handle"}
	}
	key := serviceKey{generation: generation, handle: handle}
	entry, ok := s.services[key]
	if !ok {
		return &StateError{Code: CodeUnknownService, Resource: "service"}
	}
	if entry.ActiveStreams == 0 {
		return &StateError{Code: CodeInvalidTransition, Resource: "service stream count underflow"}
	}
	entry.ActiveStreams--
	s.services[key] = entry
	return nil
}

func copyServiceSnapshot(snapshot ServiceSnapshot) ServiceSnapshot {
	snapshot.ServiceIdentity = strings.Clone(snapshot.ServiceIdentity)
	return snapshot
}
