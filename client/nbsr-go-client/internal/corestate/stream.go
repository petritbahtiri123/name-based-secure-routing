package corestate

func (s *Store) InsertStream(spec StreamSpec) error {
	if spec.Handle == InvalidServiceHandle {
		return &StateError{Code: CodeInvalidHandle, Resource: "service handle"}
	}
	if spec.Generation == 0 || spec.LocalFlowID == 0 {
		return &StateError{Code: CodeInvalidTransition, Resource: "stream specification"}
	}

	key := streamKey{generation: spec.Generation, handle: spec.Handle, streamID: spec.StreamID}
	cost := streamCost(spec)
	s.mu.Lock()
	owner, ok := s.services[serviceKey{generation: spec.Generation, handle: spec.Handle}]
	if !ok {
		s.mu.Unlock()
		return &StateError{Code: CodeUnknownService, Resource: "service"}
	}
	if owner.State != ServiceActive {
		s.mu.Unlock()
		return &StateError{Code: CodeServiceClosed, Resource: "service"}
	}
	if _, ok := s.streams[key]; ok {
		s.mu.Unlock()
		return &StateError{Code: CodeDuplicateStream, Resource: "stream"}
	}
	if len(s.streams) >= s.limits.MaxStreams {
		s.mu.Unlock()
		return &StateError{Code: CodeCapacityExceeded, Resource: "streams"}
	}
	if s.usage.StreamBytes > s.limits.MaxStreamBytes || cost > s.limits.MaxStreamBytes-s.usage.StreamBytes {
		s.mu.Unlock()
		return &StateError{Code: CodeByteCapacityExceeded, Resource: "stream bytes"}
	}
	if err := s.incrementStreamsLocked(spec.Generation, spec.Handle); err != nil {
		s.mu.Unlock()
		return err
	}
	s.streams[key] = StreamSnapshot{
		StreamSpec:     spec,
		State:          StreamActive,
		TerminalReason: TerminalNone,
		AccountedBytes: cost,
	}
	s.usage.Streams++
	s.usage.StreamBytes += cost
	s.mu.Unlock()

	s.observer.Observe(Event{Kind: EventStreamInserted, Generation: spec.Generation, Handle: spec.Handle, StreamID: spec.StreamID})
	return nil
}

func (s *Store) LookupStream(generation TSGeneration, handle ServiceHandle, streamID StreamID) (StreamSnapshot, error) {
	if handle == InvalidServiceHandle {
		return StreamSnapshot{}, &StateError{Code: CodeInvalidHandle, Resource: "service handle"}
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	if _, ok := s.services[serviceKey{generation: generation, handle: handle}]; !ok {
		return StreamSnapshot{}, &StateError{Code: CodeUnknownService, Resource: "service"}
	}
	entry, ok := s.streams[streamKey{generation: generation, handle: handle, streamID: streamID}]
	if !ok {
		return StreamSnapshot{}, &StateError{Code: CodeInvalidTransition, Resource: "stream"}
	}
	return entry, nil
}

func (s *Store) CancelStream(generation TSGeneration, handle ServiceHandle, streamID StreamID) error {
	return s.terminalStream(generation, handle, streamID, StreamCancelled, TerminalCancelled)
}

func (s *Store) FinishStream(generation TSGeneration, handle ServiceHandle, streamID StreamID, reason TerminalReason) error {
	if reason != TerminalCompleted && reason != TerminalFailed {
		return &StateError{Code: CodeInvalidTransition, Resource: "terminal reason"}
	}
	return s.terminalStream(generation, handle, streamID, StreamFinished, reason)
}

func (s *Store) terminalStream(generation TSGeneration, handle ServiceHandle, streamID StreamID, state StreamState, reason TerminalReason) error {
	if handle == InvalidServiceHandle {
		return &StateError{Code: CodeInvalidHandle, Resource: "service handle"}
	}
	key := streamKey{generation: generation, handle: handle, streamID: streamID}
	s.mu.Lock()
	if _, ok := s.services[serviceKey{generation: generation, handle: handle}]; !ok {
		s.mu.Unlock()
		return &StateError{Code: CodeUnknownService, Resource: "service"}
	}
	entry, ok := s.streams[key]
	if !ok || entry.State != StreamActive {
		s.mu.Unlock()
		return &StateError{Code: CodeInvalidTransition, Resource: "stream terminal transition"}
	}
	entry.State = state
	entry.TerminalReason = reason
	s.streams[key] = entry
	s.mu.Unlock()

	s.observer.Observe(Event{Kind: EventStreamTerminal, Generation: generation, Handle: handle, StreamID: streamID})
	return nil
}

func (s *Store) RemoveStream(generation TSGeneration, handle ServiceHandle, streamID StreamID) error {
	if handle == InvalidServiceHandle {
		return &StateError{Code: CodeInvalidHandle, Resource: "service handle"}
	}
	key := streamKey{generation: generation, handle: handle, streamID: streamID}
	s.mu.Lock()
	if _, ok := s.services[serviceKey{generation: generation, handle: handle}]; !ok {
		s.mu.Unlock()
		return &StateError{Code: CodeUnknownService, Resource: "service"}
	}
	entry, ok := s.streams[key]
	if !ok || entry.State == StreamActive {
		s.mu.Unlock()
		return &StateError{Code: CodeInvalidTransition, Resource: "stream removal"}
	}
	if err := s.decrementStreamsLocked(generation, handle); err != nil {
		s.mu.Unlock()
		return err
	}
	delete(s.streams, key)
	s.usage.Streams--
	s.usage.StreamBytes -= entry.AccountedBytes
	s.mu.Unlock()

	s.observer.Observe(Event{Kind: EventStreamRemoved, Generation: generation, Handle: handle, StreamID: streamID})
	return nil
}
