package authority

import (
	"context"
	"errors"
	"os"
	"strings"
	"testing"

	"nbsr.local/client/nbsr-go-client/internal/identity"
)

func TestPackageDocumentationStatesLocalOnlyBaselineBoundaries(t *testing.T) {
	tests := []struct {
		path     string
		required []string
	}{
		{
			path: "doc.go",
			required: []string{
				"local-only authority-provider boundary",
				"remote authority service",
				"BASELINE ONLY — NOT ACCEPTANCE CAPACITY",
				"no provider calls, I/O, or wire parsing",
			},
		},
		{
			path: "../identity/doc.go",
			required: []string{
				"local identity metadata",
				"protocol-wire, or OS",
				"keystore operations",
				"no authority-provider operations",
			},
		},
		{
			path: "../retry/doc.go",
			required: []string{
				"local retry decisions",
				"no I/O, starts no goroutines, sleeps never",
				"authority-provider operations",
			},
		},
	}
	for _, tt := range tests {
		t.Run(tt.path, func(t *testing.T) {
			body, err := os.ReadFile(tt.path)
			if err != nil {
				t.Fatal(err)
			}
			for _, required := range tt.required {
				if !strings.Contains(string(body), required) {
					t.Fatalf("%s does not state %q", tt.path, required)
				}
			}
		})
	}
}

func TestGenerationAdvanceLinearizesBeforeConsume(t *testing.T) {
	t.Run("consume before publication remains valid", func(t *testing.T) {
		m, reservation, snapshot := task11ReservedGrant(t)
		verifier := &task4DelayedCheckpointVerifier{claims: task11Checkpoint(8), started: make(chan struct{}), release: make(chan struct{})}
		m.checkpointVerifier = verifier
		published := make(chan error, 1)
		go func() {
			_, err := m.PublishFreshness(context.Background(), task11FreshnessRequest(), task11ProviderFreshness())
			published <- err
		}()
		<-verifier.started
		if _, err := m.Consume(reservation, owner(reservation.key.TSGeneration), snapshot, 99); err != nil {
			t.Fatalf("Consume before generation publication: %v", err)
		}
		close(verifier.release)
		if err := <-published; err != nil {
			t.Fatalf("PublishFreshness: %v", err)
		}
	})

	t.Run("publication before consume rejects stale reservation", func(t *testing.T) {
		m, reservation, snapshot := task11ReservedGrant(t)
		observer := &task11BlockingGenerationObserver{seen: make(chan struct{}), release: make(chan struct{})}
		m.observer = observer
		m.checkpointVerifier = &task4CheckpointVerifier{claims: task11Checkpoint(8)}
		published := make(chan error, 1)
		go func() {
			_, err := m.PublishFreshness(context.Background(), task11FreshnessRequest(), task11ProviderFreshness())
			published <- err
		}()
		<-observer.seen
		_, consumeErr := m.Consume(reservation, owner(reservation.key.TSGeneration), snapshot, 99)
		close(observer.release)
		if err := <-published; err != nil {
			t.Fatalf("PublishFreshness: %v", err)
		}
		if !errors.Is(consumeErr, ErrStaleGeneration) {
			t.Fatalf("Consume after generation publication = %v, want ErrStaleGeneration", consumeErr)
		}
	})
}

func TestConcurrentInvalidateAndReserveRespectPublishedOrder(t *testing.T) {
	t.Run("invalidation linearizes before reserve", func(t *testing.T) {
		m, authority := task11AvailableGrant(t, task11BarrierClock{})
		clock := &task11BarrierClock{now: 99, entered: make(chan struct{}), release: make(chan struct{})}
		m.clock = clock
		reserved := make(chan error, 1)
		invalidated := make(chan error, 1)
		go func() { _, err := m.reserveVerified(authority); reserved <- err }()
		<-clock.entered
		go func() { invalidated <- m.InvalidateGrant(authority.GrantDigest()) }()
		if err := <-invalidated; err != nil {
			t.Fatalf("InvalidateGrant: %v", err)
		}
		close(clock.release)
		if err := <-reserved; !errors.Is(err, ErrInvalidAuthority) {
			t.Fatalf("reserve after invalidation = %v, want ErrInvalidAuthority", err)
		}
		task11RequireInvariants(t, m)
	})

	t.Run("reserve linearizes before invalidation", func(t *testing.T) {
		m, authority := task11AvailableGrant(t, task11BarrierClock{})
		entered := make(chan struct{})
		release := make(chan struct{})
		m.observer = task11BlockingEventObserver{kind: EventCacheHit, entered: entered, release: release}
		reserved := make(chan Reservation, 1)
		reserveErr := make(chan error, 1)
		invalidated := make(chan error, 1)
		go func() { reservation, err := m.reserveVerified(authority); reserved <- reservation; reserveErr <- err }()
		<-entered
		go func() { invalidated <- m.InvalidateGrant(authority.GrantDigest()) }()
		if err := <-invalidated; err != nil {
			t.Fatalf("InvalidateGrant: %v", err)
		}
		close(release)
		reservation := <-reserved
		if err := <-reserveErr; err != nil {
			t.Fatalf("reserve before invalidation: %v", err)
		}
		if err := m.ValidateForNewWork(reservation, GenerationSnapshot{generation: 7}, 99); !errors.Is(err, ErrInvalidAuthority) {
			t.Fatalf("reservation after invalidation = %v, want ErrInvalidAuthority", err)
		}
		task11RequireInvariants(t, m)
	})
}

func TestConcurrentConsumeAndQuarantineRespectPublishedOrder(t *testing.T) {
	t.Run("consume linearizes before quarantine", func(t *testing.T) {
		m, reservation, snapshot := task11ReservedGrant(t)
		linearized := make(chan struct{})
		release := make(chan struct{})
		quarantineStarted := make(chan struct{})
		consumed := make(chan error, 1)
		quarantined := make(chan error, 1)
		go func() {
			consumed <- task11ConsumeLockedBarrier(m, reservation, owner(reservation.key.TSGeneration), snapshot, 99, linearized, release)
		}()
		<-linearized
		go func() {
			quarantined <- task11QuarantineBlockedAfterStart(m, reservation, RequestID{9}, quarantineStarted)
		}()
		<-quarantineStarted
		select {
		case err := <-quarantined:
			t.Fatalf("Quarantine completed while Consume held Manager.mu: %v", err)
		default:
		}
		close(release)
		if err := <-consumed; err != nil {
			t.Fatalf("Consume: %v", err)
		}
		if err := <-quarantined; !errors.Is(err, ErrInvalidTransition) {
			t.Fatalf("Quarantine after Consume = %v, want ErrInvalidTransition", err)
		}
		task11RequireInvariants(t, m)
	})

	t.Run("quarantine linearizes before consume", func(t *testing.T) {
		m, reservation, snapshot := task11ReservedGrant(t)
		linearized := make(chan struct{})
		release := make(chan struct{})
		consumeStarted := make(chan struct{})
		quarantined := make(chan error, 1)
		consumed := make(chan error, 1)
		go func() {
			quarantined <- task11QuarantineLockedBarrier(m, reservation, RequestID{9}, linearized, release)
		}()
		<-linearized
		go func() {
			consumed <- task11ConsumeBlockedAfterStart(m, reservation, owner(reservation.key.TSGeneration), snapshot, 99, consumeStarted)
		}()
		<-consumeStarted
		select {
		case err := <-consumed:
			t.Fatalf("Consume completed while Quarantine held Manager.mu: %v", err)
		default:
		}
		close(release)
		if err := <-consumed; !errors.Is(err, ErrInvalidTransition) {
			t.Fatalf("Consume after Quarantine = %v, want ErrInvalidTransition", err)
		}
		if err := <-quarantined; err != nil {
			t.Fatalf("Quarantine: %v", err)
		}
		task11RequireInvariants(t, m)
	})
}

func TestConcurrentCancelAndProviderCompletionRespectPublishedOrder(t *testing.T) {
	t.Run("caller cancellation before remote candidate completion quarantines authority", func(t *testing.T) {
		provider, m, request := task11RemoteCompletionFixture(t)
		completed := task11CompletionBarrier(m, EventAcquireResult)
		ctx, cancel := context.WithCancel(context.Background())
		result := make(chan error, 1)
		go func() { _, err := m.Acquire(ctx, request); result <- err }()
		<-provider.started
		cancel()
		if err := <-result; !errors.Is(err, context.Canceled) {
			t.Fatalf("Acquire after cancellation = %v, want context.Canceled", err)
		}
		<-provider.canceled
		provider.Complete()
		<-completed
		task11AssertAmbiguousRemoteCompletion(t, m, request)
	})

	t.Run("remote candidate completion before caller cancellation preserves reservation", func(t *testing.T) {
		provider, m, request := task11RemoteCompletionFixture(t)
		completed := task11CompletionBarrier(m, EventAcquireResult)
		ctx, cancel := context.WithCancel(context.Background())
		result := make(chan acquireResult, 1)
		go func() {
			reservation, err := m.Acquire(ctx, request)
			result <- acquireResult{reservation: reservation, err: err}
		}()
		<-provider.started
		provider.Complete()
		<-completed
		got := <-result
		if got.err != nil || got.reservation.id == 0 {
			t.Fatalf("Acquire before cancellation = %#v, want live reservation", got)
		}
		cancel()
		if snapshot, err := m.RequestRecordSnapshot(request.RequestID); err != nil || snapshot.Status != RequestComplete {
			t.Fatalf("completed request snapshot = %#v, %v; want RequestComplete", snapshot, err)
		}
		task11RequireInvariants(t, m)
	})
}

func TestConcurrentCloseAndAcquireRespectPublishedOrder(t *testing.T) {
	t.Run("close before acquire rejects without provider work", func(t *testing.T) {
		provider, m, request := coalesceFixture(t)
		if err := m.Close(); err != nil {
			t.Fatal(err)
		}
		if _, err := m.Acquire(context.Background(), request); !errors.Is(err, ErrClosed) {
			t.Fatalf("Acquire after Close = %v, want ErrClosed", err)
		}
		if calls := provider.calls(); calls != 0 {
			t.Fatalf("provider calls after Close = %d, want 0", calls)
		}
	})

	t.Run("acquire before close wakes waiter closed", func(t *testing.T) {
		provider, m, request := coalesceFixture(t)
		result := make(chan error, 1)
		go func() { _, err := m.Acquire(context.Background(), request); result <- err }()
		<-provider.started
		if err := m.Close(); err != nil {
			t.Fatal(err)
		}
		if err := <-result; !errors.Is(err, ErrClosed) {
			t.Fatalf("pending Acquire after Close = %v, want ErrClosed", err)
		}
		provider.releaseOnce()
	})
}

func TestFloorStoreCompletesBeforeFreshPublication(t *testing.T) {
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
	if state := gate.State(); state != RestartFreshnessRequired {
		t.Fatalf("state while StoreHigher is pending = %v, want RestartFreshnessRequired", state)
	}
	close(store.releaseStore)
	if err := <-result; err != nil {
		t.Fatalf("AcceptFresh after StoreHigher: %v", err)
	}
	if state := gate.State(); state != RestartReady {
		t.Fatalf("state after StoreHigher = %v, want RestartReady", state)
	}
}

func TestFreshPublicationRejectsNewerLoadAfterFloorStore(t *testing.T) {
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
		t.Fatalf("AcceptFresh after new Load = %v, want ErrNotReady", err)
	}
	if state := gate.State(); state != RestartFreshnessRequired {
		t.Fatalf("state after newer Load = %v, want RestartFreshnessRequired", state)
	}
}

func task11ReservedGrant(t *testing.T) (*Manager, Reservation, GenerationSnapshot) {
	t.Helper()
	m := task11Manager(t)
	key := testKey(1)
	reservation, err := m.reserveVerified(testAuthority(key, testGrant(1), 200))
	if err != nil {
		t.Fatal(err)
	}
	return m, reservation, GenerationSnapshot{generation: key.AuthorityGeneration}
}

func task11Checkpoint(generation AuthorityGeneration) CheckpointClaims {
	return CheckpointClaims{SourceOperator: "source-operator", Profile: "profile", Generation: generation, IssuedAt: 110, FreshUntil: 210, Digest: CheckpointDigest{byte(generation)}}
}

func task11FreshnessRequest() FreshnessRequest {
	return FreshnessRequest{SourceOperator: "source-operator", Profile: "profile", DeviceID: testKey(1).DeviceID, DeviceGeneration: 1, DeadlineUnix: 300}
}

func task11ProviderFreshness() ProviderFreshness {
	return ProviderFreshness{SourceOperator: "source-operator", Profile: "profile", Evidence: []byte{1}}
}

func task11Manager(t testing.TB) *Manager {
	t.Helper()
	limits := validLimits()
	limits.MaxCacheEntries, limits.MaxPending, limits.MaxWaitersPerPending, limits.MaxRequestRecords = 8, 4, 8, 8
	limits.MaxCacheBytes, limits.MaxPendingBytes, limits.MaxRequestBytes = 1<<20, 1<<20, 1<<20
	m, err := NewManager(limits, fakeClock{}, fakeProvider{}, &Verifier{}, fakeCheckpointVerifier{}, fakeFloorStore{}, noopObserver{})
	if err != nil {
		t.Fatal(err)
	}
	m.mu.Lock()
	m.checkpoint = mustSealCheckpointForTest(t, CheckpointClaims{SourceOperator: "source-operator", Profile: "profile", Generation: 7, IssuedAt: 1, FreshUntil: 300, Digest: nonZeroCheckpoint()})
	m.generation, m.hasCheckpoint = 7, true
	m.mu.Unlock()
	return m
}

func task11AvailableGrant(t *testing.T, _ Clock) (*Manager, VerifiedAuthority) {
	t.Helper()
	m := task11Manager(t)
	authority := testAuthority(testKey(1), testGrant(1), 200)
	reservation, err := m.reserveVerified(authority)
	if err != nil {
		t.Fatal(err)
	}
	if err := m.Release(reservation); err != nil {
		t.Fatal(err)
	}
	return m, authority
}

func task11RequireInvariants(t *testing.T, m *Manager) {
	t.Helper()
	if err := m.ValidateInvariants(); err != nil {
		t.Fatalf("invariants: %v", err)
	}
}

// task11ConsumeLockedBarrier is a same-package test seam for Consume's locked
// transition. It holds Manager.mu only after the real validation and terminal
// state change have linearized, so a competing public Quarantine call is
// deterministically blocked at the same mutex.
func task11ConsumeLockedBarrier(m *Manager, reservation Reservation, owner AdmissionOwner, snapshot GenerationSnapshot, now uint64, linearized chan<- struct{}, release <-chan struct{}) error {
	m.mu.Lock()
	events, err := m.validateReservedLocked(reservation, snapshot, now)
	if err == nil {
		entry := m.reserved[reservation.id]
		if owner.TSGeneration != reservation.key.TSGeneration {
			err = ErrBindingMismatch
		} else if owner.ChannelID == ([16]byte{}) {
			err = ErrInvalidAuthority
		} else {
			m.retireEntryLocked(entry, cacheConsumed)
		}
	}
	close(linearized)
	<-release
	m.mu.Unlock()
	m.notify(events)
	return err
}

// task11QuarantineLockedBarrier is the matching same-package seam for the
// quarantine transition. It does not alter production behavior or APIs.
func task11QuarantineLockedBarrier(m *Manager, reservation Reservation, request RequestID, linearized chan<- struct{}, release <-chan struct{}) error {
	m.mu.Lock()
	entry, found := m.reserved[reservation.id]
	var err error
	if !found {
		if _, terminal := m.tombstones[reservation.grant]; terminal {
			err = ErrInvalidTransition
		} else {
			err = ErrInvalidAuthority
		}
	} else if reservation.id == 0 || entry.reservation != reservation.id || entry.authority.Key() != reservation.key || entry.authority.GrantDigest() != reservation.grant || entry.state != cacheReserved {
		err = ErrInvalidAuthority
	} else {
		m.retireEntryLocked(entry, cacheQuarantined)
	}
	close(linearized)
	<-release
	m.mu.Unlock()
	if err == nil {
		m.notify([]Event{{Kind: EventAmbiguousQuarantine, Result: CodeRequestAmbiguous}})
	}
	return err
}

func task11QuarantineBlockedAfterStart(m *Manager, reservation Reservation, request RequestID, started chan<- struct{}) error {
	close(started)
	return m.Quarantine(reservation, request)
}

func task11ConsumeBlockedAfterStart(m *Manager, reservation Reservation, owner AdmissionOwner, snapshot GenerationSnapshot, now uint64, started chan<- struct{}) error {
	close(started)
	_, err := m.Consume(reservation, owner, snapshot, now)
	return err
}

type task11BarrierClock struct {
	now     uint64
	entered chan struct{}
	release chan struct{}
}

func (clock task11BarrierClock) NowUnix() uint64 {
	if clock.entered != nil {
		close(clock.entered)
		<-clock.release
	}
	if clock.now == 0 {
		return 99
	}
	return clock.now
}

type task11BlockingEventObserver struct {
	kind    EventKind
	entered chan struct{}
	release chan struct{}
}

func (observer task11BlockingEventObserver) Observe(event Event) {
	if event.Kind != observer.kind {
		return
	}
	close(observer.entered)
	<-observer.release
}

type task11RemoteCompletionProvider struct {
	candidate ProviderGrant
	started   chan struct{}
	canceled  chan struct{}
	release   chan struct{}
}

func (provider *task11RemoteCompletionProvider) Acquire(ctx context.Context, _ AcquireRequest) (ProviderGrant, error) {
	close(provider.started)
	select {
	case <-provider.release:
		return provider.candidate, nil
	case <-ctx.Done():
		close(provider.canceled)
		<-provider.release
		return provider.candidate, nil
	}
}

func (provider *task11RemoteCompletionProvider) Renew(context.Context, RenewRequest) (ProviderGrant, error) {
	return ProviderGrant{}, ErrProviderUnavailable
}

func (provider *task11RemoteCompletionProvider) Freshness(context.Context, FreshnessRequest) (ProviderFreshness, error) {
	return ProviderFreshness{}, ErrProviderUnavailable
}

func (provider *task11RemoteCompletionProvider) Close() error { return nil }
func (provider *task11RemoteCompletionProvider) Complete()    { close(provider.release) }

func task11RemoteCompletionFixture(t *testing.T) (*task11RemoteCompletionProvider, *Manager, AcquireRequest) {
	t.Helper()
	grant, verification, resolver := validFrozenGrantCase(t)
	provider := &task11RemoteCompletionProvider{candidate: grant, started: make(chan struct{}), canceled: make(chan struct{}), release: make(chan struct{})}
	limits := validLimits()
	limits.MaxCacheEntries, limits.MaxPending, limits.MaxWaitersPerPending, limits.MaxRequestRecords = 8, 4, 8, 8
	limits.MaxCacheBytes, limits.MaxPendingBytes, limits.MaxRequestBytes, limits.MaxGrantBytes = 1<<20, 1<<20, 1<<20, 1<<20
	m, err := NewManager(limits, task4Clock{now: verification.NowUnix}, provider, mustVerifier(t, resolver), fakeCheckpointVerifier{}, fakeFloorStore{}, noopObserver{})
	if err != nil {
		t.Fatal(err)
	}
	m.checkpoint = verification.Checkpoint
	m.generation, m.hasCheckpoint = verification.Checkpoint.Generation(), true
	request := AcquireRequest{Key: verification.Key, Intent: verification.Intent, Device: identity.DeviceIdentity{ID: verification.Key.DeviceID, SourceOperatorID: verification.Key.SourceOperator, CredentialGeneration: verification.Key.DeviceGeneration}, RequestID: RequestID{11}, DeadlineUnix: verification.NowUnix + 1}
	return provider, m, request
}

func task11CompletionBarrier(m *Manager, kind EventKind) <-chan struct{} {
	completed := make(chan struct{})
	m.observer = observerFunc(func(event Event) {
		if event.Kind == kind {
			close(completed)
		}
	})
	return completed
}

func task11AssertAmbiguousRemoteCompletion(t *testing.T, m *Manager, request AcquireRequest) {
	t.Helper()
	if snapshot, err := m.RequestRecordSnapshot(request.RequestID); err != nil || snapshot.Status != RequestAmbiguous {
		t.Fatalf("ambiguous request snapshot = %#v, %v; want RequestAmbiguous", snapshot, err)
	}
	if _, err := m.Acquire(context.Background(), request); !errors.Is(err, ErrRequestAmbiguous) {
		t.Fatalf("reused ambiguous request = %v, want ErrRequestAmbiguous", err)
	}
	usage := m.Usage()
	if usage.CacheEntries != 0 || usage.PendingCalls != 0 || usage.PendingWaiters != 0 || usage.RequestRecords != 1 {
		t.Fatalf("remote completion retained usable state: %+v", usage)
	}
	task11RequireInvariants(t, m)
}

type task11BlockingGenerationObserver struct {
	seen    chan struct{}
	release chan struct{}
}

func (observer *task11BlockingGenerationObserver) Observe(event Event) {
	if event.Kind != EventGenerationAdvanced {
		return
	}
	close(observer.seen)
	<-observer.release
}
