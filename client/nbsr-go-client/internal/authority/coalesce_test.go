package authority

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"math"
	"sync"
	"testing"
	"time"

	"nbsr.local/client/nbsr-go-client/internal/identity"
)

func TestExactAcquisitionCoalescesOneProviderCall(t *testing.T) {
	provider, manager, request := coalesceFixture(t)
	const callers = 8
	start := make(chan struct{})
	results := make(chan acquireResult, callers)
	for i := 0; i < callers; i++ {
		request := request
		request.RequestID[0] = byte(i + 1)
		go func() {
			<-start
			reservation, err := manager.Acquire(context.Background(), request)
			results <- acquireResult{reservation, err}
		}()
	}
	close(start)
	awaitCoalesce(t, provider.started)
	awaitWaiters(t, manager, callers)
	provider.releaseOnce()
	var first Reservation
	for i := 0; i < callers; i++ {
		result := <-results
		if result.err != nil {
			t.Fatalf("Acquire %d: %v", i, result.err)
		}
		if i == 0 {
			first = result.reservation
		} else if result.reservation != first {
			t.Fatalf("reservation %d = %#v, want %#v", i, result.reservation, first)
		}
	}
	if got := provider.calls(); got != 1 {
		t.Fatalf("provider calls = %d, want 1", got)
	}
	if calls, waiters, bytes := pendingState(manager); calls != 0 || waiters != 0 || bytes != 0 {
		t.Fatalf("pending state after completion = calls:%d waiters:%d bytes:%d", calls, waiters, bytes)
	}
}

func TestCoalescingSeparatesOperationAndPreviousGrant(t *testing.T) {
	provider, manager, request := coalesceFixture(t)
	renew := RenewRequest{AcquireRequest: request, PreviousGrant: testGrant(99)}
	acquired := make(chan error, 1)
	renewed := make(chan error, 1)
	go func() { _, err := manager.Acquire(context.Background(), request); acquired <- err }()
	awaitCoalesce(t, provider.started)
	go func() { _, err := manager.Renew(context.Background(), renew); renewed <- err }()
	provider.releaseOnce()
	acquireErr, renewErr := <-acquired, <-renewed
	if acquireErr != nil {
		t.Fatalf("Acquire: %v", acquireErr)
	}
	if !errors.Is(renewErr, ErrRequestConflict) {
		t.Fatalf("Renew with acquire request ID error = %v, want ErrRequestConflict", renewErr)
	}
	if got := provider.calls(); got != 1 {
		t.Fatalf("provider calls = %d, want 1", got)
	}
}

func TestCacheHitRetiresExpiredRevokedAndStaleAuthorityBeforeReservation(t *testing.T) {
	for _, tt := range []struct {
		name    string
		prepare func(*Manager, *mutableClock, RouteGrantDigest)
		want    error
	}{
		{"expired", func(_ *Manager, clock *mutableClock, _ RouteGrantDigest) { clock.set(1_893_456_001) }, ErrExpired},
		{"revoked", func(manager *Manager, _ *mutableClock, grant RouteGrantDigest) {
			manager.checkpoint.revoked = []RouteGrantDigest{grant}
		}, ErrRevoked},
		{"stale checkpoint", func(manager *Manager, _ *mutableClock, _ RouteGrantDigest) {
			manager.checkpoint.claims.Digest = CheckpointDigest{0xee}
		}, ErrStaleGeneration},
		{"stale generation", func(manager *Manager, _ *mutableClock, _ RouteGrantDigest) {
			manager.generation++
			manager.checkpoint.claims.Generation++
		}, ErrStaleGeneration},
	} {
		t.Run(tt.name, func(t *testing.T) {
			provider, manager, request := coalesceFixture(t)
			request.DeadlineUnix = 1_893_456_100
			clock := &mutableClock{now: 1_893_456_000}
			manager.clock = clock
			grant := testGrant(81)
			cacheAvailableForCoalesce(t, manager, request, grant, 1_893_456_001)
			manager.mu.Lock()
			tt.prepare(manager, clock, grant)
			manager.mu.Unlock()
			if _, err := manager.Acquire(context.Background(), request); !errors.Is(err, tt.want) {
				t.Fatalf("cache-hit Acquire error = %v, want %v", err, tt.want)
			}
			manager.mu.RLock()
			_, cached := manager.cache[request.Key]
			terminal, tombstoned := manager.tombstones[grant]
			manager.mu.RUnlock()
			if cached || !tombstoned || terminal.state != cacheInvalid {
				t.Fatalf("stale cache entry was not invalidated: cached=%t tombstone=%+v", cached, terminal)
			}
			if got := provider.calls(); got != 0 {
				t.Fatalf("stale cache hit called provider %d times", got)
			}
		})
	}
}

func TestRenewAtomicallyReplacesEligiblePreviousGrant(t *testing.T) {
	provider, manager, request := coalesceFixture(t)
	oldGrant := testGrant(82)
	cacheAvailableForCoalesce(t, manager, request, oldGrant, 1_893_456_300)
	provider.grant = renewedProviderGrant(t, provider.grant)
	provider.releaseOnce()
	reservation, err := manager.Renew(context.Background(), RenewRequest{AcquireRequest: request, PreviousGrant: oldGrant})
	if err != nil {
		t.Fatalf("Renew: %v", err)
	}
	newGrant := RouteGrantDigest(sha256.Sum256(provider.grant.ExactRouteGrant))
	if reservation.grant != newGrant || newGrant == oldGrant {
		t.Fatalf("renewal reservation grant = %x, want new %x", reservation.grant, newGrant)
	}
	manager.mu.RLock()
	oldTerminal, oldTombstoned := manager.tombstones[oldGrant]
	entry := manager.grants[newGrant]
	manager.mu.RUnlock()
	if !oldTombstoned || oldTerminal.state != cacheConsumed || entry == nil || entry.state != cacheReserved {
		t.Fatalf("replacement state invalid: old=%+v new=%+v", oldTerminal, entry)
	}
	if err := manager.ValidateInvariants(); err != nil {
		t.Fatalf("replacement invariants: %v", err)
	}
}

func TestRenewRejectsMismatchedOrTerminalPreviousGrant(t *testing.T) {
	t.Run("mismatched", func(t *testing.T) {
		provider, manager, request := coalesceFixture(t)
		oldGrant := testGrant(83)
		cacheAvailableForCoalesce(t, manager, request, oldGrant, 1_893_456_300)
		provider.grant = renewedProviderGrant(t, provider.grant)
		provider.releaseOnce()
		if _, err := manager.Renew(context.Background(), RenewRequest{AcquireRequest: request, PreviousGrant: testGrant(84)}); !errors.Is(err, ErrInvalidAuthority) {
			t.Fatalf("mismatched previous grant error = %v, want ErrInvalidAuthority", err)
		}
		if err := manager.ValidateInvariants(); err != nil {
			t.Fatalf("mismatch invariants: %v", err)
		}
	})
	t.Run("terminal", func(t *testing.T) {
		provider, manager, request := coalesceFixture(t)
		oldGrant := testGrant(85)
		cacheAvailableForCoalesce(t, manager, request, oldGrant, 1_893_456_300)
		manager.mu.Lock()
		manager.retireEntryLocked(manager.grants[oldGrant], cacheQuarantined)
		manager.mu.Unlock()
		provider.grant = renewedProviderGrant(t, provider.grant)
		provider.releaseOnce()
		if _, err := manager.Renew(context.Background(), RenewRequest{AcquireRequest: request, PreviousGrant: oldGrant}); !errors.Is(err, ErrInvalidTransition) {
			t.Fatalf("terminal previous grant error = %v, want ErrInvalidTransition", err)
		}
	})
}

func TestRenewReplacementReservationOverflowIsAtomic(t *testing.T) {
	provider, manager, request := coalesceFixture(t)
	oldGrant := testGrant(86)
	cacheAvailableForCoalesce(t, manager, request, oldGrant, 1_893_456_300)
	provider.grant = renewedProviderGrant(t, provider.grant)
	newGrant := RouteGrantDigest(sha256.Sum256(provider.grant.ExactRouteGrant))
	manager.mu.Lock()
	manager.nextReservation = math.MaxUint64
	manager.mu.Unlock()
	provider.releaseOnce()
	if _, err := manager.Renew(context.Background(), RenewRequest{AcquireRequest: request, PreviousGrant: oldGrant}); !errors.Is(err, ErrAccountingOverflow) {
		t.Fatalf("overflow renewal error = %v, want ErrAccountingOverflow", err)
	}
	manager.mu.RLock()
	oldEntry := manager.grants[oldGrant]
	_, oldTombstoned := manager.tombstones[oldGrant]
	newEntry := manager.grants[newGrant]
	manager.mu.RUnlock()
	if oldEntry == nil || oldEntry.state != cacheAvailable || oldTombstoned || newEntry != nil {
		t.Fatalf("overflow mutated replacement state: old=%+v tombstoned=%t new=%+v", oldEntry, oldTombstoned, newEntry)
	}
}

func TestCoalescedCallerCancellationDoesNotCancelRemainingCall(t *testing.T) {
	provider, manager, request := coalesceFixture(t)
	ownerResult := make(chan error, 1)
	go func() { _, err := manager.Acquire(context.Background(), request); ownerResult <- err }()
	awaitCoalesce(t, provider.started)
	ctx, cancel := context.WithCancel(context.Background())
	joined := make(chan error, 1)
	go func() { _, err := manager.Acquire(ctx, request); joined <- err }()
	awaitWaiters(t, manager, 2)
	cancel()
	if err := <-joined; !errors.Is(err, context.Canceled) {
		t.Fatalf("canceled joiner error = %v, want context.Canceled", err)
	}
	select {
	case <-provider.contextDone:
		t.Fatal("one canceled waiter canceled the shared provider call")
	default:
	}
	provider.releaseOnce()
	if err := <-ownerResult; err != nil {
		t.Fatalf("remaining owner: %v", err)
	}
}

func TestAllCanceledCallIsAbandonedAndCannotPopulateCache(t *testing.T) {
	provider, manager, request := coalesceFixture(t)
	ctx, cancel := context.WithCancel(context.Background())
	result := make(chan error, 1)
	go func() { _, err := manager.Acquire(ctx, request); result <- err }()
	awaitCoalesce(t, provider.started)
	cancel()
	if err := <-result; !errors.Is(err, context.Canceled) {
		t.Fatalf("caller error = %v, want context.Canceled", err)
	}
	awaitCoalesce(t, provider.contextDone)
	provider.releaseOnce()
	eventuallyCoalesce(t, func() bool { calls, _, _ := pendingState(manager); return calls == 0 })
	if calls, _, bytes := pendingState(manager); manager.Usage().CacheEntries != 0 || calls != 0 || bytes != 0 {
		t.Fatalf("abandoned call retained authority or accounting: calls:%d bytes:%d", calls, bytes)
	}
}

func TestPendingAndWaiterBoundsAreExact(t *testing.T) {
	provider, manager, request := coalesceFixture(t)
	manager.limits.MaxPending = 1
	manager.limits.MaxWaitersPerPending = 2
	owner := make(chan error, 1)
	go func() { _, err := manager.Acquire(context.Background(), request); owner <- err }()
	awaitCoalesce(t, provider.started)
	join := make(chan error, 1)
	go func() { _, err := manager.Acquire(context.Background(), request); join <- err }()
	awaitWaiters(t, manager, 2)
	if _, err := manager.Acquire(context.Background(), request); !errors.Is(err, ErrWaiterCapacity) {
		t.Fatalf("third waiter error = %v, want ErrWaiterCapacity", err)
	}
	other := request
	other.Key.TSGeneration++
	other.RequestID[0]++
	if _, err := manager.Acquire(context.Background(), other); !errors.Is(err, ErrPendingCapacity) {
		t.Fatalf("second pending call error = %v, want ErrPendingCapacity", err)
	}
	provider.releaseOnce()
	if err := <-owner; err != nil {
		t.Fatalf("owner: %v", err)
	}
	if err := <-join; err != nil {
		t.Fatalf("joiner: %v", err)
	}
}

func TestUsageAndInvariantsAccountForPendingCalls(t *testing.T) {
	provider, manager, request := coalesceFixture(t)
	result := make(chan error, 1)
	go func() { _, err := manager.Acquire(context.Background(), request); result <- err }()
	awaitCoalesce(t, provider.started)
	bytes, err := pendingLogicalBytes(pendingKey{authority: request.Key, operation: pendingAcquire}, request)
	if err != nil {
		t.Fatalf("pendingLogicalBytes: %v", err)
	}
	if usage := manager.Usage(); usage.PendingCalls != 1 || usage.PendingWaiters != 1 || usage.PendingBytes != bytes {
		t.Fatalf("pending Usage = %+v, want calls=1 waiters=1 bytes=%d", usage, bytes)
	}
	if err := manager.ValidateInvariants(); err != nil {
		t.Fatalf("valid pending state rejected: %v", err)
	}
	manager.mu.Lock()
	manager.pendingBytes++
	manager.mu.Unlock()
	if err := manager.ValidateInvariants(); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("corrupt pending bytes error = %v, want ErrInvalidAuthority", err)
	}
	manager.mu.Lock()
	manager.pendingBytes--
	manager.pending[pendingKey{authority: request.Key, operation: pendingAcquire}].waiters = 0
	manager.mu.Unlock()
	if err := manager.ValidateInvariants(); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("corrupt waiter count error = %v, want ErrInvalidAuthority", err)
	}
	manager.mu.Lock()
	manager.pending[pendingKey{authority: request.Key, operation: pendingAcquire}].waiters = 1
	manager.mu.Unlock()
	provider.releaseOnce()
	if err := <-result; err != nil {
		t.Fatalf("Acquire: %v", err)
	}
}

func TestPendingByteCapRejectsBeforeProviderCall(t *testing.T) {
	provider, manager, request := coalesceFixture(t)
	key := pendingKey{authority: request.Key, operation: pendingAcquire}
	bytes, err := pendingLogicalBytes(key, request)
	if err != nil {
		t.Fatalf("pendingLogicalBytes: %v", err)
	}
	manager.limits.MaxPendingBytes = bytes - 1
	if _, err := manager.Acquire(context.Background(), request); !errors.Is(err, ErrPendingCapacity) {
		t.Fatalf("Acquire error = %v, want ErrPendingCapacity", err)
	}
	if got := provider.calls(); got != 0 {
		t.Fatalf("provider calls = %d, want 0", got)
	}
}

func TestPendingKeyIncludesEveryAuthorityDimension(t *testing.T) {
	_, _, request := coalesceFixture(t)
	base := pendingKey{authority: request.Key, operation: pendingAcquire}
	changes := []struct {
		name string
		edit func(*AuthorityKey)
	}{
		{"intent digest", func(key *AuthorityKey) { key.IntentDigest[0]++ }},
		{"service digest", func(key *AuthorityKey) { key.ServiceDigest[0]++ }},
		{"source operator", func(key *AuthorityKey) { key.SourceOperator += "x" }},
		{"source edge", func(key *AuthorityKey) { key.SourceEdge += "x" }},
		{"target operator", func(key *AuthorityKey) { key.TargetOperator += "x" }},
		{"target edge set", func(key *AuthorityKey) { key.TargetEdgeSetDigest[0]++ }},
		{"profile", func(key *AuthorityKey) { key.Profile += "x" }},
		{"transport", func(key *AuthorityKey) { key.Transport += "x" }},
		{"port", func(key *AuthorityKey) { key.Port++ }},
		{"device id", func(key *AuthorityKey) { key.DeviceID[0]++ }},
		{"device generation", func(key *AuthorityKey) { key.DeviceGeneration++ }},
		{"workload digest", func(key *AuthorityKey) { key.WorkloadDigest[0]++ }},
		{"workload generation", func(key *AuthorityKey) { key.WorkloadGeneration++ }},
		{"transport-session generation", func(key *AuthorityKey) { key.TSGeneration++ }},
		{"proof thumbprint", func(key *AuthorityKey) { key.ProofThumbprint[0]++ }},
		{"policy hash", func(key *AuthorityKey) { key.PolicyHash[0]++ }},
		{"policy generation", func(key *AuthorityKey) { key.PolicyGeneration++ }},
		{"authority generation", func(key *AuthorityKey) { key.AuthorityGeneration++ }},
	}
	for _, change := range changes {
		t.Run(change.name, func(t *testing.T) {
			key := request.Key
			change.edit(&key)
			if got := (pendingKey{authority: key, operation: pendingAcquire}); got == base {
				t.Fatal("distinct authority scope coalesced")
			}
		})
	}
	if (pendingKey{authority: request.Key, operation: pendingRenew, previous: testGrant(1)}) == base {
		t.Fatal("renewal coalesced with acquisition")
	}
	firstRenew := pendingKey{authority: request.Key, operation: pendingRenew, previous: testGrant(1)}
	secondRenew := pendingKey{authority: request.Key, operation: pendingRenew, previous: testGrant(2)}
	if firstRenew == secondRenew {
		t.Fatal("renewals with distinct previous grants coalesced")
	}
}

func TestProviderAndVerificationFailureWakeEveryWaiterWithoutCaching(t *testing.T) {
	for _, tt := range []struct {
		name  string
		setup func(*coalesceProvider)
		want  error
	}{
		{"provider", func(provider *coalesceProvider) { provider.err = errors.New("unavailable") }, ErrProviderUnavailable},
		{"verification", func(provider *coalesceProvider) {
			provider.grant.ExactRouteGrant = append([]byte(nil), provider.grant.ExactRouteGrant...)
			provider.grant.ExactRouteGrant[0] ^= 0xff
		}, ErrInvalidAuthority},
	} {
		t.Run(tt.name, func(t *testing.T) {
			provider, manager, request := coalesceFixture(t)
			tt.setup(provider)
			results := make(chan error, 2)
			go func() { _, err := manager.Acquire(context.Background(), request); results <- err }()
			awaitCoalesce(t, provider.started)
			go func() { _, err := manager.Acquire(context.Background(), request); results <- err }()
			awaitWaiters(t, manager, 2)
			provider.releaseOnce()
			for i := 0; i < 2; i++ {
				if err := <-results; !errors.Is(err, tt.want) {
					t.Fatalf("waiter %d error = %v, want %v", i, err, tt.want)
				}
			}
			if entries := manager.Usage().CacheEntries; entries != 0 {
				t.Fatalf("failed result populated cache: %d entries", entries)
			}
		})
	}
}

func TestGenerationChangeDuringProviderCallCannotCommit(t *testing.T) {
	provider, manager, request := coalesceFixture(t)
	result := make(chan error, 1)
	go func() { _, err := manager.Acquire(context.Background(), request); result <- err }()
	awaitCoalesce(t, provider.started)
	manager.mu.Lock()
	manager.generation++
	manager.checkpoint.claims.Generation++
	manager.mu.Unlock()
	provider.releaseOnce()
	if err := <-result; !errors.Is(err, ErrStaleGeneration) {
		t.Fatalf("Acquire after generation change = %v, want ErrStaleGeneration", err)
	}
	if entries := manager.Usage().CacheEntries; entries != 0 {
		t.Fatalf("stale result populated cache: %d entries", entries)
	}
}

func TestProviderAndObserverRunOutsideManagerLock(t *testing.T) {
	provider, manager, request := coalesceFixture(t)
	provider.reenter = func() {
		if !manager.mu.TryLock() {
			t.Error("provider called with manager lock held")
			return
		}
		manager.mu.Unlock()
	}
	manager.observer = observerFunc(func(Event) {
		if !manager.mu.TryLock() {
			t.Error("observer called with manager lock held")
			return
		}
		manager.mu.Unlock()
	})
	resolver := manager.verifier.issuers
	manager.verifier = mustVerifier(t, issuerResolverFunc(func(ctx context.Context, kid []byte, profile, source string, now uint64) (IssuerRecord, error) {
		if !manager.mu.TryLock() {
			t.Error("verifier callback called with manager lock held")
		} else {
			manager.mu.Unlock()
		}
		return resolver.ResolveRouteGrantIssuer(ctx, kid, profile, source, now)
	}))
	result := make(chan error, 1)
	go func() { _, err := manager.Acquire(context.Background(), request); result <- err }()
	awaitCoalesce(t, provider.started)
	provider.releaseOnce()
	if err := <-result; err != nil {
		t.Fatalf("Acquire: %v", err)
	}
}

func TestCloseWakesPendingWaiters(t *testing.T) {
	provider, manager, request := coalesceFixture(t)
	result := make(chan error, 1)
	go func() { _, err := manager.Acquire(context.Background(), request); result <- err }()
	awaitCoalesce(t, provider.started)
	if err := manager.Close(); err != nil {
		t.Fatalf("Close: %v", err)
	}
	if err := <-result; !errors.Is(err, ErrClosed) {
		t.Fatalf("pending Acquire error = %v, want ErrClosed", err)
	}
	awaitCoalesce(t, provider.contextDone)
	provider.releaseOnce()
}

func TestBothReadyDoneWinsOverCanceledContext(t *testing.T) {
	for range 128 {
		ctx, cancel := context.WithCancel(context.Background())
		call := &pendingCall{done: make(chan struct{}), result: pendingResult{reservation: Reservation{id: 1}}}
		close(call.done)
		cancel()
		got, err := (&Manager{}).waitPending(ctx, call)
		if err != nil || got.id != 1 {
			t.Fatalf("both-ready result = %#v, %v; want completed result", got, err)
		}
	}
}

func TestProviderResultAtRequestDeadlineCannotReserveOrComplete(t *testing.T) {
	provider, manager, request := coalesceFixture(t)
	clock := &mutableClock{now: request.DeadlineUnix - 1}
	manager.clock = clock
	result := make(chan error, 1)
	go func() { _, err := manager.Acquire(context.Background(), request); result <- err }()
	awaitCoalesce(t, provider.started)
	clock.set(request.DeadlineUnix)
	provider.releaseOnce()
	if err := <-result; !errors.Is(err, ErrExpired) {
		t.Fatalf("deadline result = %v, want ErrExpired", err)
	}
	if usage := manager.Usage(); usage.CacheEntries != 0 || usage.RequestRecords != 0 {
		t.Fatalf("deadline result retained authority/request state: %#v", usage)
	}
}

type acquireResult struct {
	reservation Reservation
	err         error
}

type coalesceProvider struct {
	mu           sync.Mutex
	grant        ProviderGrant
	started      chan struct{}
	renewStarted chan struct{}
	release      chan struct{}
	contextDone  chan struct{}
	startOnce    sync.Once
	renewOnce    sync.Once
	releaseOnceS sync.Once
	doneOnce     sync.Once
	callCount    int
	reenter      func()
	err          error
}

func (p *coalesceProvider) Acquire(ctx context.Context, _ AcquireRequest) (ProviderGrant, error) {
	p.start(ctx, p.started, &p.startOnce)
	return p.wait(ctx)
}

func (p *coalesceProvider) Renew(ctx context.Context, _ RenewRequest) (ProviderGrant, error) {
	p.start(ctx, p.renewStarted, &p.renewOnce)
	return p.wait(ctx)
}

func (p *coalesceProvider) Freshness(context.Context, FreshnessRequest) (ProviderFreshness, error) {
	return ProviderFreshness{}, ErrProviderUnavailable
}
func (p *coalesceProvider) Close() error { return nil }

func (p *coalesceProvider) start(ctx context.Context, started chan struct{}, once *sync.Once) {
	p.mu.Lock()
	p.callCount++
	reenter := p.reenter
	p.mu.Unlock()
	if reenter != nil {
		reenter()
	}
	once.Do(func() { close(started) })
	go func() { <-ctx.Done(); p.doneOnce.Do(func() { close(p.contextDone) }) }()
}

func (p *coalesceProvider) wait(ctx context.Context) (ProviderGrant, error) {
	select {
	case <-p.release:
		p.mu.Lock()
		err := p.err
		p.mu.Unlock()
		if err != nil {
			return ProviderGrant{}, err
		}
		return p.grant, nil
	case <-ctx.Done():
		return ProviderGrant{}, ctx.Err()
	}
}

func (p *coalesceProvider) releaseOnce() { p.releaseOnceS.Do(func() { close(p.release) }) }
func (p *coalesceProvider) calls() int   { p.mu.Lock(); defer p.mu.Unlock(); return p.callCount }

func coalesceFixture(t *testing.T) (*coalesceProvider, *Manager, AcquireRequest) {
	t.Helper()
	grant, verification, resolver := validFrozenGrantCase(t)
	provider := &coalesceProvider{grant: grant, started: make(chan struct{}), renewStarted: make(chan struct{}), release: make(chan struct{}), contextDone: make(chan struct{})}
	limits := validLimits()
	limits.MaxCacheEntries, limits.MaxPending, limits.MaxWaitersPerPending, limits.MaxRequestRecords = 8, 8, 8, 16
	limits.MaxCacheBytes, limits.MaxPendingBytes, limits.MaxRequestBytes, limits.MaxGrantBytes = 1<<20, 1<<20, 1<<20, 1<<20
	manager, err := NewManager(limits, task4Clock{now: verification.NowUnix}, provider, mustVerifier(t, resolver), fakeCheckpointVerifier{}, fakeFloorStore{}, noopObserver{})
	if err != nil {
		t.Fatalf("NewManager: %v", err)
	}
	manager.checkpoint = checkpointState{claims: verification.Checkpoint}
	manager.generation, manager.hasCheckpoint = verification.Checkpoint.Generation, true
	request := AcquireRequest{Key: verification.Key, Intent: verification.Intent, Device: identity.DeviceIdentity{ID: verification.Key.DeviceID, SourceOperatorID: verification.Key.SourceOperator, CredentialGeneration: verification.Key.DeviceGeneration}, RequestID: RequestID{1}, DeadlineUnix: verification.NowUnix + 1}
	return provider, manager, request
}

func awaitCoalesce(t *testing.T, signal <-chan struct{}) {
	t.Helper()
	select {
	case <-signal:
	case <-time.After(2 * time.Second):
		t.Fatal("timed out waiting for coalescing signal")
	}
}

func awaitWaiters(t *testing.T, manager *Manager, wanted int) {
	t.Helper()
	eventuallyCoalesce(t, func() bool { _, waiters, _ := pendingState(manager); return waiters == wanted })
}

func pendingState(manager *Manager) (calls, waiters int, bytes uint64) {
	manager.mu.RLock()
	defer manager.mu.RUnlock()
	for _, call := range manager.pending {
		waiters += call.waiters
	}
	return len(manager.pending), waiters, manager.pendingBytes
}

func cacheAvailableForCoalesce(t *testing.T, manager *Manager, request AcquireRequest, grant RouteGrantDigest, expiresAt uint64) {
	t.Helper()
	manager.mu.RLock()
	checkpoint := manager.checkpoint.claims.Digest
	manager.mu.RUnlock()
	reservation, err := manager.reserveVerified(sealAuthority(request.Key, grant, expiresAt, checkpoint, request.Key.AuthorityGeneration))
	if err != nil {
		t.Fatalf("reserve old authority: %v", err)
	}
	if err := manager.Release(reservation); err != nil {
		t.Fatalf("release old authority: %v", err)
	}
}

func renewedProviderGrant(t *testing.T, grant ProviderGrant) ProviderGrant {
	t.Helper()
	sign1, err := parseRouteGrantSign1(grant.ExactRouteGrant)
	if err != nil {
		t.Fatalf("parse frozen grant: %v", err)
	}
	decoded, err := decodeCBORExact(sign1.payload, defaultCBORLimits())
	if err != nil {
		t.Fatalf("decode frozen payload: %v", err)
	}
	fields, ok := decoded.(map[uint64]any)
	if !ok {
		t.Fatal("frozen payload is not a field map")
	}
	fields[16] = append([]byte{0xff}, make([]byte, 15)...)
	payload, err := encodeCBOR(fields)
	if err != nil {
		t.Fatalf("encode renewed payload: %v", err)
	}
	seed, err := hex.DecodeString(string(bytes.TrimSpace(readRepo(t, "vectors", "core-v0.2", "keys", "test-only-route-grant-ed25519-seed.hex"))))
	if err != nil || len(seed) != ed25519.SeedSize {
		t.Fatal("invalid test route-grant signing seed")
	}
	structure, err := encodeCBOR([]any{"Signature1", sign1.protected, []byte{}, payload})
	if err != nil {
		t.Fatalf("encode signature structure: %v", err)
	}
	signature := ed25519.Sign(ed25519.NewKeyFromSeed(seed), structure)
	encoded, err := encodeCBOR([]any{sign1.protected, map[uint64]any{}, payload, signature})
	if err != nil {
		t.Fatalf("encode renewed Sign1: %v", err)
	}
	grant.ExactRouteGrant = append([]byte{0xd2}, encoded...)
	return grant
}

func eventuallyCoalesce(t *testing.T, predicate func() bool) {
	t.Helper()
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		if predicate() {
			return
		}
		time.Sleep(time.Millisecond)
	}
	t.Fatal("condition was not satisfied")
}
