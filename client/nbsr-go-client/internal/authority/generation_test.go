package authority

import (
	"context"
	"errors"
	"math"
	"testing"
)

func TestGenerationAdvanceWinsBeforeFinalCheck(t *testing.T) {
	t.Run("validation linearizes before publication", func(t *testing.T) {
		m := freshManager(t, checkpoint(7, 100, 200))
		snapshot, err := m.CaptureGeneration()
		if err != nil {
			t.Fatal(err)
		}
		verifier := &task4DelayedCheckpointVerifier{claims: checkpoint(8, 110, 210), started: make(chan struct{}), release: make(chan struct{})}
		m.checkpointVerifier = verifier
		published := make(chan error, 1)
		go func() {
			_, err := m.PublishFreshness(context.Background(), task4Request(), task4ProviderFreshness())
			published <- err
		}()
		<-verifier.started
		validated := make(chan error, 1)
		go func() { validated <- m.ValidateStillCurrent(snapshot) }()
		if err := <-validated; err != nil {
			t.Fatalf("validation before publication = %v, want nil", err)
		}
		close(verifier.release)
		if err := <-published; err != nil {
			t.Fatalf("publication = %v", err)
		}
	})

	t.Run("publication linearizes before validation", func(t *testing.T) {
		m := freshManager(t, checkpoint(7, 100, 200))
		snapshot, err := m.CaptureGeneration()
		if err != nil {
			t.Fatal(err)
		}
		observer := &task4BlockingGenerationObserver{seen: make(chan struct{}), release: make(chan struct{})}
		m.observer = observer
		m.checkpointVerifier.(*task4CheckpointVerifier).claims = checkpoint(8, 110, 210)
		published := make(chan error, 1)
		go func() {
			_, err := m.PublishFreshness(context.Background(), task4Request(), task4ProviderFreshness())
			published <- err
		}()
		<-observer.seen
		validated := make(chan error, 1)
		go func() { validated <- m.ValidateStillCurrent(snapshot) }()
		if err := <-validated; !errors.Is(err, ErrStaleGeneration) {
			t.Fatalf("validation after publication = %v, want ErrStaleGeneration", err)
		}
		close(observer.release)
		if err := <-published; err != nil {
			t.Fatalf("publication = %v", err)
		}
	})
}

type task4BlockingGenerationObserver struct {
	seen    chan struct{}
	release chan struct{}
}

func (observer *task4BlockingGenerationObserver) Observe(event Event) {
	if event.Kind != EventGenerationAdvanced {
		return
	}
	close(observer.seen)
	<-observer.release
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
