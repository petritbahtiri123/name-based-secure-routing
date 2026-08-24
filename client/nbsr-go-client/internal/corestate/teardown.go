package corestate

import (
	"fmt"
	"math"
)

func (s *Store) CloseGeneration(generation TSGeneration) error {
	s.mu.Lock()
	if _, ok := s.generations[generation]; !ok {
		s.mu.Unlock()
		return &StateError{Code: CodeGenerationClosed, Resource: "generation"}
	}

	// Removing the generation first makes every later insertion fail closed.
	delete(s.generations, generation)
	for key, entry := range s.services {
		if key.generation == generation && entry.State == ServiceActive {
			entry.State = ServiceClosed
			s.services[key] = entry
		}
	}
	for key, entry := range s.streams {
		if key.generation != generation {
			continue
		}
		if entry.State == StreamActive {
			entry.State = StreamFinished
			entry.TerminalReason = TerminalFailed
		}
		s.teardownStreamLocked(key, entry)
	}
	for key, entry := range s.services {
		if key.generation != generation {
			continue
		}
		s.teardownServiceLocked(key, entry)
	}
	s.mu.Unlock()

	s.observer.Observe(Event{Kind: EventGenerationClosed, Generation: generation})
	return nil
}

func (s *Store) validateInvariantsLocked() error {
	var got Usage
	activeStreams := make(map[serviceKey]uint64, len(s.services))

	for generation, state := range s.generations {
		if generation == 0 || generation > s.highestGeneration {
			return invariantError("generation key or high-water mark")
		}
		if state.next == InvalidServiceHandle {
			// Zero is the valid exhausted allocator sentinel after MaxUint32 commits.
			continue
		}
	}

	for id, entry := range s.mappings {
		if id == 0 || id != entry.snapshot.ID || id > s.highestMappingID {
			return invariantError("mapping identity")
		}
		targetEdgeBytes := 0
		for _, edge := range entry.snapshot.RouteIntent.TargetEdges {
			targetEdgeBytes += len(edge)
		}
		if !validMappingSpec(entry.snapshot.MappingSpec) || len(entry.snapshot.ServiceIdentity) > s.limits.MaxServiceIdentityBytes ||
			len(entry.snapshot.PolicyContext) > s.limits.MaxPolicyContextBytes || len(entry.snapshot.CanonicalName) > s.limits.MaxCanonicalNameBytes ||
			len(entry.snapshot.RouteIntent.Canonical) > s.limits.MaxRouteIntentBytes || targetEdgeBytes > s.limits.MaxTargetEdgeBytes {
			return invariantError("mapping specification")
		}
		cost, err := mappingCost(entry.snapshot.MappingSpec)
		if err != nil || cost != entry.snapshot.AccountedBytes {
			return invariantError("mapping accounting")
		}
		got.Mappings++
		if addOverflow(got.MappingBytes, cost) {
			return accountingInvariantError("mapping bytes")
		}
		got.MappingBytes += cost
	}

	for key, entry := range s.services {
		if key.generation == 0 || key.handle == InvalidServiceHandle || key.generation != entry.Generation || key.handle != entry.Handle {
			return invariantError("service identity")
		}
		state, ok := s.generations[key.generation]
		if !ok || (state.next != InvalidServiceHandle && key.handle >= state.next) {
			return invariantError("service generation or handle")
		}
		if entry.State != ServiceActive && entry.State != ServiceClosed {
			return invariantError("service lifecycle")
		}
		if entry.ChannelID == (ChannelID{}) || entry.ChannelGeneration == 0 || entry.ServiceIdentity == "" || len(entry.ServiceIdentity) > s.limits.MaxServiceIdentityBytes || entry.RouteGrantDigest == (RouteGrantDigest{}) || entry.AuthorityGeneration == 0 || entry.CreditState == 0 {
			return invariantError("service specification")
		}
		cost, err := serviceCost(entry.ServiceSpec)
		if err != nil || cost != entry.AccountedBytes {
			return invariantError("service accounting")
		}
		channel := channelKey{generation: key.generation, channelID: entry.ChannelID}
		if reverse, ok := s.servicesByChannel[channel]; !ok || reverse != key {
			return invariantError("service reverse index")
		}
		got.Services++
		if addOverflow(got.ServiceBytes, cost) {
			return accountingInvariantError("service bytes")
		}
		got.ServiceBytes += cost
	}
	if len(s.servicesByChannel) != len(s.services) {
		return invariantError("service reverse index cardinality")
	}
	for channel, key := range s.servicesByChannel {
		entry, ok := s.services[key]
		if !ok || channel.generation != key.generation || channel.channelID != entry.ChannelID {
			return invariantError("service reverse index bijection")
		}
	}

	for key, entry := range s.streams {
		if key.generation != entry.Generation || key.handle != entry.Handle || key.streamID != entry.StreamID {
			return invariantError("stream identity")
		}
		if entry.Generation == 0 || entry.Handle == InvalidServiceHandle || entry.LocalFlowID == 0 {
			return invariantError("stream specification")
		}
		ownerKey := serviceKey{generation: key.generation, handle: key.handle}
		if _, ok := s.generations[key.generation]; !ok {
			return invariantError("stream generation")
		}
		if _, ok := s.services[ownerKey]; !ok {
			return invariantError("stream owner")
		}
		switch entry.State {
		case StreamActive:
			if entry.TerminalReason != TerminalNone {
				return invariantError("active stream terminal reason")
			}
		case StreamCancelled:
			if entry.TerminalReason != TerminalCancelled {
				return invariantError("cancelled stream terminal reason")
			}
		case StreamFinished:
			if entry.TerminalReason != TerminalCompleted && entry.TerminalReason != TerminalFailed {
				return invariantError("finished stream terminal reason")
			}
		default:
			return invariantError("stream lifecycle")
		}
		if entry.AccountedBytes != streamCost(entry.StreamSpec) {
			return invariantError("stream accounting")
		}
		if activeStreams[ownerKey] == math.MaxUint64 {
			return accountingInvariantError("service stream count")
		}
		activeStreams[ownerKey]++
		got.Streams++
		if addOverflow(got.StreamBytes, entry.AccountedBytes) {
			return accountingInvariantError("stream bytes")
		}
		got.StreamBytes += entry.AccountedBytes
	}
	for key, entry := range s.services {
		if entry.ActiveStreams != activeStreams[key] {
			return invariantError("service stream count")
		}
	}
	if len(s.generations) > s.limits.MaxGenerations || got.Mappings > s.limits.MaxMappings || got.Services > s.limits.MaxServices || got.Streams > s.limits.MaxStreams {
		return invariantError("entry capacity")
	}
	if got.MappingBytes > s.limits.MaxMappingBytes || got.ServiceBytes > s.limits.MaxServiceBytes || got.StreamBytes > s.limits.MaxStreamBytes {
		return invariantError("byte capacity")
	}
	if got != s.usage {
		return invariantError(fmt.Sprintf("usage: got %+v recorded %+v", got, s.usage))
	}
	return nil
}

func addOverflow(a, b uint64) bool { return b > math.MaxUint64-a }

func invariantError(resource string) error {
	return &StateError{Code: CodeInvalidTransition, Resource: "invariant " + resource}
}

func accountingInvariantError(resource string) error {
	return &StateError{Code: CodeAccountingOverflow, Resource: "invariant " + resource}
}
