package corestate

import "sync"

type generationState struct {
	closed          bool
	highWaterHandle ServiceHandle
}

type serviceKey struct {
	generation TSGeneration
	handle     ServiceHandle
}

type streamKey struct {
	generation TSGeneration
	handle     ServiceHandle
	streamID   StreamID
}

type Store struct {
	mu sync.RWMutex

	limits   Limits
	clock    Clock
	observer Observer

	generations map[TSGeneration]generationState
	mappings    map[MappingID]MappingSnapshot
	services    map[serviceKey]ServiceSnapshot
	streams     map[streamKey]StreamSnapshot

	mappingHighWater MappingID
	usage            Usage
}

func NewStore(limits Limits, clock Clock, observer Observer) (*Store, error) {
	if err := limits.Validate(); err != nil {
		return nil, err
	}
	if clock == nil {
		return nil, &StateError{Code: CodeInvalidLimits, Resource: "clock is required"}
	}
	if observer == nil {
		observer = noopObserver{}
	}
	return &Store{
		limits:      limits,
		clock:       clock,
		observer:    observer,
		generations: make(map[TSGeneration]generationState),
		mappings:    make(map[MappingID]MappingSnapshot),
		services:    make(map[serviceKey]ServiceSnapshot),
		streams:     make(map[streamKey]StreamSnapshot),
	}, nil
}

func (s *Store) OpenGeneration(TSGeneration) error  { return unimplementedTransition() }
func (s *Store) CloseGeneration(TSGeneration) error { return unimplementedTransition() }

func (s *Store) AddMapping(MappingSpec) (MappingSnapshot, error) {
	return MappingSnapshot{}, unimplementedTransition()
}
func (s *Store) LookupMapping(MappingID) (MappingSnapshot, error) {
	return MappingSnapshot{}, unimplementedTransition()
}
func (s *Store) AcquireMapping(MappingID) (MappingSnapshot, error) {
	return MappingSnapshot{}, unimplementedTransition()
}
func (s *Store) ReleaseMapping(MappingID) error { return unimplementedTransition() }
func (s *Store) RemoveMapping(MappingID) error  { return unimplementedTransition() }
func (s *Store) ExpireMappings() (int, error)   { return 0, unimplementedTransition() }

func (s *Store) AddService(ServiceSpec) (ServiceSnapshot, error) {
	return ServiceSnapshot{}, unimplementedTransition()
}
func (s *Store) LookupService(TSGeneration, ServiceHandle) (ServiceSnapshot, error) {
	return ServiceSnapshot{}, unimplementedTransition()
}
func (s *Store) CloseService(TSGeneration, ServiceHandle) error  { return unimplementedTransition() }
func (s *Store) RemoveService(TSGeneration, ServiceHandle) error { return unimplementedTransition() }

func (s *Store) InsertStream(StreamSpec) error { return unimplementedTransition() }
func (s *Store) LookupStream(TSGeneration, ServiceHandle, StreamID) (StreamSnapshot, error) {
	return StreamSnapshot{}, unimplementedTransition()
}
func (s *Store) CancelStream(TSGeneration, ServiceHandle, StreamID) error {
	return unimplementedTransition()
}
func (s *Store) FinishStream(TSGeneration, ServiceHandle, StreamID, TerminalReason) error {
	return unimplementedTransition()
}
func (s *Store) RemoveStream(TSGeneration, ServiceHandle, StreamID) error {
	return unimplementedTransition()
}

func (s *Store) Usage() Usage {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.usage
}

func (s *Store) ValidateInvariants() error {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return nil
}

func unimplementedTransition() error {
	return &StateError{Code: CodeInvalidTransition, Resource: "not implemented in foundation task"}
}

var (
	_ MappingRegistry = (*Store)(nil)
	_ ServiceRegistry = (*Store)(nil)
	_ StreamRegistry  = (*Store)(nil)
)
