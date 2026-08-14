package authority

import (
	"bytes"
	"context"
	"sync"
)

const maxMemoryFloorEvidenceBytes = 64 * 1024

type FloorErrorCode uint8

const (
	FloorNotFound FloorErrorCode = iota + 1
	FloorInvalid
)

type FloorError struct{ Code FloorErrorCode }

func (e *FloorError) Error() string {
	if e == nil {
		return "<nil>"
	}
	if e.Code == FloorNotFound {
		return "generation floor not found"
	}
	return "invalid generation floor"
}

func (e *FloorError) Is(target error) bool {
	t, ok := target.(*FloorError)
	return ok && e != nil && t != nil && e.Code == t.Code
}

var (
	ErrFloorNotFound = &FloorError{Code: FloorNotFound}
	ErrFloorInvalid  = &FloorError{Code: FloorInvalid}
)

type floorKey struct {
	sourceOperator string
	profile        string
}

// MemoryGenerationFloorStore is deterministic fixture/test storage. It makes
// no filesystem, hardware, or production durability claim.
type MemoryGenerationFloorStore struct {
	mu          sync.RWMutex
	maxEvidence int
	floors      map[floorKey]SignedGenerationFloor
}

func NewMemoryGenerationFloorStore(maxEvidence int) *MemoryGenerationFloorStore {
	if maxEvidence <= 0 || maxEvidence > maxMemoryFloorEvidenceBytes {
		maxEvidence = maxMemoryFloorEvidenceBytes
	}
	return &MemoryGenerationFloorStore{maxEvidence: maxEvidence, floors: make(map[floorKey]SignedGenerationFloor)}
}

func (s *MemoryGenerationFloorStore) Load(ctx context.Context, sourceOperator, profile string) (SignedGenerationFloor, error) {
	if s == nil || ctx == nil || !validTextID(sourceOperator) || !validTextID(profile) {
		return SignedGenerationFloor{}, ErrFloorInvalid
	}
	s.mu.RLock()
	floor, ok := s.floors[floorKey{sourceOperator: sourceOperator, profile: profile}]
	s.mu.RUnlock()
	if !ok {
		return SignedGenerationFloor{}, ErrFloorNotFound
	}
	return copySignedGenerationFloor(floor, s.maxEvidence)
}

func (s *MemoryGenerationFloorStore) StoreHigher(ctx context.Context, candidate SignedGenerationFloor) error {
	if s == nil || ctx == nil {
		return ErrFloorInvalid
	}
	candidate, err := copySignedGenerationFloor(candidate, s.maxEvidence)
	if err != nil {
		return err
	}
	key := floorKey{sourceOperator: candidate.SourceOperator, profile: candidate.Profile}
	s.mu.Lock()
	current, exists := s.floors[key]
	if exists {
		switch {
		case candidate.Generation < current.Generation:
			s.mu.Unlock()
			return ErrFloorInvalid
		case candidate.Generation == current.Generation && !sameSignedGenerationFloor(candidate, current):
			s.mu.Unlock()
			return ErrFloorInvalid
		case candidate.Generation == current.Generation:
			s.mu.Unlock()
			return nil
		}
	}
	s.floors[key] = candidate
	s.mu.Unlock()
	return nil
}

func copySignedGenerationFloor(floor SignedGenerationFloor, maxEvidence int) (SignedGenerationFloor, error) {
	if !validTextID(floor.SourceOperator) || !validTextID(floor.Profile) || floor.Generation == 0 || floor.Generation == ^AuthorityGeneration(0) || floor.Checkpoint == (CheckpointDigest{}) || len(floor.SignedEvidence) == 0 || len(floor.SignedEvidence) > maxEvidence {
		return SignedGenerationFloor{}, ErrFloorInvalid
	}
	floor.SignedEvidence = append([]byte(nil), floor.SignedEvidence...)
	return floor, nil
}

func sameSignedGenerationFloor(left, right SignedGenerationFloor) bool {
	return left.SourceOperator == right.SourceOperator && left.Profile == right.Profile && left.Generation == right.Generation && left.Checkpoint == right.Checkpoint && bytes.Equal(left.SignedEvidence, right.SignedEvidence)
}
