package authority

import (
	"bytes"
	"context"
	"errors"
	"testing"
)

func TestFloorStoresHigherAndCopiesEvidence(t *testing.T) {
	store := NewMemoryGenerationFloorStore(32)
	floor := testFloor(7)
	if err := store.StoreHigher(context.Background(), floor); err != nil {
		t.Fatal(err)
	}
	floor.SignedEvidence[0] ^= 0xff
	got, err := store.Load(context.Background(), "source-a", "profile-a")
	if err != nil {
		t.Fatal(err)
	}
	if got.Generation != 7 || got.Checkpoint != testCheckpoint(7) || !bytes.Equal(got.SignedEvidence, []byte("floor-7")) {
		t.Fatalf("stored floor = %#v", got)
	}
	got.SignedEvidence[0] ^= 0xff
	again, err := store.Load(context.Background(), "source-a", "profile-a")
	if err != nil || !bytes.Equal(again.SignedEvidence, []byte("floor-7")) {
		t.Fatalf("defensive Load copy = %#v, %v", again, err)
	}
	if err := store.StoreHigher(context.Background(), testFloor(7)); err != nil {
		t.Fatalf("equal identical floor = %v", err)
	}
	conflict := testFloor(7)
	conflict.SignedEvidence = []byte("different")
	if err := store.StoreHigher(context.Background(), conflict); !errors.Is(err, ErrFloorInvalid) {
		t.Fatalf("equal conflicting floor error = %v, want ErrFloorInvalid", err)
	}
	if err := store.StoreHigher(context.Background(), testFloor(6)); !errors.Is(err, ErrFloorInvalid) {
		t.Fatalf("lower floor error = %v, want ErrFloorInvalid", err)
	}
}

func TestFloorRejectsMalformedOversizedAndWrongBinding(t *testing.T) {
	store := NewMemoryGenerationFloorStore(7)
	for _, floor := range []SignedGenerationFloor{
		{},
		{SourceOperator: "source-a", Profile: "profile-a", Generation: 1, Checkpoint: testCheckpoint(1)},
		{SourceOperator: "source-a", Profile: "profile-a", Generation: 1, SignedEvidence: []byte("evidence")},
		{SourceOperator: "source-a", Profile: "profile-a", Generation: 1, Checkpoint: testCheckpoint(1), SignedEvidence: []byte("too-long")},
	} {
		if err := store.StoreHigher(context.Background(), floor); !errors.Is(err, ErrFloorInvalid) {
			t.Fatalf("invalid floor %#v error = %v, want ErrFloorInvalid", floor, err)
		}
	}
	if _, err := store.Load(context.Background(), "", "profile-a"); !errors.Is(err, ErrFloorInvalid) {
		t.Fatalf("empty source error = %v, want ErrFloorInvalid", err)
	}
	if _, err := store.Load(context.Background(), "source-a", ""); !errors.Is(err, ErrFloorInvalid) {
		t.Fatalf("empty profile error = %v, want ErrFloorInvalid", err)
	}
	if _, err := store.Load(context.Background(), "source-a", "profile-a"); !errors.Is(err, ErrFloorNotFound) {
		t.Fatalf("missing floor error = %v, want ErrFloorNotFound", err)
	}
	if err := store.StoreHigher(context.Background(), testFloor(1)); err != nil {
		t.Fatal(err)
	}
	if _, err := store.Load(context.Background(), "source-b", "profile-a"); !errors.Is(err, ErrFloorNotFound) {
		t.Fatalf("wrong source error = %v, want ErrFloorNotFound", err)
	}
	if _, err := store.Load(context.Background(), "source-a", "profile-b"); !errors.Is(err, ErrFloorNotFound) {
		t.Fatalf("wrong profile error = %v, want ErrFloorNotFound", err)
	}
}

func TestFloorLossAfterPersistenceIsInvalidNotPristine(t *testing.T) {
	store := NewMemoryGenerationFloorStore(32)
	if err := store.StoreHigher(context.Background(), testFloor(9)); err != nil {
		t.Fatal(err)
	}
	store.mu.Lock()
	delete(store.floors, floorKey{sourceOperator: "source-a", profile: "profile-a"})
	store.mu.Unlock()
	if _, err := store.Load(context.Background(), "source-a", "profile-a"); !errors.Is(err, ErrFloorInvalid) {
		t.Fatalf("lost floor error = %v, want ErrFloorInvalid", err)
	}
	if err := store.StoreHigher(context.Background(), testFloor(10)); !errors.Is(err, ErrFloorInvalid) {
		t.Fatalf("lost floor recovery error = %v, want ErrFloorInvalid", err)
	}
}

func testCheckpoint(generation AuthorityGeneration) CheckpointDigest {
	var checkpoint CheckpointDigest
	checkpoint[0] = byte(generation)
	return checkpoint
}

func testFloor(generation AuthorityGeneration) SignedGenerationFloor {
	return SignedGenerationFloor{
		SourceOperator: "source-a",
		Profile:        "profile-a",
		Generation:     generation,
		Checkpoint:     testCheckpoint(generation),
		SignedEvidence: []byte("floor-" + string(rune('0'+generation))),
	}
}
