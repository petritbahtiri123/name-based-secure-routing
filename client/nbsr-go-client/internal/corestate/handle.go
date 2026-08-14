package corestate

func (s *Store) OpenGeneration(generation TSGeneration) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if generation == 0 || generation <= s.highestGeneration {
		return &StateError{Code: CodeGenerationClosed, Resource: "generation"}
	}
	if len(s.generations) >= s.limits.MaxGenerations {
		return &StateError{Code: CodeCapacityExceeded, Resource: "generations"}
	}

	s.generations[generation] = generationState{next: 1}
	s.highestGeneration = generation
	return nil
}

func (s *Store) CloseGeneration(generation TSGeneration) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if _, ok := s.generations[generation]; !ok {
		return &StateError{Code: CodeGenerationClosed, Resource: "generation"}
	}
	for key := range s.services {
		if key.generation == generation {
			return &StateError{Code: CodeInvalidTransition, Resource: "nonempty generation"}
		}
	}
	for key := range s.streams {
		if key.generation == generation {
			return &StateError{Code: CodeInvalidTransition, Resource: "nonempty generation"}
		}
	}

	delete(s.generations, generation)
	return nil
}

func (s *Store) allocateHandleLocked(generation TSGeneration) (ServiceHandle, error) {
	state, ok := s.generations[generation]
	if !ok {
		return InvalidServiceHandle, &StateError{Code: CodeGenerationClosed, Resource: "generation"}
	}
	if state.next == InvalidServiceHandle {
		return InvalidServiceHandle, &StateError{Code: CodeHandleExhausted, Resource: "service handle"}
	}
	return state.next, nil
}

func (s *Store) commitHandleLocked(generation TSGeneration, candidate ServiceHandle) error {
	state, ok := s.generations[generation]
	if !ok {
		return &StateError{Code: CodeGenerationClosed, Resource: "generation"}
	}
	if candidate == InvalidServiceHandle || candidate != state.next {
		return &StateError{Code: CodeInvalidTransition, Resource: "service handle allocation"}
	}
	state.next++
	s.generations[generation] = state
	return nil
}
