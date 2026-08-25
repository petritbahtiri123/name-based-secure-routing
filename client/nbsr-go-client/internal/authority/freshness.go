package authority

import (
	"bytes"
	"context"
	"errors"
	"sort"
)

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
		m.notify([]Event{{Kind: EventFreshnessRejected, Result: errorCode(err)}})
		return VerifiedCheckpoint{}, err
	}

	m.mu.Lock()
	now = m.clock.NowUnix()
	if !validUnixTime(now) {
		m.mu.Unlock()
		return VerifiedCheckpoint{}, ErrInvalidAuthority
	}
	if now >= checkpoint.FreshUntil() {
		m.mu.Unlock()
		m.notify([]Event{{Kind: EventFreshnessRejected, Result: CodeStaleFreshness}})
		return VerifiedCheckpoint{}, ErrStaleFreshness
	}
	if checkpoint.sourceOperator() != request.SourceOperator || checkpoint.profile() != request.Profile {
		m.mu.Unlock()
		m.notify([]Event{{Kind: EventFreshnessRejected, Result: CodeBindingMismatch}})
		return VerifiedCheckpoint{}, ErrBindingMismatch
	}
	events, publishErr := m.publishCheckpointLocked(checkpoint)
	m.mu.Unlock()
	m.notify(events)
	if publishErr != nil {
		return VerifiedCheckpoint{}, publishErr
	}
	return checkpoint, nil
}

func validateFreshnessRequest(request FreshnessRequest) error {
	if !validTextID(request.SourceOperator) || !validTextID(request.Profile) || request.DeviceID == ([32]byte{}) || request.DeviceGeneration == 0 || request.DeadlineUnix == 0 || !validUnixTime(request.DeadlineUnix) {
		return ErrInvalidAuthority
	}
	return nil
}

// sealCheckpoint is the sole constructor for usable checkpoint authority. It
// is deliberately private and is called only after CheckpointEvidenceVerifier
// returns successfully.
func sealCheckpoint(claims CheckpointClaims, limits Limits) (VerifiedCheckpoint, error) {
	if !validTextID(claims.SourceOperator) || !validTextID(claims.Profile) || claims.Generation == 0 || claims.IssuedAt >= claims.FreshUntil || !validUnixTime(claims.IssuedAt) || !validUnixTime(claims.FreshUntil) || claims.Digest == (CheckpointDigest{}) {
		return VerifiedCheckpoint{}, ErrInvalidAuthority
	}
	if claims.Generation == ^AuthorityGeneration(0) {
		return VerifiedCheckpoint{}, ErrGenerationRollback
	}
	revoked := append([]RouteGrantDigest(nil), claims.RevokedGrants...)
	sort.Slice(revoked, func(left, right int) bool { return bytes.Compare(revoked[left][:], revoked[right][:]) < 0 })
	unique := revoked[:0]
	for _, digest := range revoked {
		if digest == (RouteGrantDigest{}) {
			return VerifiedCheckpoint{}, ErrInvalidAuthority
		}
		if len(unique) == 0 || unique[len(unique)-1] != digest {
			unique = append(unique, digest)
		}
	}
	if len(unique) > limits.MaxCacheEntries {
		return VerifiedCheckpoint{}, ErrCacheCapacity
	}
	return VerifiedCheckpoint{seal: verifiedCheckpoint{
		sourceOperator: claims.SourceOperator,
		profile:        claims.Profile,
		generation:     claims.Generation,
		issuedAt:       claims.IssuedAt,
		freshUntil:     claims.FreshUntil,
		digest:         claims.Digest,
		revoked:        append([]RouteGrantDigest(nil), unique...),
	}}, nil
}

func (m *Manager) publishCheckpointLocked(candidate VerifiedCheckpoint) ([]Event, error) {
	if m.hasCheckpoint {
		current := m.checkpoint
		if current.sourceOperator() != candidate.sourceOperator() || current.profile() != candidate.profile() {
			return []Event{{Kind: EventFreshnessRejected, Result: CodeBindingMismatch}}, ErrBindingMismatch
		}
		if candidate.Generation() < m.generation || (candidate.Generation() == m.generation && candidate.Digest() != current.Digest()) {
			return []Event{{Kind: EventFreshnessRejected, Result: CodeGenerationRollback}}, ErrGenerationRollback
		}
		if candidate.Generation() == m.generation {
			return nil, nil
		}
	}
	m.checkpoint = candidate
	m.generation = candidate.Generation()
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
		{Kind: EventFreshnessAccepted},
		{Kind: EventGenerationAdvanced},
	}...), nil
}

func (m *Manager) requireFreshLocked(now uint64) ([]Event, error) {
	if !m.hasCheckpoint || now >= m.checkpoint.FreshUntil() {
		if m.hasCheckpoint && !m.freshnessExpired {
			m.freshnessExpired = true
			return []Event{{Kind: EventFreshnessExpired, Result: CodeStaleFreshness}}, ErrStaleFreshness
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
