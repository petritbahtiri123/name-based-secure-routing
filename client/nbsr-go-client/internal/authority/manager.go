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

	cache    map[AuthorityKey]cachedAuthority
	pending  map[AuthorityKey]pendingCall
	requests map[RequestID]RequestSnapshot
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
		cache:              make(map[AuthorityKey]cachedAuthority),
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

func (m *Manager) PublishFreshness(context.Context, FreshnessRequest, ProviderFreshness) (VerifiedCheckpoint, error) {
	return VerifiedCheckpoint{}, ErrNotReady
}

func (m *Manager) CaptureGeneration() (GenerationSnapshot, error) {
	return GenerationSnapshot{}, ErrNotReady
}

func (m *Manager) ValidateForNewWork(Reservation, GenerationSnapshot, uint64) error {
	return ErrNotReady
}

func (m *Manager) Consume(Reservation, AdmissionOwner, GenerationSnapshot, uint64) (AuthorityHandle, error) {
	return AuthorityHandle{}, ErrNotReady
}

func (m *Manager) Release(Reservation) error { return ErrNotReady }

func (m *Manager) Quarantine(Reservation, RequestID) error { return ErrNotReady }

func (m *Manager) InvalidateGrant(RouteGrantDigest) error { return ErrNotReady }

func (m *Manager) InvalidateOlderThan(AuthorityGeneration) (int, error) { return 0, ErrNotReady }

func (m *Manager) Usage() Usage { return Usage{} }

func (m *Manager) ValidateInvariants() error { return ErrNotReady }

func (m *Manager) Close() error { return ErrNotReady }
