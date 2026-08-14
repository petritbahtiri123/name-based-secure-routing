package authority

import (
	"bytes"
	"context"
	"errors"
	"sort"
)

type checkpointState struct {
	claims  CheckpointClaims
	revoked []RouteGrantDigest
}

// PublishFreshness verifies supplied checkpoint evidence and atomically makes
// the resulting checkpoint current. It deliberately never calls the provider:
// callers that need remote evidence must obtain it before this method.
func (m *Manager) PublishFreshness(ctx context.Context, request FreshnessRequest, supplied ProviderFreshness) (VerifiedCheckpoint, error) {
	if m == nil || ctx == nil {
		return VerifiedCheckpoint{}, ErrInvalidAuthority
	}
	if err := validateFreshnessRequest(request); err != nil {
		return VerifiedCheckpoint{}, err
	}
	if supplied.SourceOperator != request.SourceOperator || supplied.Profile != request.Profile {
		return VerifiedCheckpoint{}, ErrBindingMismatch
	}
	freshness, err := copyProviderFreshness(supplied, m.limits)
	if err != nil {
		return VerifiedCheckpoint{}, err
	}
	now := m.clock.NowUnix()
	if !validUnixTime(now) {
		return VerifiedCheckpoint{}, ErrInvalidAuthority
	}
	claims, err := m.checkpointVerifier.VerifyFreshnessEvidence(ctx, freshness, request, now)
	if err != nil {
		m.notify([]Event{{Kind: EventFreshnessRejected, Result: errorCode(err)}})
		return VerifiedCheckpoint{}, typedFreshnessError(err)
	}
	checkpoint, err := sealCheckpoint(claims, m.limits)
	if err != nil {
		m.notify([]Event{{Kind: EventFreshnessRejected, AuthorityGeneration: claims.Generation, Result: errorCode(err)}})
		return VerifiedCheckpoint{}, err
	}

	m.mu.Lock()
	now = m.clock.NowUnix()
	if !validUnixTime(now) {
		m.mu.Unlock()
		return VerifiedCheckpoint{}, ErrInvalidAuthority
	}
	if now >= checkpoint.claims.FreshUntil {
		m.mu.Unlock()
		m.notify([]Event{{Kind: EventFreshnessRejected, AuthorityGeneration: checkpoint.claims.Generation, Result: CodeStaleFreshness}})
		return VerifiedCheckpoint{}, ErrStaleFreshness
	}
	if checkpoint.claims.SourceOperator != request.SourceOperator || checkpoint.claims.Profile != request.Profile {
		m.mu.Unlock()
		m.notify([]Event{{Kind: EventFreshnessRejected, AuthorityGeneration: checkpoint.claims.Generation, Result: CodeBindingMismatch}})
		return VerifiedCheckpoint{}, ErrBindingMismatch
	}
	events, publishErr := m.publishCheckpointLocked(checkpoint)
	m.mu.Unlock()
	m.notify(events)
	if publishErr != nil {
		return VerifiedCheckpoint{}, publishErr
	}
	return VerifiedCheckpoint{seal: verifiedCheckpoint{}}, nil
}

func validateFreshnessRequest(request FreshnessRequest) error {
	if !validTextID(request.SourceOperator) || !validTextID(request.Profile) || request.DeviceID == ([32]byte{}) || request.DeviceGeneration == 0 || request.DeadlineUnix == 0 || !validUnixTime(request.DeadlineUnix) {
		return ErrInvalidAuthority
	}
	return nil
}

func sealCheckpoint(claims CheckpointClaims, limits Limits) (checkpointState, error) {
	if !validTextID(claims.SourceOperator) || !validTextID(claims.Profile) || claims.Generation == 0 || claims.IssuedAt >= claims.FreshUntil || !validUnixTime(claims.IssuedAt) || !validUnixTime(claims.FreshUntil) || claims.Digest == (CheckpointDigest{}) {
		return checkpointState{}, ErrInvalidAuthority
	}
	if claims.Generation == ^AuthorityGeneration(0) {
		return checkpointState{}, ErrGenerationRollback
	}
	revoked := append([]RouteGrantDigest(nil), claims.RevokedGrants...)
	sort.Slice(revoked, func(left, right int) bool { return bytes.Compare(revoked[left][:], revoked[right][:]) < 0 })
	unique := revoked[:0]
	for _, digest := range revoked {
		if digest == (RouteGrantDigest{}) {
			return checkpointState{}, ErrInvalidAuthority
		}
		if len(unique) == 0 || unique[len(unique)-1] != digest {
			unique = append(unique, digest)
		}
	}
	if len(unique) > limits.MaxCacheEntries {
		return checkpointState{}, ErrCacheCapacity
	}
	claims.RevokedGrants = append([]RouteGrantDigest(nil), unique...)
	return checkpointState{claims: claims, revoked: append([]RouteGrantDigest(nil), unique...)}, nil
}

func (m *Manager) publishCheckpointLocked(candidate checkpointState) ([]Event, error) {
	if m.hasCheckpoint {
		current := m.checkpoint.claims
		if current.SourceOperator != candidate.claims.SourceOperator || current.Profile != candidate.claims.Profile {
			return []Event{{Kind: EventFreshnessRejected, AuthorityGeneration: candidate.claims.Generation, Result: CodeBindingMismatch}}, ErrBindingMismatch
		}
		if candidate.claims.Generation < m.generation || (candidate.claims.Generation == m.generation && candidate.claims.Digest != current.Digest) {
			return []Event{{Kind: EventFreshnessRejected, AuthorityGeneration: candidate.claims.Generation, Result: CodeGenerationRollback}}, ErrGenerationRollback
		}
		if candidate.claims.Generation == m.generation {
			return nil, nil
		}
	}
	m.checkpoint = candidate
	m.generation = candidate.claims.Generation
	m.invalidateRequestGenerationsLocked()
	pendingEvents := make([]Event, 0)
	for _, call := range m.pending {
		for _, record := range call.records {
			if m.requests[record.key] != record {
				call.abandoned = true
				call.cancel()
				pendingEvents = append(pendingEvents, m.finishPendingLocked(call, Reservation{}, ErrStaleGeneration)...)
				break
			}
		}
	}
	m.hasCheckpoint = true
	m.freshnessExpired = false
	return append(pendingEvents, []Event{
		{Kind: EventFreshnessAccepted, AuthorityGeneration: candidate.claims.Generation},
		{Kind: EventGenerationAdvanced, AuthorityGeneration: candidate.claims.Generation},
	}...), nil
}

func (m *Manager) requireFreshLocked(now uint64) ([]Event, error) {
	if !m.hasCheckpoint || now >= m.checkpoint.claims.FreshUntil {
		if m.hasCheckpoint && !m.freshnessExpired {
			m.freshnessExpired = true
			return []Event{{Kind: EventFreshnessExpired, AuthorityGeneration: m.generation, Result: CodeStaleFreshness}}, ErrStaleFreshness
		}
		return nil, ErrStaleFreshness
	}
	return nil, nil
}

func typedFreshnessError(err error) error {
	var typed *AuthorityError
	if errors.As(err, &typed) {
		return typed
	}
	return ErrInvalidAuthority
}

func errorCode(err error) ErrorCode {
	if typed, ok := err.(*AuthorityError); ok {
		return typed.Code
	}
	return CodeInvalidAuthority
}
