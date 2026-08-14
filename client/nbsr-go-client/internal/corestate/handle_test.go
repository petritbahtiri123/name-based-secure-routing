package corestate

import (
	"errors"
	"math"
	"testing"
)

func newSmallStore(t *testing.T) *Store {
	t.Helper()
	limits := validLimits()
	limits.MaxGenerations = 2
	s, err := NewStore(limits, fakeClock{}, nil)
	if err != nil {
		t.Fatal(err)
	}
	return s
}

func mustOpen(t *testing.T, s *Store, generation TSGeneration) {
	t.Helper()
	if err := s.OpenGeneration(generation); err != nil {
		t.Fatal(err)
	}
}

func allocateHandleForTest(t *testing.T, s *Store, generation TSGeneration, commit bool) ServiceHandle {
	t.Helper()
	s.mu.Lock()
	defer s.mu.Unlock()
	handle, err := s.allocateHandleLocked(generation)
	if err != nil {
		t.Fatal(err)
	}
	if commit {
		if err := s.commitHandleLocked(generation, handle); err != nil {
			t.Fatal(err)
		}
	}
	return handle
}

func TestHandlesNeverReuseWithinGeneration(t *testing.T) {
	s := newSmallStore(t)
	mustOpen(t, s, 7)
	a := allocateHandleForTest(t, s, 7, true)
	b := allocateHandleForTest(t, s, 7, true)
	if a != 1 || b != 2 {
		t.Fatalf("handles = %d, %d; want 1, 2", a, b)
	}
}

func TestGenerationsHaveIndependentNamespaces(t *testing.T) {
	s := newSmallStore(t)
	mustOpen(t, s, 7)
	mustOpen(t, s, 8)
	if got := allocateHandleForTest(t, s, 7, true); got != 1 {
		t.Fatalf("generation 7 handle = %d, want 1", got)
	}
	if got := allocateHandleForTest(t, s, 8, true); got != 1 {
		t.Fatalf("generation 8 handle = %d, want 1", got)
	}
}

func TestGenerationRejectsZero(t *testing.T) {
	s := newSmallStore(t)
	if err := s.OpenGeneration(0); !errors.Is(err, ErrGenerationClosed) {
		t.Fatalf("OpenGeneration(0) error = %v, want ErrGenerationClosed", err)
	}
}

func TestGenerationRejectsDuplicateOpen(t *testing.T) {
	s := newSmallStore(t)
	mustOpen(t, s, 7)
	if err := s.OpenGeneration(7); !errors.Is(err, ErrGenerationClosed) {
		t.Fatalf("duplicate open error = %v, want ErrGenerationClosed", err)
	}
}

func TestGenerationRejectsClosedReopen(t *testing.T) {
	s := newSmallStore(t)
	mustOpen(t, s, 7)
	if err := s.CloseGeneration(7); err != nil {
		t.Fatal(err)
	}
	if err := s.OpenGeneration(7); !errors.Is(err, ErrGenerationClosed) {
		t.Fatalf("closed reopen error = %v, want ErrGenerationClosed", err)
	}
	if err := s.OpenGeneration(6); !errors.Is(err, ErrGenerationClosed) {
		t.Fatalf("older open error = %v, want ErrGenerationClosed", err)
	}
}

func TestHandleMaxUint32SucceedsOnce(t *testing.T) {
	s := newSmallStore(t)
	mustOpen(t, s, 7)
	s.mu.Lock()
	state := s.generations[7]
	state.next = ServiceHandle(math.MaxUint32)
	s.generations[7] = state
	s.mu.Unlock()

	if got := allocateHandleForTest(t, s, 7, true); got != ServiceHandle(math.MaxUint32) {
		t.Fatalf("handle = %d, want MaxUint32", got)
	}
}

func TestHandleOverflowFailsClosed(t *testing.T) {
	s := newSmallStore(t)
	mustOpen(t, s, 7)
	s.mu.Lock()
	state := s.generations[7]
	state.next = ServiceHandle(math.MaxUint32)
	s.generations[7] = state
	handle, err := s.allocateHandleLocked(7)
	if err == nil {
		err = s.commitHandleLocked(7, handle)
	}
	_, overflowErr := s.allocateHandleLocked(7)
	s.mu.Unlock()
	if err != nil {
		t.Fatal(err)
	}
	if !errors.Is(overflowErr, ErrHandleExhausted) {
		t.Fatalf("overflow error = %v, want ErrHandleExhausted", overflowErr)
	}
}

func TestHandleFailedInsertDoesNotConsume(t *testing.T) {
	s := newSmallStore(t)
	mustOpen(t, s, 7)
	first := allocateHandleForTest(t, s, 7, false)
	second := allocateHandleForTest(t, s, 7, false)
	if first != 1 || second != first {
		t.Fatalf("uncommitted candidates = %d, %d; want 1, 1", first, second)
	}
	if committed := allocateHandleForTest(t, s, 7, true); committed != first {
		t.Fatalf("committed handle = %d, want %d", committed, first)
	}
}

func TestHandleCommitRejectsStaleCandidate(t *testing.T) {
	s := newSmallStore(t)
	mustOpen(t, s, 7)
	s.mu.Lock()
	err := s.commitHandleLocked(7, 2)
	s.mu.Unlock()
	if !errors.Is(err, ErrInvalidTransition) {
		t.Fatalf("stale commit error = %v, want ErrInvalidTransition", err)
	}
	if got := allocateHandleForTest(t, s, 7, false); got != 1 {
		t.Fatalf("next handle = %d, want 1", got)
	}
}

func TestGenerationCapacityBelow(t *testing.T) {
	s := newSmallStore(t)
	mustOpen(t, s, 7)
}

func TestGenerationCapacityExact(t *testing.T) {
	s := newSmallStore(t)
	mustOpen(t, s, 7)
	mustOpen(t, s, 8)
}

func TestGenerationCapacityAbove(t *testing.T) {
	s := newSmallStore(t)
	mustOpen(t, s, 7)
	mustOpen(t, s, 8)
	if err := s.OpenGeneration(9); !errors.Is(err, ErrCapacityExceeded) {
		t.Fatalf("third open error = %v, want ErrCapacityExceeded", err)
	}
	if s.highestGeneration != 8 {
		t.Fatalf("highest generation = %d, want 8", s.highestGeneration)
	}
}

func TestGenerationCloseRejectsNonemptyWithoutDeletingAllocator(t *testing.T) {
	s := newSmallStore(t)
	mustOpen(t, s, 7)
	s.services[serviceKey{generation: 7, handle: 1}] = ServiceSnapshot{}
	if err := s.CloseGeneration(7); !errors.Is(err, ErrInvalidTransition) {
		t.Fatalf("nonempty close error = %v, want ErrInvalidTransition", err)
	}
	if got := allocateHandleForTest(t, s, 7, false); got != 1 {
		t.Fatalf("allocator was changed after rejected close: got %d, want 1", got)
	}
}

func TestGenerationCloseReleasesCapacity(t *testing.T) {
	s := newSmallStore(t)
	mustOpen(t, s, 7)
	mustOpen(t, s, 8)
	if err := s.CloseGeneration(7); err != nil {
		t.Fatal(err)
	}
	mustOpen(t, s, 9)
}

func TestHandleRejectsClosedGeneration(t *testing.T) {
	s := newSmallStore(t)
	mustOpen(t, s, 7)
	if err := s.CloseGeneration(7); err != nil {
		t.Fatal(err)
	}
	s.mu.Lock()
	_, err := s.allocateHandleLocked(7)
	s.mu.Unlock()
	if !errors.Is(err, ErrGenerationClosed) {
		t.Fatalf("closed generation allocation error = %v, want ErrGenerationClosed", err)
	}
}
