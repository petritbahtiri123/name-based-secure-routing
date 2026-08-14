package authority

import (
	"context"
	"reflect"
	"sync"
)

type cachedAuthority struct{}
type pendingCall struct{}

// Manager owns bounded authority bookkeeping. Verification and provider work
// are added by later tasks.
type Manager struct {
	mu sync.RWMutex

	limits             Limits
	clock              Clock
	provider           AuthorityProvider
	verifier           *Verifier
	checkpointVerifier CheckpointEvidenceVerifier
	floorStore         GenerationFloorStore
	observer           Observer

	cache           map[AuthorityKey]*cacheEntry
	grants          map[RouteGrantDigest]*cacheEntry
	reserved        map[uint64]*cacheEntry
	cacheBytes      uint64
	nextReservation uint64
	pending         map[AuthorityKey]pendingCall
	requests        map[RequestID]RequestSnapshot

	checkpoint       checkpointState
	generation       AuthorityGeneration
	hasCheckpoint    bool
	freshnessExpired bool
}

func NewManager(limits Limits, clock Clock, provider AuthorityProvider, verifier *Verifier, checkpointVerifier CheckpointEvidenceVerifier, floorStore GenerationFloorStore, observer Observer) (*Manager, error) {
	if err := limits.Validate(); err != nil {
		return nil, err
	}
	if isNilDependency(clock) || isNilDependency(provider) || verifier == nil || isNilDependency(checkpointVerifier) || isNilDependency(floorStore) || isNilDependency(observer) {
		return nil, &AuthorityError{Code: CodeInvalidAuthority, Resource: "manager dependency"}
	}
	return &Manager{
		limits:             limits,
		clock:              clock,
		provider:           provider,
		verifier:           verifier,
		checkpointVerifier: checkpointVerifier,
		floorStore:         floorStore,
		observer:           observer,
		cache:              make(map[AuthorityKey]*cacheEntry),
		grants:             make(map[RouteGrantDigest]*cacheEntry),
		reserved:           make(map[uint64]*cacheEntry),
		pending:            make(map[AuthorityKey]pendingCall),
		requests:           make(map[RequestID]RequestSnapshot),
	}, nil
}

func isNilDependency(dependency any) bool {
	if dependency == nil {
		return true
	}
	value := reflect.ValueOf(dependency)
	switch value.Kind() {
	case reflect.Chan, reflect.Func, reflect.Interface, reflect.Map, reflect.Pointer, reflect.Slice:
		return value.IsNil()
	default:
		return false
	}
}

func (m *Manager) mutate(change func() ([]Event, error)) error {
	m.mu.Lock()
	events, err := change()
	m.mu.Unlock()
	m.notify(events)
	return err
}

func (m *Manager) notify(events []Event) {
	for _, event := range events {
		m.observer.Observe(event)
	}
}

func (m *Manager) Acquire(context.Context, AcquireRequest) (Reservation, error) {
	return Reservation{}, ErrNotReady
}

func (m *Manager) Renew(context.Context, RenewRequest) (Reservation, error) {
	return Reservation{}, ErrNotReady
}

func (m *Manager) Close() error { return ErrNotReady }
