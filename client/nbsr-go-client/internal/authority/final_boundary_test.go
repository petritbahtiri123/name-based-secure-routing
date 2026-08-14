package authority

import (
	"context"
	"errors"
	"reflect"
	"testing"
)

func TestVerifiedCheckpointSealsAndCopiesClaims(t *testing.T) {
	claims := checkpoint(7, 100, 200)
	claims.RevokedGrants = []RouteGrantDigest{{3}, {1}, {3}}
	sealed, err := sealCheckpoint(claims, validLimits())
	if err != nil {
		t.Fatalf("sealCheckpoint: %v", err)
	}
	if sealed.Generation() != 7 || sealed.FreshUntil() != 200 || sealed.Digest() != claims.Digest {
		t.Fatalf("sealed checkpoint accessors = generation %d fresh-until %d digest %x", sealed.Generation(), sealed.FreshUntil(), sealed.Digest())
	}
	claims.RevokedGrants[0] = RouteGrantDigest{9}
	if got := sealed.revokedDigests(); len(got) != 2 || got[0] != (RouteGrantDigest{1}) || got[1] != (RouteGrantDigest{3}) {
		t.Fatalf("sealed revocations = %#v, want sorted immutable copy", got)
	}
}

func TestPublishFreshnessReturnsUsableSealedCheckpoint(t *testing.T) {
	m := freshManager(t, checkpoint(7, 100, 200))
	checkpoint, err := m.PublishFreshness(context.Background(), task4Request(), task4ProviderFreshness())
	if err != nil {
		t.Fatalf("PublishFreshness: %v", err)
	}
	if checkpoint.Generation() != 7 || checkpoint.FreshUntil() != 200 || checkpoint.Digest() != (CheckpointDigest{7}) {
		t.Fatalf("published checkpoint did not retain verified claims: %#v", checkpoint)
	}
}

func TestZeroVerifiedCheckpointCannotAuthorizeRouteGrant(t *testing.T) {
	grant, verification, resolver := validFrozenGrantCase(t)
	verifier := mustVerifier(t, resolver)
	verification.Checkpoint = VerifiedCheckpoint{}
	if _, err := verifier.VerifyRouteGrant(context.Background(), grant, verification); !errors.Is(err, ErrStaleFreshness) {
		t.Fatalf("zero sealed checkpoint verification = %v, want ErrStaleFreshness", err)
	}
}

func TestRawCheckpointClaimsCannotActAsSealedAuthority(t *testing.T) {
	sealedType := reflect.TypeOf(VerifiedCheckpoint{})
	rawType := reflect.TypeOf(CheckpointClaims{})
	if sealedType == rawType {
		t.Fatal("raw claims and sealed checkpoint unexpectedly share a type")
	}
	for index := 0; index < sealedType.NumField(); index++ {
		if sealedType.Field(index).IsExported() {
			t.Fatalf("VerifiedCheckpoint exports forgeable field %q", sealedType.Field(index).Name)
		}
	}
	if _, ok := any(CheckpointClaims{}).(interface{ Generation() AuthorityGeneration }); ok {
		t.Fatal("raw checkpoint claims satisfy sealed authority accessor contract")
	}
}

func TestRestartGateReturnsUsableSealedCheckpoint(t *testing.T) {
	gate := newGate(t, testFloor(7))
	if err := gate.Load(context.Background(), "source-a", "profile-a"); err != nil {
		t.Fatalf("Load: %v", err)
	}
	checkpoint, err := gate.AcceptFresh(context.Background(), freshnessRequest(8), freshnessEvidence(8))
	if err != nil {
		t.Fatalf("AcceptFresh: %v", err)
	}
	if checkpoint.Generation() != 8 || checkpoint.FreshUntil() != 200 || checkpoint.Digest() != testCheckpoint(8) {
		t.Fatalf("restart checkpoint accessors = generation %d fresh-until %d digest %x", checkpoint.Generation(), checkpoint.FreshUntil(), checkpoint.Digest())
	}
}

func TestConsumedCompletedRequestRemainsTerminalAndInvariantSafe(t *testing.T) {
	provider, manager, request := coalesceFixture(t)
	provider.releaseOnce()
	reservation, err := manager.Acquire(context.Background(), request)
	if err != nil {
		t.Fatalf("Acquire: %v", err)
	}
	snapshot, err := manager.CaptureGeneration()
	if err != nil {
		t.Fatalf("CaptureGeneration: %v", err)
	}
	if _, err := manager.Consume(reservation, owner(request.Key.TSGeneration), snapshot, manager.clock.NowUnix()); err != nil {
		t.Fatalf("Consume: %v", err)
	}
	if err := manager.ValidateInvariants(); err != nil {
		t.Fatalf("invariants after consume: %v", err)
	}
	if _, err := manager.Acquire(context.Background(), request); !errors.Is(err, ErrInvalidTransition) {
		t.Fatalf("duplicate consumed request = %v, want ErrInvalidTransition", err)
	}
	if got := provider.calls(); got != 1 {
		t.Fatalf("provider calls after consumed duplicate = %d, want 1", got)
	}
}

func TestReleasedQuarantinedAndInvalidatedCompletedRequestsBecomeTerminal(t *testing.T) {
	for _, terminalize := range []struct {
		name  string
		apply func(*Manager, Reservation, AcquireRequest) error
	}{
		{"release", func(manager *Manager, reservation Reservation, _ AcquireRequest) error {
			return manager.Release(reservation)
		}},
		{"quarantine", func(manager *Manager, reservation Reservation, request AcquireRequest) error {
			return manager.Quarantine(reservation, request.RequestID)
		}},
		{"invalidation", func(manager *Manager, reservation Reservation, _ AcquireRequest) error {
			return manager.InvalidateGrant(reservation.grant)
		}},
	} {
		t.Run(terminalize.name, func(t *testing.T) {
			provider, manager, request := coalesceFixture(t)
			provider.releaseOnce()
			reservation, err := manager.Acquire(context.Background(), request)
			if err != nil {
				t.Fatalf("Acquire: %v", err)
			}
			if err := terminalize.apply(manager, reservation, request); err != nil {
				t.Fatalf("terminalize: %v", err)
			}
			if err := manager.ValidateInvariants(); err != nil {
				t.Fatalf("invariants after %s: %v", terminalize.name, err)
			}
			if _, err := manager.Acquire(context.Background(), request); !errors.Is(err, ErrInvalidTransition) {
				t.Fatalf("duplicate after %s = %v, want ErrInvalidTransition", terminalize.name, err)
			}
			if got := provider.calls(); got != 1 {
				t.Fatalf("provider calls after %s duplicate = %d, want 1", terminalize.name, got)
			}
		})
	}
}

func mustSealCheckpointForTest(t testing.TB, claims CheckpointClaims) VerifiedCheckpoint {
	t.Helper()
	checkpoint, err := sealCheckpoint(claims, validLimits())
	if err != nil {
		t.Fatalf("seal test checkpoint: %v", err)
	}
	return checkpoint
}

func rawClaimsFromVerifiedForTest(checkpoint VerifiedCheckpoint) CheckpointClaims {
	return CheckpointClaims{
		SourceOperator: checkpoint.sourceOperator(),
		Profile:        checkpoint.profile(),
		Generation:     checkpoint.Generation(),
		IssuedAt:       checkpoint.issuedAt(),
		FreshUntil:     checkpoint.FreshUntil(),
		Digest:         checkpoint.Digest(),
		RevokedGrants:  checkpoint.revokedDigests(),
	}
}
