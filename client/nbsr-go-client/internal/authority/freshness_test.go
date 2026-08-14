package authority

import (
	"context"
	"errors"
	"sync"
	"testing"
)

func TestFreshnessExpiresAtExactBoundary(t *testing.T) {
	m := freshManager(t, checkpoint(7, 100, 200))
	if err := m.requireFreshLockedForTest(199); err != nil {
		t.Fatal(err)
	}
	if err := m.requireFreshLockedForTest(200); !errors.Is(err, ErrStaleFreshness) {
		t.Fatalf("boundary error = %v, want ErrStaleFreshness", err)
	}
}

func TestFreshnessRejectsMismatchedOrMalformedClaims(t *testing.T) {
	m := freshManager(t, checkpoint(7, 100, 200))
	verifier := m.checkpointVerifier.(*task4CheckpointVerifier)
	verifier.claims.SourceOperator = "other.operator"
	if _, err := m.PublishFreshness(context.Background(), task4Request(), task4ProviderFreshness()); !errors.Is(err, ErrBindingMismatch) {
		t.Fatalf("operator error = %v, want ErrBindingMismatch", err)
	}
	verifier.claims = checkpoint(8, 100, 200)
	verifier.claims.Profile = "other.profile"
	if _, err := m.PublishFreshness(context.Background(), task4Request(), task4ProviderFreshness()); !errors.Is(err, ErrBindingMismatch) {
		t.Fatalf("profile error = %v, want ErrBindingMismatch", err)
	}

	verifier.claims = checkpoint(8, 100, 200)
	verifier.claims.FreshUntil = verifier.claims.IssuedAt
	if _, err := m.PublishFreshness(context.Background(), task4Request(), task4ProviderFreshness()); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("malformed error = %v, want ErrInvalidAuthority", err)
	}
	verifier.err = ErrSignatureFailure
	if _, err := m.PublishFreshness(context.Background(), task4Request(), task4ProviderFreshness()); !errors.Is(err, ErrSignatureFailure) {
		t.Fatalf("unverified error = %v, want ErrSignatureFailure", err)
	}
}

func TestFreshnessExpirationEventEmittedOnce(t *testing.T) {
	m := freshManager(t, checkpoint(7, 100, 200))
	observer := m.observer.(*task4Observer)
	for range 2 {
		if err := m.requireFreshLockedForTest(200); !errors.Is(err, ErrStaleFreshness) {
			t.Fatalf("expiry error = %v, want ErrStaleFreshness", err)
		}
	}
	if got := observer.count(EventFreshnessExpired); got != 1 {
		t.Fatalf("expired events = %d, want 1", got)
	}
}

func TestFreshnessRechecksClockAfterDelayedVerification(t *testing.T) {
	m := freshManager(t, checkpoint(7, 100, 200))
	clock := &task4MutableClock{now: 150}
	verifier := &task4DelayedCheckpointVerifier{
		claims:  checkpoint(8, 110, 200),
		started: make(chan struct{}),
		release: make(chan struct{}),
	}
	observer := &task4Observer{}
	m.clock = clock
	m.checkpointVerifier = verifier
	m.observer = observer

	result := make(chan error, 1)
	go func() {
		_, err := m.PublishFreshness(context.Background(), task4Request(), task4ProviderFreshness())
		result <- err
	}()
	<-verifier.started
	clock.Set(200)
	close(verifier.release)
	if err := <-result; !errors.Is(err, ErrStaleFreshness) {
		t.Fatalf("publication error = %v, want ErrStaleFreshness", err)
	}
	if m.generation != 7 {
		t.Fatalf("generation = %d, want 7", m.generation)
	}
	if got := observer.count(EventFreshnessAccepted); got != 0 {
		t.Fatalf("accepted events = %d, want 0", got)
	}
	if got := observer.count(EventGenerationAdvanced); got != 0 {
		t.Fatalf("advanced events = %d, want 0", got)
	}
}

func TestFreshnessStateCopiesAndCanonicalizesRevocations(t *testing.T) {
	claims := checkpoint(7, 100, 200)
	claims.RevokedGrants = []RouteGrantDigest{{3}, {1}, {3}, {2}}
	limits := validLimits()
	limits.MaxCacheEntries = 3
	m := freshManagerWithLimits(t, limits, claims)
	claims.RevokedGrants[0][0] = 9
	if got, want := m.checkpoint.revoked, []RouteGrantDigest{{1}, {2}, {3}}; !sameRevocations(got, want) {
		t.Fatalf("revocations = %v, want %v", got, want)
	}
}

func TestFreshnessRejectsRevocationSetOverConfiguredBound(t *testing.T) {
	claims := checkpoint(7, 100, 200)
	claims.RevokedGrants = []RouteGrantDigest{{1}, {2}, {3}}
	m := freshManagerWithLimits(t, validLimits(), claims)
	if m.hasCheckpoint {
		t.Fatal("over-limit initial checkpoint accepted")
	}
}

func TestNoProviderCallForLocalFreshnessAndGenerationChecks(t *testing.T) {
	m := freshManager(t, checkpoint(7, 100, 200))
	provider := m.provider.(*task4CountingProvider)
	snapshot, err := m.CaptureGeneration()
	if err != nil {
		t.Fatal(err)
	}
	for range 10_000 {
		if err := m.ValidateStillCurrent(snapshot); err != nil {
			t.Fatal(err)
		}
	}
	if got := provider.calls(); got != 0 {
		t.Fatalf("provider calls = %d, want 0", got)
	}
}

func (m *Manager) requireFreshLockedForTest(now uint64) error {
	m.mu.Lock()
	events, err := m.requireFreshLocked(now)
	m.mu.Unlock()
	m.notify(events)
	return err
}

type task4Clock struct{ now uint64 }

func (clock task4Clock) NowUnix() uint64 { return clock.now }

type task4MutableClock struct {
	mu  sync.Mutex
	now uint64
}

func (clock *task4MutableClock) NowUnix() uint64 {
	clock.mu.Lock()
	defer clock.mu.Unlock()
	return clock.now
}
func (clock *task4MutableClock) Set(now uint64) {
	clock.mu.Lock()
	clock.now = now
	clock.mu.Unlock()
}

type task4CheckpointVerifier struct {
	claims CheckpointClaims
	err    error
}

func (verifier *task4CheckpointVerifier) VerifyFreshnessEvidence(_ context.Context, _ ProviderFreshness, _ FreshnessRequest, _ uint64) (CheckpointClaims, error) {
	return verifier.claims, verifier.err
}

type task4DelayedCheckpointVerifier struct {
	claims  CheckpointClaims
	started chan struct{}
	release chan struct{}
}

func (verifier *task4DelayedCheckpointVerifier) VerifyFreshnessEvidence(_ context.Context, _ ProviderFreshness, _ FreshnessRequest, _ uint64) (CheckpointClaims, error) {
	close(verifier.started)
	<-verifier.release
	return verifier.claims, nil
}

type task4CountingProvider struct {
	mu    sync.Mutex
	count int
}

func (provider *task4CountingProvider) Acquire(context.Context, AcquireRequest) (ProviderGrant, error) {
	provider.record()
	return ProviderGrant{}, ErrProviderUnavailable
}
func (provider *task4CountingProvider) Renew(context.Context, RenewRequest) (ProviderGrant, error) {
	provider.record()
	return ProviderGrant{}, ErrProviderUnavailable
}
func (provider *task4CountingProvider) Freshness(context.Context, FreshnessRequest) (ProviderFreshness, error) {
	provider.record()
	return ProviderFreshness{}, ErrProviderUnavailable
}
func (provider *task4CountingProvider) Close() error { return nil }
func (provider *task4CountingProvider) record() {
	provider.mu.Lock()
	provider.count++
	provider.mu.Unlock()
}
func (provider *task4CountingProvider) calls() int {
	provider.mu.Lock()
	defer provider.mu.Unlock()
	return provider.count
}

type task4Observer struct {
	mu     sync.Mutex
	events []Event
}

func (observer *task4Observer) Observe(event Event) {
	observer.mu.Lock()
	observer.events = append(observer.events, event)
	observer.mu.Unlock()
}
func (observer *task4Observer) count(kind EventKind) int {
	observer.mu.Lock()
	defer observer.mu.Unlock()
	count := 0
	for _, event := range observer.events {
		if event.Kind == kind {
			count++
		}
	}
	return count
}

func freshManager(t *testing.T, claims CheckpointClaims) *Manager {
	t.Helper()
	return freshManagerWithLimits(t, validLimits(), claims)
}

func freshManagerWithLimits(t *testing.T, limits Limits, claims CheckpointClaims) *Manager {
	t.Helper()
	provider := &task4CountingProvider{}
	observer := &task4Observer{}
	verifier := &task4CheckpointVerifier{claims: claims}
	m, err := NewManager(limits, task4Clock{now: 150}, provider, &Verifier{}, verifier, fakeFloorStore{}, observer)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := m.PublishFreshness(context.Background(), task4Request(), task4ProviderFreshness()); err != nil && len(claims.RevokedGrants) <= limits.MaxCacheEntries {
		t.Fatal(err)
	}
	return m
}

func checkpoint(generation, issued, freshUntil uint64) CheckpointClaims {
	return CheckpointClaims{SourceOperator: "source.operator", Profile: "profile", Generation: AuthorityGeneration(generation), IssuedAt: issued, FreshUntil: freshUntil, Digest: CheckpointDigest{byte(generation)}}
}

func task4Request() FreshnessRequest {
	return FreshnessRequest{SourceOperator: "source.operator", Profile: "profile", DeviceID: [32]byte{1}, DeviceGeneration: 1, DeadlineUnix: 300}
}

func task4ProviderFreshness() ProviderFreshness {
	return ProviderFreshness{SourceOperator: "source.operator", Profile: "profile", Evidence: []byte{1}}
}

func sameRevocations(left, right []RouteGrantDigest) bool {
	if len(left) != len(right) {
		return false
	}
	for index := range left {
		if left[index] != right[index] {
			return false
		}
	}
	return true
}
