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
	f.Add([]byte{0xf0, 0xf1, 0xf2})
	f.Fuzz(func(t *testing.T, ops []byte) {
		if len(ops) > 256 {
			ops = ops[:256]
		}
		provider, m, observer, request := task11FuzzManager(t)
		for index, op := range ops {
			if task11FuzzBoundaryOperation(t, op) {
				continue
			}
			request.RequestID = task11FuzzRequestID(index, op)
			var err error
			switch op & 7 {
			case 0:
				err = task11FuzzAcquire(m, observer, request)
			case 1:
				err = task11FuzzAcquire(m, observer, request)
			case 2:
				err = task11FuzzRenew(m, observer, RenewRequest{AcquireRequest: request, PreviousGrant: testGrant(250)})
			case 3:
				err = task11FuzzCoalesce(m, provider, observer, request)
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

func task11FuzzBoundaryOperation(t *testing.T, op byte) bool {
	switch op {
	case 0xf0:
		task11FuzzPendingAndWaiterBoundary(t)
	case 0xf1:
		task11FuzzCacheBoundary(t)
	case 0xf2:
		task11FuzzRenewBoundary(t)
	default:
		return false
	}
	return true
}

func task11FuzzPendingAndWaiterBoundary(t *testing.T) {
	provider := &task11BoundaryProvider{started: make(chan struct{}, 4), release: make(chan struct{})}
	m := task11Manager(t)
	observer := &task11BoundaryObserver{events: make(chan Event, 16)}
	m.provider = provider
	m.observer = observer
	requests := make([]AcquireRequest, 5)
	for index := range requests {
		request := validAcquireRequest()
		request.Key.AuthorityGeneration = 7
		request.Key.TSGeneration = TSGeneration(index + 1)
		request.RequestID = RequestID{byte(index + 1)}
		request.DeadlineUnix = 200
		requests[index] = request
	}
	results := make(chan error, 8)
	for index := 0; index < 4; index++ {
		request := requests[index]
		go func() { _, err := m.Acquire(context.Background(), request); results <- err }()
	}
	for range 4 {
		<-provider.started
	}
	for range 4 {
		if event := <-observer.events; event.Kind != EventAcquireRequested {
			t.Fatalf("initial pending event = %v, want EventAcquireRequested", event.Kind)
		}
	}
	for index := 0; index < 4; index++ {
		request := requests[index]
		request.RequestID[1] = 1
		go func() { _, err := m.Acquire(context.Background(), request); results <- err }()
		if event := <-observer.events; event.Kind != EventAcquireCoalesced {
			t.Fatalf("coalesced pending event = %v, want EventAcquireCoalesced", event.Kind)
		}
	}
	if usage := m.Usage(); usage.PendingCalls != 4 || usage.PendingWaiters != 8 || usage.RequestRecords != 8 {
		t.Fatalf("exact pending boundary usage = %+v, want 4 calls/8 waiters/8 records", usage)
	}
	ninth := requests[4]
	ninth.RequestID[2] = 1
	if _, err := m.Acquire(context.Background(), ninth); !errors.Is(err, ErrCacheCapacity) {
		t.Fatalf("ninth retained request = %v, want ErrCacheCapacity", err)
	}
	close(provider.release)
	for range 8 {
		if err := <-results; !errors.Is(err, ErrProviderUnavailable) {
			t.Fatalf("bounded pending result = %v, want ErrProviderUnavailable", err)
		}
	}
	task11RequireInvariants(t, m)
	if usage := m.Usage(); usage.PendingCalls != 0 || usage.PendingWaiters != 0 || usage.RequestRecords != 0 {
		t.Fatalf("pending boundary cleanup = %+v", usage)
	}
}

func task11FuzzCacheBoundary(t *testing.T) {
	m := task11Manager(t)
	for index := 0; index < 8; index++ {
		key := testKey(byte(index + 1))
		_, err := m.reserveVerified(testAuthority(key, testGrant(byte(index+1)), 200))
		if err != nil {
			t.Fatalf("cache entry %d: %v", index, err)
		}
	}
	if usage := m.Usage(); usage.CacheEntries != 8 {
		t.Fatalf("exact cache boundary usage = %+v, want 8 entries", usage)
	}
	if _, err := m.reserveVerified(testAuthority(testKey(9), testGrant(9), 200)); !errors.Is(err, ErrCacheCapacity) {
		t.Fatalf("ninth cache entry = %v, want ErrCacheCapacity", err)
	}
	task11RequireInvariants(t, m)
}

func task11FuzzRenewBoundary(t *testing.T) {
	provider, m, request := coalesceFixture(t)
	previous := testGrant(80)
	cacheAvailableForCoalesce(t, m, request, previous, request.DeadlineUnix+100)
	provider.releaseOnce()
	reservation, err := m.Renew(context.Background(), RenewRequest{AcquireRequest: request, PreviousGrant: previous})
	if err != nil || reservation.id == 0 {
		t.Fatalf("valid matching renew = %#v, %v", reservation, err)
	}
	task11RequireInvariants(t, m)
}

type task11BoundaryProvider struct {
	started chan struct{}
	release chan struct{}
}

func (provider *task11BoundaryProvider) Acquire(context.Context, AcquireRequest) (ProviderGrant, error) {
	provider.started <- struct{}{}
	<-provider.release
	return ProviderGrant{}, ErrProviderUnavailable
}

func (provider *task11BoundaryProvider) Renew(context.Context, RenewRequest) (ProviderGrant, error) {
	return ProviderGrant{}, ErrProviderUnavailable
}

func (provider *task11BoundaryProvider) Freshness(context.Context, FreshnessRequest) (ProviderFreshness, error) {
	return ProviderFreshness{}, ErrProviderUnavailable
}

func (provider *task11BoundaryProvider) Close() error { return nil }

type task11BoundaryObserver struct{ events chan Event }

func (observer *task11BoundaryObserver) Observe(event Event) {
	observer.events <- event
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

func task11FuzzManager(t *testing.T) (*task11FuzzProvider, *Manager, *task11FuzzObserver, AcquireRequest) {
	t.Helper()
	grant, verification, resolver := validFrozenGrantCase(t)
	provider := &task11FuzzProvider{grant: grant}
	observer := &task11FuzzObserver{}
	limits := validLimits()
	limits.MaxCacheEntries, limits.MaxPending, limits.MaxWaitersPerPending, limits.MaxRequestRecords = 8, 4, 8, 8
	limits.MaxCacheBytes, limits.MaxPendingBytes, limits.MaxRequestBytes, limits.MaxGrantBytes = 1<<20, 1<<20, 1<<20, 1<<20
	m, err := NewManager(limits, task4Clock{now: verification.NowUnix}, provider, mustVerifier(t, resolver), fakeCheckpointVerifier{}, fakeFloorStore{}, observer)
	if err != nil {
		t.Fatal(err)
	}
	m.checkpoint = verification.Checkpoint
	m.generation, m.hasCheckpoint = verification.Checkpoint.Generation(), true
	request := AcquireRequest{Key: verification.Key, Intent: verification.Intent, Device: identity.DeviceIdentity{ID: verification.Key.DeviceID, SourceOperatorID: verification.Key.SourceOperator, CredentialGeneration: verification.Key.DeviceGeneration}, RequestID: RequestID{1}, DeadlineUnix: verification.NowUnix + 1}
	return provider, m, observer, request
}

func task11FuzzRequestID(index int, op byte) RequestID {
	return RequestID{1, byte(index), op}
}

// task11FuzzCoalesce creates exactly two caller goroutines and one manager
// worker, then waits for the terminal observer event before the next action.
func task11FuzzCoalesce(m *Manager, provider *task11FuzzProvider, observer *task11FuzzObserver, request AcquireRequest) error {
	started := provider.armCoalesce()
	coalesced := observer.armCoalesced()
	completed := observer.armAcquireResult()
	first := make(chan error, 1)
	second := make(chan error, 1)
	go func() { _, err := m.Acquire(context.Background(), request); first <- err }()
	<-started
	go func() { _, err := m.Acquire(context.Background(), request); second <- err }()
	<-coalesced
	provider.completeCoalesce()
	firstErr, secondErr := <-first, <-second
	<-completed
	if firstErr != nil {
		return firstErr
	}
	return secondErr
}

func task11FuzzAcquire(m *Manager, observer *task11FuzzObserver, request AcquireRequest) error {
	m.mu.RLock()
	entry := m.cache[request.Key]
	cacheHit := entry != nil && entry.state == cacheAvailable
	m.mu.RUnlock()
	completed := observer.armAcquireResult()
	_, err := m.Acquire(context.Background(), request)
	if cacheHit {
		observer.disarmAcquireResult(completed)
		return err
	}
	<-completed
	return err
}

func task11FuzzRenew(m *Manager, observer *task11FuzzObserver, request RenewRequest) error {
	completed := observer.armRenewResult()
	_, err := m.Renew(context.Background(), request)
	<-completed
	return err
}

// task11FuzzObserver is installed once at manager construction. Its channels
// are armed before each bounded operation, never by replacing Manager fields
// while a worker may be completing notification.
type task11FuzzObserver struct {
	mu sync.Mutex

	coalesced  chan struct{}
	acquireEnd chan struct{}
	renewEnd   chan struct{}
}

func (observer *task11FuzzObserver) Observe(event Event) {
	observer.mu.Lock()
	var signal chan struct{}
	switch event.Kind {
	case EventAcquireCoalesced:
		signal, observer.coalesced = observer.coalesced, nil
	case EventAcquireResult:
		signal, observer.acquireEnd = observer.acquireEnd, nil
	case EventRenewalResult:
		signal, observer.renewEnd = observer.renewEnd, nil
	}
	observer.mu.Unlock()
	if signal != nil {
		close(signal)
	}
}

func (observer *task11FuzzObserver) armCoalesced() <-chan struct{} {
	observer.mu.Lock()
	defer observer.mu.Unlock()
	if observer.coalesced != nil {
		panic("coalescing signal already armed")
	}
	observer.coalesced = make(chan struct{})
	return observer.coalesced
}

func (observer *task11FuzzObserver) armAcquireResult() <-chan struct{} {
	observer.mu.Lock()
	defer observer.mu.Unlock()
	if observer.acquireEnd != nil {
		panic("acquire completion signal already armed")
	}
	observer.acquireEnd = make(chan struct{})
	return observer.acquireEnd
}

func (observer *task11FuzzObserver) disarmAcquireResult(signal <-chan struct{}) {
	observer.mu.Lock()
	if observer.acquireEnd == signal {
		observer.acquireEnd = nil
	}
	observer.mu.Unlock()
}

func (observer *task11FuzzObserver) armRenewResult() <-chan struct{} {
	observer.mu.Lock()
	defer observer.mu.Unlock()
	if observer.renewEnd != nil {
		panic("renew completion signal already armed")
	}
	observer.renewEnd = make(chan struct{})
	return observer.renewEnd
}
