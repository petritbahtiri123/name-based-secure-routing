package authority

import (
	"context"
	"errors"
	"reflect"
	"sync"
	"testing"
)

func TestColdStartRequiresFreshness(t *testing.T) {
	gate := newGate(t, testFloor(7))
	if err := gate.Load(context.Background(), "source-a", "profile-a"); err != nil {
		t.Fatal(err)
	}
	if gate.State() != RestartFreshnessRequired {
		t.Fatalf("state = %v, want RestartFreshnessRequired", gate.State())
	}
	if err := gate.RequireReady(); !errors.Is(err, ErrNotReady) {
		t.Fatalf("RequireReady error = %v, want ErrNotReady", err)
	}
}

func TestRestartRejectsFloorRollbackAndRequiresFreshnessAfterEachLoad(t *testing.T) {
	gate := newGate(t, testFloor(7))
	if err := gate.Load(context.Background(), "source-a", "profile-a"); err != nil {
		t.Fatal(err)
	}
	if _, err := gate.AcceptFresh(context.Background(), freshnessRequest(6), freshnessEvidence(6)); !errors.Is(err, ErrGenerationRollback) {
		t.Fatalf("below floor error = %v, want ErrGenerationRollback", err)
	}
	if gate.State() != RestartFailClosed || !errors.Is(gate.RequireReady(), ErrNotReady) {
		t.Fatalf("state after rejected freshness = %v, ready = %v", gate.State(), gate.RequireReady())
	}
	gate = newGate(t, testFloor(7))
	if err := gate.Load(context.Background(), "source-a", "profile-a"); err != nil {
		t.Fatal(err)
	}
	if _, err := gate.AcceptFresh(context.Background(), freshnessRequest(7), freshnessEvidence(7)); err != nil {
		t.Fatal(err)
	}
	if gate.State() != RestartReady || gate.RequireReady() != nil {
		t.Fatalf("state after fresh checkpoint = %v, ready = %v", gate.State(), gate.RequireReady())
	}
	if err := gate.Load(context.Background(), "source-a", "profile-a"); err != nil {
		t.Fatal(err)
	}
	if gate.State() != RestartFreshnessRequired || !errors.Is(gate.RequireReady(), ErrNotReady) {
		t.Fatalf("restarted state = %v, ready = %v", gate.State(), gate.RequireReady())
	}
}

func TestRestartFailsClosedForInvalidFloorAndStoreFailure(t *testing.T) {
	badStore := &scriptedFloorStore{load: SignedGenerationFloor{SourceOperator: "source-a", Profile: "profile-a", Generation: 7, Checkpoint: testCheckpoint(7)}}
	gate, err := NewRestartGate(badStore, testCheckpointVerifier{}, testClock{now: 100}, noopObserver{})
	if err != nil {
		t.Fatal(err)
	}
	if err := gate.Load(context.Background(), "source-a", "profile-a"); !errors.Is(err, ErrFloorInvalid) || gate.State() != RestartFailClosed {
		t.Fatalf("invalid floor: err=%v state=%v", err, gate.State())
	}

	failingStore := &scriptedFloorStore{load: testFloor(7), storeErr: errors.New("write failed")}
	gate, err = NewRestartGate(failingStore, testCheckpointVerifier{}, testClock{now: 100}, noopObserver{})
	if err != nil {
		t.Fatal(err)
	}
	if err := gate.Load(context.Background(), "source-a", "profile-a"); err != nil {
		t.Fatal(err)
	}
	if _, err := gate.AcceptFresh(context.Background(), freshnessRequest(8), freshnessEvidence(8)); err == nil || gate.State() != RestartFailClosed {
		t.Fatalf("store failure: err=%v state=%v", err, gate.State())
	}
}

func TestRestartAllowsMissingFloorButStillRequiresFreshness(t *testing.T) {
	store := &scriptedFloorStore{loadErr: ErrFloorNotFound}
	gate, err := NewRestartGate(store, testCheckpointVerifier{}, testClock{now: 100}, noopObserver{})
	if err != nil {
		t.Fatal(err)
	}
	if err := gate.Load(context.Background(), "source-a", "profile-a"); err != nil {
		t.Fatal(err)
	}
	if gate.State() != RestartFreshnessRequired || !errors.Is(gate.RequireReady(), ErrNotReady) {
		t.Fatalf("missing-floor state=%v ready=%v", gate.State(), gate.RequireReady())
	}
}

func TestRestartFailsClosedOnFloorLossAfterPersistence(t *testing.T) {
	store := NewMemoryGenerationFloorStore(32)
	if err := store.StoreHigher(context.Background(), testFloor(9)); err != nil {
		t.Fatal(err)
	}
	store.mu.Lock()
	delete(store.floors, floorKey{sourceOperator: "source-a", profile: "profile-a"})
	store.mu.Unlock()
	gate, err := NewRestartGate(store, testCheckpointVerifier{}, testClock{now: 100}, noopObserver{})
	if err != nil {
		t.Fatal(err)
	}
	if err := gate.Load(context.Background(), "source-a", "profile-a"); !errors.Is(err, ErrFloorInvalid) || gate.State() != RestartFailClosed {
		t.Fatalf("lost floor load: err=%v state=%v", err, gate.State())
	}
	if _, err := gate.AcceptFresh(context.Background(), freshnessRequest(8), freshnessEvidence(8)); !errors.Is(err, ErrNotReady) {
		t.Fatalf("lost floor accepted rollback: %v", err)
	}
}

func TestRestartDoesNotPublishAtFreshnessExpiryAfterDelayedStore(t *testing.T) {
	store := &raceFloorStore{floor: testFloor(7), storeStarted: make(chan struct{}), releaseStore: make(chan struct{})}
	clock := &mutableRestartClock{now: 100}
	observer := &task4Observer{}
	gate, err := NewRestartGate(store, fixedFreshnessVerifier{freshUntil: 200}, clock, observer)
	if err != nil {
		t.Fatal(err)
	}
	if err := gate.Load(context.Background(), "source-a", "profile-a"); err != nil {
		t.Fatal(err)
	}
	result := make(chan error, 1)
	go func() {
		_, err := gate.AcceptFresh(context.Background(), freshnessRequest(8), freshnessEvidence(8))
		result <- err
	}()
	<-store.storeStarted
	clock.Set(200)
	close(store.releaseStore)
	if err := <-result; !errors.Is(err, ErrStaleFreshness) {
		t.Fatalf("publication at freshness boundary = %v, want ErrStaleFreshness", err)
	}
	if gate.State() != RestartFreshnessRequired || !errors.Is(gate.RequireReady(), ErrNotReady) {
		t.Fatalf("expired publication state=%v ready=%v", gate.State(), gate.RequireReady())
	}
	if got := observer.count(EventRollbackFloorUpdated); got != 0 {
		t.Fatalf("floor updated events = %d, want 0", got)
	}
}

func TestRestartDoesNotPublishAtFreshnessExpiryAfterDelayedVerifier(t *testing.T) {
	clock := &mutableRestartClock{now: 100}
	observer := &task4Observer{}
	verifier := &delayedFreshnessVerifier{freshUntil: 200, started: make(chan struct{}), release: make(chan struct{})}
	gate, err := NewRestartGate(&scriptedFloorStore{load: testFloor(7)}, verifier, clock, observer)
	if err != nil {
		t.Fatal(err)
	}
	if err := gate.Load(context.Background(), "source-a", "profile-a"); err != nil {
		t.Fatal(err)
	}
	result := make(chan error, 1)
	go func() {
		_, err := gate.AcceptFresh(context.Background(), freshnessRequest(8), freshnessEvidence(8))
		result <- err
	}()
	<-verifier.started
	clock.Set(200)
	close(verifier.release)
	if err := <-result; !errors.Is(err, ErrStaleFreshness) {
		t.Fatalf("verifier-boundary publication = %v, want ErrStaleFreshness", err)
	}
	if gate.State() != RestartFreshnessRequired || !errors.Is(gate.RequireReady(), ErrNotReady) {
		t.Fatalf("expired verifier state=%v ready=%v", gate.State(), gate.RequireReady())
	}
	if got := observer.count(EventRollbackFloorUpdated); got != 0 {
		t.Fatalf("floor updated events = %d, want 0", got)
	}
}

func TestRestartDoesNotHoldGateLockDuringVerifierOrStore(t *testing.T) {
	store := &reentrantFloorStore{load: testFloor(7)}
	verifier := &reentrantCheckpointVerifier{}
	gate, err := NewRestartGate(store, verifier, testClock{now: 100}, noopObserver{})
	if err != nil {
		t.Fatal(err)
	}
	store.gate = gate
	verifier.gate = gate
	if err := gate.Load(context.Background(), "source-a", "profile-a"); err != nil {
		t.Fatal(err)
	}
	if _, err := gate.AcceptFresh(context.Background(), freshnessRequest(8), freshnessEvidence(8)); err != nil {
		t.Fatal(err)
	}
}

func TestRestartLoadWinsOverInFlightFreshnessPersistence(t *testing.T) {
	store := &raceFloorStore{floor: testFloor(7), storeStarted: make(chan struct{}), releaseStore: make(chan struct{})}
	gate, err := NewRestartGate(store, testCheckpointVerifier{}, testClock{now: 100}, noopObserver{})
	if err != nil {
		t.Fatal(err)
	}
	if err := gate.Load(context.Background(), "source-a", "profile-a"); err != nil {
		t.Fatal(err)
	}
	result := make(chan error, 1)
	go func() {
		_, err := gate.AcceptFresh(context.Background(), freshnessRequest(8), freshnessEvidence(8))
		result <- err
	}()
	<-store.storeStarted
	if err := gate.Load(context.Background(), "source-a", "profile-a"); err != nil {
		t.Fatal(err)
	}
	close(store.releaseStore)
	if err := <-result; !errors.Is(err, ErrNotReady) {
		t.Fatalf("in-flight freshness result = %v, want ErrNotReady", err)
	}
	if gate.State() != RestartFreshnessRequired || !errors.Is(gate.RequireReady(), ErrNotReady) {
		t.Fatalf("load-lost state=%v ready=%v", gate.State(), gate.RequireReady())
	}
}

func TestNoDurableAPIAcceptsLiveAuthority(t *testing.T) {
	for _, typ := range []reflect.Type{reflect.TypeOf((*GenerationFloorStore)(nil)).Elem(), reflect.TypeOf((*MemoryGenerationFloorStore)(nil))} {
		for index := 0; index < typ.NumMethod(); index++ {
			method := typ.Method(index)
			for parameter := 0; parameter < method.Type.NumIn(); parameter++ {
				got := method.Type.In(parameter)
				for _, forbidden := range []reflect.Type{reflect.TypeOf(ProviderGrant{}), reflect.TypeOf(VerifiedAuthority{}), reflect.TypeOf(Reservation{}), reflect.TypeOf(AuthorityHandle{})} {
					if got == forbidden || (got.Kind() == reflect.Pointer && got.Elem() == forbidden) {
						t.Fatalf("%v consumes live authority %v", method.Name, forbidden)
					}
				}
			}
		}
	}
}

func newGate(t *testing.T, floor SignedGenerationFloor) *RestartGate {
	t.Helper()
	store := &scriptedFloorStore{load: floor}
	gate, err := NewRestartGate(store, testCheckpointVerifier{}, testClock{now: 100}, noopObserver{})
	if err != nil {
		t.Fatal(err)
	}
	return gate
}

type testClock struct{ now uint64 }

func (c testClock) NowUnix() uint64 { return c.now }

type mutableRestartClock struct {
	mu  sync.Mutex
	now uint64
}

func (c *mutableRestartClock) NowUnix() uint64 {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.now
}
func (c *mutableRestartClock) Set(now uint64) {
	c.mu.Lock()
	c.now = now
	c.mu.Unlock()
}

type testCheckpointVerifier struct{}

func (testCheckpointVerifier) VerifyFreshnessEvidence(_ context.Context, freshness ProviderFreshness, request FreshnessRequest, now uint64) (CheckpointClaims, error) {
	if freshness.SourceOperator != request.SourceOperator || freshness.Profile != request.Profile || len(freshness.Evidence) == 0 {
		return CheckpointClaims{}, ErrBindingMismatch
	}
	generation := AuthorityGeneration(freshness.Evidence[0])
	return CheckpointClaims{SourceOperator: request.SourceOperator, Profile: request.Profile, Generation: generation, IssuedAt: now - 1, FreshUntil: now + 100, Digest: testCheckpoint(generation)}, nil
}

type fixedFreshnessVerifier struct{ freshUntil uint64 }

func (v fixedFreshnessVerifier) VerifyFreshnessEvidence(_ context.Context, freshness ProviderFreshness, request FreshnessRequest, now uint64) (CheckpointClaims, error) {
	if freshness.SourceOperator != request.SourceOperator || freshness.Profile != request.Profile || len(freshness.Evidence) == 0 {
		return CheckpointClaims{}, ErrBindingMismatch
	}
	generation := AuthorityGeneration(freshness.Evidence[0])
	return CheckpointClaims{SourceOperator: request.SourceOperator, Profile: request.Profile, Generation: generation, IssuedAt: now - 1, FreshUntil: v.freshUntil, Digest: testCheckpoint(generation)}, nil
}

type delayedFreshnessVerifier struct {
	freshUntil       uint64
	started, release chan struct{}
}

func (v *delayedFreshnessVerifier) VerifyFreshnessEvidence(_ context.Context, freshness ProviderFreshness, request FreshnessRequest, now uint64) (CheckpointClaims, error) {
	if freshness.SourceOperator != request.SourceOperator || freshness.Profile != request.Profile || len(freshness.Evidence) == 0 {
		return CheckpointClaims{}, ErrBindingMismatch
	}
	close(v.started)
	<-v.release
	generation := AuthorityGeneration(freshness.Evidence[0])
	return CheckpointClaims{SourceOperator: request.SourceOperator, Profile: request.Profile, Generation: generation, IssuedAt: now - 1, FreshUntil: v.freshUntil, Digest: testCheckpoint(generation)}, nil
}

func freshnessRequest(generation AuthorityGeneration) FreshnessRequest {
	return FreshnessRequest{SourceOperator: "source-a", Profile: "profile-a", DeviceID: [32]byte{1}, DeviceGeneration: 1, AfterGeneration: generation - 1, AfterCheckpoint: testCheckpoint(generation - 1), DeadlineUnix: 200}
}
func freshnessEvidence(generation AuthorityGeneration) ProviderFreshness {
	return ProviderFreshness{SourceOperator: "source-a", Profile: "profile-a", Evidence: []byte{byte(generation)}}
}

type scriptedFloorStore struct {
	load              SignedGenerationFloor
	loadErr, storeErr error
}

func (s *scriptedFloorStore) Load(context.Context, string, string) (SignedGenerationFloor, error) {
	return s.load, s.loadErr
}
func (s *scriptedFloorStore) StoreHigher(context.Context, SignedGenerationFloor) error {
	return s.storeErr
}

type reentrantFloorStore struct {
	mu   sync.Mutex
	load SignedGenerationFloor
	gate *RestartGate
}

func (s *reentrantFloorStore) Load(context.Context, string, string) (SignedGenerationFloor, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.gate != nil {
		_ = s.gate.State()
	}
	return s.load, nil
}
func (s *reentrantFloorStore) StoreHigher(context.Context, SignedGenerationFloor) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.gate != nil {
		_ = s.gate.State()
	}
	return nil
}

type reentrantCheckpointVerifier struct{ gate *RestartGate }

func (v *reentrantCheckpointVerifier) VerifyFreshnessEvidence(ctx context.Context, freshness ProviderFreshness, request FreshnessRequest, now uint64) (CheckpointClaims, error) {
	if v.gate != nil {
		_ = v.gate.State()
	}
	return testCheckpointVerifier{}.VerifyFreshnessEvidence(ctx, freshness, request, now)
}

type raceFloorStore struct {
	floor        SignedGenerationFloor
	storeStarted chan struct{}
	releaseStore chan struct{}
}

func (s *raceFloorStore) Load(context.Context, string, string) (SignedGenerationFloor, error) {
	return s.floor, nil
}
func (s *raceFloorStore) StoreHigher(context.Context, SignedGenerationFloor) error {
	select {
	case <-s.storeStarted:
	default:
		close(s.storeStarted)
	}
	<-s.releaseStore
	return nil
}
