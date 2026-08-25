package authority

import (
	"context"
	"errors"
	"sync"
)

const maxRestartEvidenceBytes = 64 * 1024

type RestartState uint8

const (
	RestartColdStart RestartState = iota + 1
	RestartFreshnessRequired
	RestartReady
	RestartFailClosed
)

// RestartGate permits no authority-dependent work until newly supplied ACP
// freshness evidence has been independently verified against the local floor.
type RestartGate struct {
	mu sync.RWMutex

	store    GenerationFloorStore
	verifier CheckpointEvidenceVerifier
	clock    Clock
	observer Observer

	state          RestartState
	epoch          uint64
	sourceOperator string
	profile        string
	floor          SignedGenerationFloor
	hasFloor       bool
	accepting      bool
}

func NewRestartGate(store GenerationFloorStore, verifier CheckpointEvidenceVerifier, clock Clock, observer Observer) (*RestartGate, error) {
	if isNilDependency(store) || isNilDependency(verifier) || isNilDependency(clock) || isNilDependency(observer) {
		return nil, ErrInvalidAuthority
	}
	return &RestartGate{store: store, verifier: verifier, clock: clock, observer: observer, state: RestartColdStart}, nil
}

// Load establishes a new cold-start epoch. Missing state is permitted for
// first enrollment, but readiness always requires newly verified freshness.
func (g *RestartGate) Load(ctx context.Context, sourceOperator, profile string) error {
	if g == nil || ctx == nil || !validTextID(sourceOperator) || !validTextID(profile) {
		if g != nil {
			g.failClosed()
		}
		return ErrFloorInvalid
	}
	floor, err := g.store.Load(ctx, sourceOperator, profile)
	if err != nil && !errors.Is(err, ErrFloorNotFound) {
		g.failClosed()
		return err
	}
	hasFloor := err == nil
	if hasFloor {
		floor, err = copySignedGenerationFloor(floor, maxRestartEvidenceBytes)
		if err != nil || floor.SourceOperator != sourceOperator || floor.Profile != profile {
			g.failClosed()
			return ErrFloorInvalid
		}
	}
	g.mu.Lock()
	g.epoch++
	g.sourceOperator = sourceOperator
	g.profile = profile
	g.floor = floor
	g.hasFloor = hasFloor
	g.accepting = false
	g.state = RestartFreshnessRequired
	g.mu.Unlock()
	return nil
}

// AcceptFresh verifies evidence before any floor persistence. The verifier and
// floor store are callbacks and are deliberately invoked outside g.mu.
func (g *RestartGate) AcceptFresh(ctx context.Context, request FreshnessRequest, supplied ProviderFreshness) (VerifiedCheckpoint, error) {
	if g == nil || ctx == nil {
		return VerifiedCheckpoint{}, ErrInvalidAuthority
	}
	if err := validateFreshnessRequest(request); err != nil {
		return VerifiedCheckpoint{}, err
	}
	freshness, err := copyRestartFreshness(supplied)
	if err != nil {
		return VerifiedCheckpoint{}, err
	}
	now := g.clock.NowUnix()
	if !validUnixTime(now) {
		g.failClosed()
		return VerifiedCheckpoint{}, ErrInvalidAuthority
	}
	claims, err := g.verifier.VerifyFreshnessEvidence(ctx, freshness, request, now)
	if err != nil {
		return VerifiedCheckpoint{}, typedFreshnessError(err)
	}
	if err := validateRestartClaims(claims, request, now); err != nil {
		return VerifiedCheckpoint{}, err
	}
	checkpoint, err := sealCheckpoint(claims, Limits{MaxCacheEntries: maxRestartEvidenceBytes})
	if err != nil {
		return VerifiedCheckpoint{}, err
	}

	g.mu.Lock()
	epoch := g.epoch
	state := g.state
	sourceOperator := g.sourceOperator
	profile := g.profile
	floor := g.floor
	hasFloor := g.hasFloor
	if state != RestartFreshnessRequired || g.accepting {
		g.mu.Unlock()
		return VerifiedCheckpoint{}, ErrNotReady
	}
	if request.SourceOperator != sourceOperator || request.Profile != profile {
		g.mu.Unlock()
		return VerifiedCheckpoint{}, ErrBindingMismatch
	}
	if hasFloor && checkpoint.Generation() < floor.Generation {
		g.epoch++
		g.accepting = false
		g.state = RestartFailClosed
		g.mu.Unlock()
		return VerifiedCheckpoint{}, ErrGenerationRollback
	}
	g.accepting = true
	g.mu.Unlock()
	candidate := SignedGenerationFloor{SourceOperator: sourceOperator, Profile: profile, Generation: checkpoint.Generation(), Checkpoint: checkpoint.Digest(), SignedEvidence: freshness.Evidence}
	if err := g.store.StoreHigher(ctx, candidate); err != nil {
		g.failClosedIfEpoch(epoch)
		return VerifiedCheckpoint{}, err
	}

	g.mu.Lock()
	publicationNow := g.clock.NowUnix()
	if g.epoch != epoch || g.state != RestartFreshnessRequired || g.sourceOperator != sourceOperator || g.profile != profile {
		if g.epoch == epoch {
			g.accepting = false
		}
		g.mu.Unlock()
		return VerifiedCheckpoint{}, ErrNotReady
	}
	if !validUnixTime(publicationNow) {
		g.accepting = false
		g.state = RestartFailClosed
		g.epoch++
		g.mu.Unlock()
		return VerifiedCheckpoint{}, ErrInvalidAuthority
	}
	if publicationNow >= checkpoint.FreshUntil() {
		// The verified higher floor remains useful rollback protection, but the
		// evidence has expired before readiness can linearize.
		g.floor = candidate
		g.hasFloor = true
		g.accepting = false
		g.mu.Unlock()
		return VerifiedCheckpoint{}, ErrStaleFreshness
	}
	g.floor = candidate
	g.hasFloor = true
	g.accepting = false
	g.state = RestartReady
	g.mu.Unlock()
	g.observer.Observe(Event{Kind: EventRollbackFloorUpdated})
	return checkpoint, nil
}

func (g *RestartGate) State() RestartState {
	if g == nil {
		return RestartFailClosed
	}
	g.mu.RLock()
	state := g.state
	g.mu.RUnlock()
	return state
}

func (g *RestartGate) RequireReady() error {
	if g == nil {
		return ErrNotReady
	}
	g.mu.RLock()
	ready := g.state == RestartReady
	g.mu.RUnlock()
	if !ready {
		return ErrNotReady
	}
	return nil
}

func (g *RestartGate) failClosed() {
	g.mu.Lock()
	g.epoch++
	g.accepting = false
	g.state = RestartFailClosed
	g.mu.Unlock()
}

func (g *RestartGate) failClosedIfEpoch(epoch uint64) {
	g.mu.Lock()
	if g.epoch == epoch {
		g.epoch++
		g.accepting = false
		g.state = RestartFailClosed
	}
	g.mu.Unlock()
}

func copyRestartFreshness(freshness ProviderFreshness) (ProviderFreshness, error) {
	if !validTextID(freshness.SourceOperator) || !validTextID(freshness.Profile) || len(freshness.Evidence) == 0 || len(freshness.Evidence) > maxRestartEvidenceBytes {
		return ProviderFreshness{}, ErrInvalidAuthority
	}
	freshness.Evidence = append([]byte(nil), freshness.Evidence...)
	return freshness, nil
}

func validateRestartClaims(claims CheckpointClaims, request FreshnessRequest, now uint64) error {
	if !validTextID(claims.SourceOperator) || !validTextID(claims.Profile) || claims.SourceOperator != request.SourceOperator || claims.Profile != request.Profile || claims.Generation == 0 || claims.Generation == ^AuthorityGeneration(0) || claims.Digest == (CheckpointDigest{}) || !validUnixTime(claims.IssuedAt) || !validUnixTime(claims.FreshUntil) || claims.IssuedAt >= claims.FreshUntil || now >= claims.FreshUntil {
		return ErrInvalidAuthority
	}
	return nil
}
