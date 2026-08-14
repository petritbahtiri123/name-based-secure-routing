package authority

import (
	"context"
	"errors"
	"math"
	"testing"
)

func TestGenerationAdvanceWinsBeforeFinalCheck(t *testing.T) {
	m := freshManager(t, checkpoint(7, 100, 200))
	snapshot, err := m.CaptureGeneration()
	if err != nil {
		t.Fatal(err)
	}
	publishCheckpoint(t, m, checkpoint(8, 110, 210))
	if err := m.ValidateStillCurrent(snapshot); !errors.Is(err, ErrStaleGeneration) {
		t.Fatalf("final check error = %v, want ErrStaleGeneration", err)
	}
}

func TestGenerationRejectsZeroLowerAndConflictingEqualCheckpoint(t *testing.T) {
	m := freshManager(t, checkpoint(7, 100, 200))
	m.checkpointVerifier.(*task4CheckpointVerifier).claims = checkpoint(0, 100, 200)
	if _, err := m.PublishFreshness(context.Background(), task4Request(), task4ProviderFreshness()); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("zero generation error = %v, want ErrInvalidAuthority", err)
	}
	for _, claims := range []CheckpointClaims{
		checkpoint(6, 100, 200),
		func() CheckpointClaims {
			value := checkpoint(7, 100, 201)
			value.Digest = CheckpointDigest{8}
			return value
		}(),
	} {
		m.checkpointVerifier.(*task4CheckpointVerifier).claims = claims
		if _, err := m.PublishFreshness(context.Background(), task4Request(), task4ProviderFreshness()); !errors.Is(err, ErrGenerationRollback) {
			t.Fatalf("claims %+v error = %v, want ErrGenerationRollback", claims, err)
		}
	}
}

func TestGenerationAcceptsIdenticalEqualCheckpointIdempotently(t *testing.T) {
	m := freshManager(t, checkpoint(7, 100, 200))
	if _, err := m.PublishFreshness(context.Background(), task4Request(), task4ProviderFreshness()); err != nil {
		t.Fatalf("idempotent publication: %v", err)
	}
	if got := m.observer.(*task4Observer).count(EventGenerationAdvanced); got != 1 {
		t.Fatalf("generation advances = %d, want 1", got)
	}
}

func TestGenerationRejectsMaximumValueToAvoidOverflow(t *testing.T) {
	m := freshManager(t, checkpoint(math.MaxUint64-1, 100, 200))
	m.checkpointVerifier.(*task4CheckpointVerifier).claims = checkpoint(math.MaxUint64, 101, 201)
	if _, err := m.PublishFreshness(context.Background(), task4Request(), task4ProviderFreshness()); !errors.Is(err, ErrGenerationRollback) {
		t.Fatalf("maximum generation error = %v, want ErrGenerationRollback", err)
	}
}

func TestFreshnessPrecedesStaleGeneration(t *testing.T) {
	m := freshManager(t, checkpoint(7, 100, 200))
	m.clock = task4Clock{now: 200}
	if err := m.ValidateStillCurrent(GenerationSnapshot{}); !errors.Is(err, ErrStaleFreshness) {
		t.Fatalf("error = %v, want ErrStaleFreshness", err)
	}
}

func publishCheckpoint(t *testing.T, manager *Manager, claims CheckpointClaims) {
	t.Helper()
	manager.checkpointVerifier.(*task4CheckpointVerifier).claims = claims
	if _, err := manager.PublishFreshness(context.Background(), task4Request(), task4ProviderFreshness()); err != nil {
		t.Fatal(err)
	}
}
