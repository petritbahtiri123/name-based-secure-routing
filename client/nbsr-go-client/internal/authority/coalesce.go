package authority

import (
	"context"
	"errors"
	"math"
)

type pendingOperation uint8

const (
	pendingAcquire pendingOperation = iota + 1
	pendingRenew
)

// pendingKey includes the complete authenticated authority scope. Renewals
// additionally include the consumed-grant digest; an Acquire can never join a
// Renew, even when every AuthorityKey field is identical.
type pendingKey struct {
	authority AuthorityKey
	operation pendingOperation
	previous  RouteGrantDigest
}

type pendingResult struct {
	reservation Reservation
	err         error
}

type pendingCall struct {
	key             pendingKey
	acquire         AcquireRequest
	renew           RenewRequest
	checkpoint      VerifiedCheckpoint
	logicalBytes    uint64
	waiters         int
	abandoned       bool
	finished        bool
	result          pendingResult
	done            chan struct{}
	providerContext context.Context
	cancel          context.CancelFunc
	records         []*requestRecord
}

func (m *Manager) Acquire(ctx context.Context, request AcquireRequest) (Reservation, error) {
	if m == nil || ctx == nil {
		return Reservation{}, ErrInvalidAuthority
	}
	request, err := validateAcquireRequest(request, m.limits)
	if err != nil {
		return Reservation{}, err
	}
	return m.startOrJoin(ctx, pendingKey{authority: request.Key, operation: pendingAcquire}, request, RenewRequest{})
}

func (m *Manager) Renew(ctx context.Context, request RenewRequest) (Reservation, error) {
	if m == nil || ctx == nil || request.PreviousGrant == (RouteGrantDigest{}) {
		return Reservation{}, ErrInvalidAuthority
	}
	acquire, err := validateAcquireRequest(request.AcquireRequest, m.limits)
	if err != nil {
		return Reservation{}, err
	}
	request.AcquireRequest = acquire
	key := pendingKey{authority: acquire.Key, operation: pendingRenew, previous: request.PreviousGrant}
	return m.startOrJoin(ctx, key, acquire, request)
}

func (m *Manager) startOrJoin(ctx context.Context, key pendingKey, acquire AcquireRequest, renew RenewRequest) (Reservation, error) {
	if err := ctx.Err(); err != nil {
		return Reservation{}, err
	}
	now := m.clock.NowUnix()
	if !validUnixTime(now) || now >= acquire.DeadlineUnix {
		return Reservation{}, ErrExpired
	}
	m.mu.Lock()
	if m.closed {
		m.mu.Unlock()
		return Reservation{}, ErrClosed
	}
	events, err := m.requireFreshLocked(now)
	if err != nil {
		m.mu.Unlock()
		m.notify(events)
		return Reservation{}, err
	}
	requestKey := requestKey{deviceID: acquire.Key.DeviceID, deviceGeneration: acquire.Key.DeviceGeneration, operation: key.operation, id: acquire.RequestID}
	record, _, err := m.beginRequestLocked(requestKey, canonicalRequestDigest(key, acquire, renew), acquire.DeadlineUnix, now)
	if err != nil {
		m.mu.Unlock()
		m.notify(events)
		return Reservation{}, err
	}
	if record.snapshot.Status == RequestComplete {
		reservation, err := m.completedReservationLocked(record)
		m.mu.Unlock()
		m.notify(events)
		return reservation, err
	}
	if key.operation == pendingAcquire {
		if entry := m.cache[key.authority]; entry != nil && entry.state == cacheAvailable {
			var validationEvents []Event
			validationEvents, err = m.validateAvailableLocked(entry, now)
			events = append(events, validationEvents...)
			if err == nil {
				var cacheEvents []Event
				reservation, cacheEvents, reserveErr := m.reserveExistingLocked(entry)
				events = append(events, cacheEvents...)
				if reserveErr == nil {
					err = m.finishRequestLocked(record, reservation.grant, reservation)
				} else {
					err = reserveErr
				}
				m.mu.Unlock()
				m.notify(events)
				return reservation, err
			}
			m.mu.Unlock()
			m.notify(events)
			return Reservation{}, err
		}
	}
	if err = m.pendingScopeCurrentLocked(key.authority); err != nil {
		m.mu.Unlock()
		m.notify(events)
		return Reservation{}, err
	}
	if existing := m.pending[key]; existing != nil {
		if existing.waiters >= m.limits.MaxWaitersPerPending {
			m.mu.Unlock()
			m.notify(events)
			return Reservation{}, ErrWaiterCapacity
		}
		existing.waiters++
		if !callHasRequestRecord(existing, record) {
			existing.records = append(existing.records, record)
		}
		events = append(events, Event{Kind: EventAcquireCoalesced})
		m.mu.Unlock()
		m.notify(events)
		return m.waitPending(ctx, existing)
	}
	logicalBytes, err := pendingLogicalBytes(key, acquire)
	if err == nil && (len(m.pending) >= m.limits.MaxPending || logicalBytes > m.limits.MaxPendingBytes-m.pendingBytes) {
		err = ErrPendingCapacity
	}
	if err != nil {
		m.mu.Unlock()
		m.notify(events)
		return Reservation{}, err
	}
	providerContext, cancel := context.WithCancel(context.Background())
	call := &pendingCall{key: key, acquire: acquire, renew: renew, checkpoint: m.checkpoint, logicalBytes: logicalBytes, waiters: 1, done: make(chan struct{}), providerContext: providerContext, cancel: cancel, records: []*requestRecord{record}}
	m.pending[key] = call
	m.pendingBytes += logicalBytes
	if key.operation == pendingRenew {
		events = append(events, Event{Kind: EventRenewalRequested})
	} else {
		events = append(events, Event{Kind: EventAcquireRequested})
	}
	m.mu.Unlock()
	m.notify(events)
	// One bounded worker per pending provider operation; waiters only select on
	// the shared completion channel and never create goroutines.
	go m.runPending(call)
	return m.waitPending(ctx, call)
}

func callHasRequestRecord(call *pendingCall, record *requestRecord) bool {
	for _, candidate := range call.records {
		if candidate == record {
			return true
		}
	}
	return false
}

func (m *Manager) waitPending(ctx context.Context, call *pendingCall) (Reservation, error) {
	select {
	case <-call.done:
		return call.result.reservation, call.result.err
	default:
	}
	select {
	case <-call.done:
		return call.result.reservation, call.result.err
	case <-ctx.Done():
		cancelProvider := false
		var events []Event
		m.mu.Lock()
		if call.finished {
			result := call.result
			m.mu.Unlock()
			return result.reservation, result.err
		} else {
			call.waiters--
			if call.waiters == 0 {
				call.abandoned = true
				cancelProvider = true
			}
		}
		m.mu.Unlock()
		m.notify(events)
		if cancelProvider {
			call.cancel()
		}
		return Reservation{}, ctx.Err()
	}
}

func (m *Manager) runPending(call *pendingCall) {
	candidate, err := m.invokeProvider(call.providerContext, call.key.operation, call.acquire, call.renew)
	if err != nil {
		m.finishPending(call, Reservation{}, providerError(call, err))
		return
	}
	// The frozen ACP result carries the independently signed RouteGrant bytes
	// but deliberately does not duplicate the client's current checkpoint.
	// Bind an omitted transport field to the sealed checkpoint captured when
	// this pending call began; explicit non-zero provider values still undergo
	// the existing mismatch check in VerifyRouteGrant.
	if candidate.Checkpoint == (CheckpointDigest{}) {
		candidate.Checkpoint = call.checkpoint.Digest()
	}
	candidate, err = copyProviderGrant(candidate, m.limits)
	if err != nil {
		m.finishPending(call, Reservation{}, err)
		return
	}
	now := m.clock.NowUnix()
	if !validUnixTime(now) {
		m.finishPending(call, Reservation{}, ErrInvalidAuthority)
		return
	}
	authority, err := m.verifier.VerifyRouteGrant(call.providerContext, candidate, VerificationContext{Key: call.acquire.Key, Intent: call.acquire.Intent, Checkpoint: call.checkpoint, NowUnix: now})
	if err != nil {
		m.finishPending(call, Reservation{}, err)
		return
	}
	m.commitPending(call, authority)
}

func (m *Manager) commitPending(call *pendingCall, authority VerifiedAuthority) {
	m.mu.Lock()
	if call.finished {
		m.mu.Unlock()
		return
	}
	var events []Event
	var reservation Reservation
	var err error
	if m.closed {
		err = ErrClosed
	} else if call.abandoned {
		err = ErrRequestAmbiguous
	} else {
		now := m.clock.NowUnix()
		if !validUnixTime(now) {
			err = ErrInvalidAuthority
		} else if now >= call.acquire.DeadlineUnix {
			err = ErrExpired
		} else {
			events, err = m.requireFreshLocked(now)
			if err == nil {
				err = m.pendingScopeCurrentLocked(call.key.authority)
			}
			if err == nil && (authority.Key() != call.key.authority || authority.Checkpoint() != call.checkpoint.Digest() || authority.AuthorityGeneration() != call.checkpoint.Generation()) {
				err = ErrStaleGeneration
			}
			if err == nil && call.key.operation == pendingRenew {
				var reserveEvents []Event
				reservation, reserveEvents, err = m.replaceRenewedLocked(call.key.previous, authority, now)
				events = append(events, reserveEvents...)
			} else if err == nil {
				var reserveEvents []Event
				reservation, reserveEvents, err = m.reserveVerifiedLocked(authority, now)
				events = append(events, reserveEvents...)
			}
		}
	}
	events = append(events, m.finishPendingLocked(call, reservation, err)...)
	m.mu.Unlock()
	m.notify(events)
}

func (m *Manager) finishPending(call *pendingCall, reservation Reservation, err error) {
	m.mu.Lock()
	if call.finished {
		m.mu.Unlock()
		return
	}
	if m.closed {
		err = ErrClosed
	} else if call.abandoned {
		err = ErrRequestAmbiguous
	}
	events := m.finishPendingLocked(call, reservation, err)
	m.mu.Unlock()
	m.notify(events)
}

func (m *Manager) finishPendingLocked(call *pendingCall, reservation Reservation, err error) []Event {
	if call.finished {
		return nil
	}
	if current := m.pending[call.key]; current == call {
		delete(m.pending, call.key)
		m.pendingBytes -= call.logicalBytes
	}
	call.finished = true
	call.result = pendingResult{reservation: reservation, err: err}
	var requestEvents []Event
	for _, record := range call.records {
		if err == nil {
			if finishErr := m.finishRequestLocked(record, reservation.grant, reservation); finishErr != nil {
				err = finishErr
				call.result.err = err
			}
		} else if errors.Is(err, ErrRequestAmbiguous) {
			ambiguousEvents, _ := m.markAmbiguousLocked(record)
			requestEvents = append(requestEvents, ambiguousEvents...)
		} else {
			m.removeRequestLocked(record)
		}
	}
	close(call.done)
	if call.key.operation == pendingRenew {
		return append(requestEvents, Event{Kind: EventRenewalResult, Result: errorCode(err)})
	}
	return append(requestEvents, Event{Kind: EventAcquireResult, Result: errorCode(err)})
}

func (m *Manager) pendingScopeCurrentLocked(key AuthorityKey) error {
	if !m.hasCheckpoint || key.AuthorityGeneration != m.generation || m.checkpoint.sourceOperator() != key.SourceOperator || m.checkpoint.profile() != key.Profile || m.checkpoint.Generation() != key.AuthorityGeneration {
		return ErrStaleGeneration
	}
	return nil
}

func (m *Manager) Close() error {
	if m == nil {
		return ErrInvalidAuthority
	}
	m.mu.Lock()
	if m.closed {
		m.mu.Unlock()
		return ErrClosed
	}
	m.closed = true
	pending := make([]*pendingCall, 0, len(m.pending))
	for _, call := range m.pending {
		call.abandoned = true
		pending = append(pending, call)
	}
	var events []Event
	for _, call := range pending {
		events = append(events, m.finishPendingLocked(call, Reservation{}, ErrClosed)...)
	}
	m.mu.Unlock()
	for _, call := range pending {
		call.cancel()
	}
	m.notify(events)
	// Provider.Close is also a callback and runs only after waiters have been
	// released and the manager mutex is unlocked.
	return m.provider.Close()
}

func pendingLogicalBytes(key pendingKey, request AcquireRequest) (uint64, error) {
	// The charge covers every copied variable field plus a fixed discriminator,
	// fixed digests/integers, and the exact previous-grant digest.
	values := []string{key.authority.SourceOperator, key.authority.SourceEdge, key.authority.TargetOperator, key.authority.Profile, key.authority.Transport, request.Intent.ServiceIdentity, request.Intent.SourceOperator, request.Intent.SourceEdge, request.Intent.TargetOperator, request.Intent.Transport}
	bytes := uint64(len(request.Intent.Canonical))
	for _, edge := range request.Intent.TargetEdges {
		if uint64(len(edge)) > math.MaxUint64-bytes {
			return 0, ErrAccountingOverflow
		}
		bytes += uint64(len(edge))
	}
	for _, value := range values {
		if uint64(len(value)) > math.MaxUint64-bytes {
			return 0, ErrAccountingOverflow
		}
		bytes += uint64(len(value))
	}
	const fixed = uint64(2 + 32 + 32 + 32 + 32 + 32 + 32 + 32 + 32 + 32 + 16 + 16 + 16 + 16 + 8*7 + 2)
	if fixed > math.MaxUint64-bytes {
		return 0, ErrAccountingOverflow
	}
	return bytes + fixed, nil
}

func providerError(call *pendingCall, err error) error {
	if call.providerContext.Err() != nil {
		return ErrRequestAmbiguous
	}
	var semantic *VerifiedACPSemanticError
	if errors.As(err, &semantic) {
		return semantic
	}
	if typed, ok := err.(*AuthorityError); ok {
		return typed
	}
	return ErrProviderUnavailable
}
