package authority

import (
	"context"
	"errors"
	"os"
	"strings"
	"testing"
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
	for _, tt := range []struct {
		name  string
		first func(*Manager, VerifiedAuthority, Reservation) error
		want  error
	}{
		{
			name: "invalidation before reservation",
			first: func(m *Manager, authority VerifiedAuthority, _ Reservation) error {
				if err := m.InvalidateGrant(authority.GrantDigest()); err != nil {
					return err
				}
				_, err := m.reserveVerified(authority)
				return err
			},
			want: ErrInvalidAuthority,
		},
		{
			name: "reservation before invalidation",
			first: func(m *Manager, authority VerifiedAuthority, _ Reservation) error {
				reservation, err := m.reserveVerified(authority)
				if err != nil {
					return err
				}
				return m.InvalidateGrant(reservation.grant)
			},
			want: nil,
		},
	} {
		t.Run(tt.name, func(t *testing.T) {
			m := task11Manager(t)
			authority := testAuthority(testKey(1), testGrant(1), 200)
			reservation, err := m.reserveVerified(authority)
			if err != nil {
				t.Fatal(err)
			}
			if err := m.Release(reservation); err != nil {
				t.Fatal(err)
			}
			if err := tt.first(m, authority, Reservation{}); !errors.Is(err, tt.want) {
				t.Fatalf("ordered operation = %v, want %v", err, tt.want)
			}
			if err := m.ValidateInvariants(); err != nil {
				t.Fatalf("invariants: %v", err)
			}
		})
	}
}

func TestConcurrentConsumeAndQuarantineRespectPublishedOrder(t *testing.T) {
	for _, tt := range []struct {
		name  string
		first func(*Manager, Reservation, GenerationSnapshot) error
		want  error
	}{
		{
			name: "consume before quarantine",
			first: func(m *Manager, reservation Reservation, snapshot GenerationSnapshot) error {
				if _, err := m.Consume(reservation, owner(reservation.key.TSGeneration), snapshot, 99); err != nil {
					return err
				}
				return m.Quarantine(reservation, RequestID{9})
			},
			want: ErrInvalidTransition,
		},
		{
			name: "quarantine before consume",
			first: func(m *Manager, reservation Reservation, snapshot GenerationSnapshot) error {
				if err := m.Quarantine(reservation, RequestID{9}); err != nil {
					return err
				}
				_, err := m.Consume(reservation, owner(reservation.key.TSGeneration), snapshot, 99)
				return err
			},
			want: ErrInvalidTransition,
		},
	} {
		t.Run(tt.name, func(t *testing.T) {
			m, reservation, snapshot := task11ReservedGrant(t)
			if err := tt.first(m, reservation, snapshot); !errors.Is(err, tt.want) {
				t.Fatalf("ordered operation = %v, want %v", err, tt.want)
			}
			if err := m.ValidateInvariants(); err != nil {
				t.Fatalf("invariants: %v", err)
			}
		})
	}
}

func TestConcurrentCancelAndProviderCompletionRespectPublishedOrder(t *testing.T) {
	t.Run("cancellation before completion quarantines provider result", func(t *testing.T) {
		provider, m, request := coalesceFixture(t)
		completed := make(chan struct{}, 1)
		m.observer = observerFunc(func(event Event) {
			if event.Kind == EventAcquireResult {
				completed <- struct{}{}
			}
		})
		ctx, cancel := context.WithCancel(context.Background())
		result := make(chan error, 1)
		go func() { _, err := m.Acquire(ctx, request); result <- err }()
		<-provider.started
		cancel()
		if err := <-result; !errors.Is(err, context.Canceled) {
			t.Fatalf("Acquire after cancellation = %v, want context.Canceled", err)
		}
		<-provider.contextDone
		<-completed
		provider.releaseOnce()
		if err := m.ValidateInvariants(); err != nil {
			t.Fatalf("invariants after cancellation: %v", err)
		}
	})

	t.Run("completion before cancellation preserves completed result", func(t *testing.T) {
		provider, m, request := coalesceFixture(t)
		ctx, cancel := context.WithCancel(context.Background())
		result := make(chan error, 1)
		go func() { _, err := m.Acquire(ctx, request); result <- err }()
		<-provider.started
		provider.releaseOnce()
		if err := <-result; err != nil {
			t.Fatalf("Acquire before cancellation: %v", err)
		}
		cancel()
		if err := m.ValidateInvariants(); err != nil {
			t.Fatalf("invariants after completion: %v", err)
		}
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
	m.checkpoint = checkpointState{claims: CheckpointClaims{SourceOperator: "source-operator", Profile: "profile", Generation: 7, FreshUntil: 300, Digest: nonZeroCheckpoint()}}
	m.generation, m.hasCheckpoint = 7, true
	m.mu.Unlock()
	return m
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
