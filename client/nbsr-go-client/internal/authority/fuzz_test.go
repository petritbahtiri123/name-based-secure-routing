package authority

import (
	"context"
	"errors"
	"sync"
	"testing"

	"nbsr.local/client/nbsr-go-client/internal/identity"
)

func FuzzAuthorityLifecycle(f *testing.F) {
	f.Add([]byte{0, 1, 2, 3, 4, 5, 6, 7})
	f.Add([]byte{7, 6, 5, 4, 3, 2, 1, 0})
	f.Fuzz(func(t *testing.T, ops []byte) {
		if len(ops) > 256 {
			ops = ops[:256]
		}
		provider, m, request := task11FuzzManager(t)
		for index, op := range ops {
			request.RequestID = task11FuzzRequestID(index, op)
			var err error
			switch op & 7 {
			case 0:
				_, err = m.Acquire(context.Background(), request)
			case 1:
				_, err = m.Acquire(context.Background(), request)
			case 2:
				_, err = m.Renew(context.Background(), RenewRequest{AcquireRequest: request, PreviousGrant: testGrant(250)})
			case 3:
				err = task11FuzzCoalesce(m, provider, request)
			case 4:
				_, err = m.RequestRecordSnapshot(request.RequestID)
			case 5:
				_, err = m.CaptureGeneration()
			case 6:
				err = m.ValidateStillCurrent(GenerationSnapshot{generation: request.Key.AuthorityGeneration})
			case 7:
				_, err = m.InvalidateOlderThan(request.Key.AuthorityGeneration)
			}
			if err != nil && !task11TypedAuthorityError(err) {
				t.Fatalf("operation %d (opcode %d) returned undocumented error %T: %v", index, op&7, err, err)
			}
			if err := m.ValidateInvariants(); err != nil {
				t.Fatalf("operation %d invariants: %v", index, err)
			}
			usage := m.Usage()
			if usage.CacheEntries > 8 || usage.PendingCalls > 4 || usage.RequestRecords > 8 || usage.PendingWaiters > 8 || usage.CacheBytes > m.limits.MaxCacheBytes || usage.PendingBytes > m.limits.MaxPendingBytes || usage.RequestBytes > m.limits.MaxRequestBytes {
				t.Fatalf("operation %d exceeded bounded state: %+v", index, usage)
			}
		}
	})
}

func task11TypedAuthorityError(err error) bool {
	var typed *AuthorityError
	return errors.As(err, &typed) && typed != nil
}

type task11FuzzProvider struct {
	mu      sync.Mutex
	grant   ProviderGrant
	started chan struct{}
	release chan struct{}
}

func (provider *task11FuzzProvider) Acquire(context.Context, AcquireRequest) (ProviderGrant, error) {
	return provider.grantOrBarrier()
}

func (provider *task11FuzzProvider) Renew(context.Context, RenewRequest) (ProviderGrant, error) {
	return provider.grantOrBarrier()
}

func (provider *task11FuzzProvider) Freshness(context.Context, FreshnessRequest) (ProviderFreshness, error) {
	return ProviderFreshness{}, ErrProviderUnavailable
}

func (provider *task11FuzzProvider) Close() error { return nil }

func (provider *task11FuzzProvider) grantOrBarrier() (ProviderGrant, error) {
	provider.mu.Lock()
	started, release := provider.started, provider.release
	provider.mu.Unlock()
	if release != nil {
		close(started)
		<-release
		provider.mu.Lock()
		provider.started, provider.release = nil, nil
		provider.mu.Unlock()
	}
	return provider.grant, nil
}

func (provider *task11FuzzProvider) armCoalesce() <-chan struct{} {
	provider.mu.Lock()
	defer provider.mu.Unlock()
	if provider.release != nil {
		panic("coalesce barrier already armed")
	}
	provider.started = make(chan struct{})
	provider.release = make(chan struct{})
	return provider.started
}

func (provider *task11FuzzProvider) completeCoalesce() {
	provider.mu.Lock()
	release := provider.release
	provider.mu.Unlock()
	if release == nil {
		panic("coalesce barrier not armed")
	}
	close(release)
}

func task11FuzzManager(t *testing.T) (*task11FuzzProvider, *Manager, AcquireRequest) {
	t.Helper()
	grant, verification, resolver := validFrozenGrantCase(t)
	provider := &task11FuzzProvider{grant: grant}
	limits := validLimits()
	limits.MaxCacheEntries, limits.MaxPending, limits.MaxWaitersPerPending, limits.MaxRequestRecords = 8, 4, 8, 8
	limits.MaxCacheBytes, limits.MaxPendingBytes, limits.MaxRequestBytes, limits.MaxGrantBytes = 1<<20, 1<<20, 1<<20, 1<<20
	m, err := NewManager(limits, task4Clock{now: verification.NowUnix}, provider, mustVerifier(t, resolver), fakeCheckpointVerifier{}, fakeFloorStore{}, noopObserver{})
	if err != nil {
		t.Fatal(err)
	}
	m.checkpoint = checkpointState{claims: verification.Checkpoint}
	m.generation, m.hasCheckpoint = verification.Checkpoint.Generation, true
	request := AcquireRequest{Key: verification.Key, Intent: verification.Intent, Device: identity.DeviceIdentity{ID: verification.Key.DeviceID, SourceOperatorID: verification.Key.SourceOperator, CredentialGeneration: verification.Key.DeviceGeneration}, RequestID: RequestID{1}, DeadlineUnix: verification.NowUnix + 1}
	return provider, m, request
}

func task11FuzzRequestID(index int, op byte) RequestID {
	return RequestID{1, byte(index), op}
}

// task11FuzzCoalesce creates exactly two caller goroutines and one manager
// worker, then waits for all three paths before returning to the fuzzer.
func task11FuzzCoalesce(m *Manager, provider *task11FuzzProvider, request AcquireRequest) error {
	started := provider.armCoalesce()
	coalesced := make(chan struct{})
	m.observer = observerFunc(func(event Event) {
		if event.Kind == EventAcquireCoalesced {
			close(coalesced)
		}
	})
	first := make(chan error, 1)
	second := make(chan error, 1)
	go func() { _, err := m.Acquire(context.Background(), request); first <- err }()
	<-started
	go func() { _, err := m.Acquire(context.Background(), request); second <- err }()
	<-coalesced
	provider.completeCoalesce()
	firstErr, secondErr := <-first, <-second
	if firstErr != nil {
		return firstErr
	}
	return secondErr
}
