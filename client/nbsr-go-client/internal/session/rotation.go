package session

import (
	"context"
	"errors"
	"time"

	"nbsr.local/client/nbsr-go-client/internal/corestate"
)

type RotationTrigger uint8

const (
	RotationExplicit RotationTrigger = iota + 1
	RotationAuthorityReplacement
	RotationProofReplacement
	RotationReplayCapacity
	RotationTransportFailure
	RotationRevocation
)

func (trigger RotationTrigger) valid() bool {
	return trigger >= RotationExplicit && trigger <= RotationRevocation
}

func (trigger RotationTrigger) prohibitsNewWork() bool {
	return trigger >= RotationReplayCapacity
}

type RotationRequest struct {
	CurrentGeneration corestate.TSGeneration
	Replacement       TransportSessionSpec
	Trigger           RotationTrigger
}

type RotationResult struct {
	Previous TransportSessionSnapshot
	Current  TransportSessionSnapshot
	Trigger  RotationTrigger
}

type pendingRotation struct {
	done    chan struct{}
	waiters int
	request RotationRequest
	trigger RotationTrigger
	result  RotationResult
	err     error
	cancel  context.CancelFunc
}

func (manager *Manager) CurrentTransportSession(key ReuseKey) (TransportSessionSnapshot, error) {
	manager.mu.Lock()
	defer manager.mu.Unlock()
	for _, entry := range manager.byReuse[key] {
		if entry.snapshot.State == TransportCurrent {
			return entry.snapshot, nil
		}
	}
	return TransportSessionSnapshot{}, ErrGenerationNotCurrent
}

func (manager *Manager) EffectiveTrigger(key ReuseKey) RotationTrigger {
	manager.mu.Lock()
	defer manager.mu.Unlock()
	return manager.effectiveTriggers[key]
}

func (manager *Manager) RotateTransportSession(ctx context.Context, request RotationRequest) (RotationResult, error) {
	if ctx == nil || !request.Trigger.valid() || request.CurrentGeneration == 0 || request.Replacement.Generation == 0 || request.Replacement.Generation == request.CurrentGeneration {
		return RotationResult{}, ErrInvalidSession
	}
	authorityGeneration, err := manager.authority.Capture()
	if err != nil {
		return RotationResult{}, authorityError(err)
	}
	_, proof, err := manager.validateSessionSpec(request.Replacement)
	if err != nil {
		return RotationResult{}, err
	}
	if err := manager.authority.ValidateSession(request.Replacement.ReuseKey, authorityGeneration); err != nil {
		return RotationResult{}, sessionAuthorityError(err)
	}

	manager.mu.Lock()
	if pending := manager.pendingRotations[request.Replacement.ReuseKey]; pending != nil {
		if pending.request.CurrentGeneration != request.CurrentGeneration || pending.request.Replacement != request.Replacement {
			manager.mu.Unlock()
			return RotationResult{}, ErrRotationConflict
		}
		if pending.waiters >= manager.limits.MaxRotationWaiters {
			manager.mu.Unlock()
			return RotationResult{}, ErrPendingCapacity
		}
		if request.Trigger > pending.trigger {
			pending.trigger = request.Trigger
			manager.effectiveTriggers[request.Replacement.ReuseKey] = request.Trigger
			if request.Trigger.prohibitsNewWork() {
				manager.markNoNewWorkLocked(request.CurrentGeneration)
			}
		}
		pending.waiters++
		done := pending.done
		manager.mu.Unlock()
		select {
		case <-ctx.Done():
			manager.mu.Lock()
			if manager.pendingRotations[request.Replacement.ReuseKey] == pending && pending.waiters > 0 {
				pending.waiters--
			}
			manager.mu.Unlock()
			return RotationResult{}, ctx.Err()
		case <-done:
			return pending.result, pending.err
		}
	}
	current := manager.sessions[request.CurrentGeneration]
	group := manager.byReuse[request.Replacement.ReuseKey]
	if len(group) >= 2 {
		manager.mu.Unlock()
		return RotationResult{}, ErrGenerationCapacity
	}
	if current == nil || current.snapshot.ReuseKey != request.Replacement.ReuseKey || (current.snapshot.State != TransportCurrent && !request.Trigger.prohibitsNewWork()) {
		manager.mu.Unlock()
		return RotationResult{}, ErrGenerationNotCurrent
	}
	if request.Replacement.Generation <= manager.highestGeneration || manager.sessions[request.Replacement.Generation] != nil {
		manager.mu.Unlock()
		return RotationResult{}, ErrGenerationClosed
	}
	if manager.pendingSessions >= manager.limits.MaxPendingSessions || len(manager.sessions)+manager.pendingSessions >= manager.limits.MaxSessions {
		manager.mu.Unlock()
		return RotationResult{}, ErrSessionCapacity
	}
	cost := transportSessionCost(request.Replacement)
	if manager.sessionBytes+manager.channelBytes > manager.limits.MaxStateBytes || cost > manager.limits.MaxStateBytes-manager.sessionBytes-manager.channelBytes {
		manager.mu.Unlock()
		return RotationResult{}, ErrSessionCapacity
	}
	rotationCtx, cancelRotation := context.WithCancel(ctx)
	pending := &pendingRotation{done: make(chan struct{}), request: request, trigger: request.Trigger, cancel: cancelRotation}
	manager.pendingRotations[request.Replacement.ReuseKey] = pending
	manager.effectiveTriggers[request.Replacement.ReuseKey] = request.Trigger
	manager.pendingSessions++
	if request.Trigger.prohibitsNewWork() {
		manager.markNoNewWorkLocked(request.CurrentGeneration)
	}
	manager.mu.Unlock()

	transport, connectErr := manager.connector.Connect(rotationCtx, TransportSessionAttempt{Generation: request.Replacement.Generation, ReuseKey: request.Replacement.ReuseKey, ProofKey: proof.Key, AuthorityGeneration: authorityGeneration})
	if connectErr == nil && transport == nil {
		connectErr = ErrTransport
	}
	if connectErr == nil {
		connectErr = manager.authority.ValidateSession(request.Replacement.ReuseKey, authorityGeneration)
	}
	if connectErr == nil {
		_, _, connectErr = manager.validateSessionSpec(request.Replacement)
	}

	manager.mu.Lock()
	manager.pendingSessions--
	effective := pending.trigger
	current = manager.sessions[request.CurrentGeneration]
	if connectErr == nil {
		if current == nil || current.snapshot.ReuseKey != request.Replacement.ReuseKey || (current.snapshot.State != TransportCurrent && !effective.prohibitsNewWork()) || len(manager.byReuse[request.Replacement.ReuseKey]) >= 2 {
			connectErr = ErrGenerationNotCurrent
		}
	}
	var result RotationResult
	if connectErr == nil {
		previous := current.snapshot
		current.snapshot.State = TransportDraining
		manager.invalidateUnusedCreditsLocked(current)
		manager.startDrainTimerLocked(current.snapshot.Generation)
		snapshot := TransportSessionSnapshot{Generation: request.Replacement.Generation, ReuseKey: request.Replacement.ReuseKey, State: TransportCurrent, ProofThumbprint: proof.Key.Thumbprint, AuthorityGeneration: authorityGeneration}
		entry := &transportEntry{snapshot: snapshot, transport: transport, nextHandle: 1, channels: make(map[corestate.ServiceHandle]*channelEntry), byWire: make(map[corestate.ChannelID]corestate.ServiceHandle), accountedBytes: cost}
		manager.sessions[snapshot.Generation] = entry
		manager.byReuse[snapshot.ReuseKey][snapshot.Generation] = entry
		manager.highestGeneration = snapshot.Generation
		manager.sessionBytes += cost
		previous.State = TransportDraining
		result = RotationResult{Previous: previous, Current: snapshot, Trigger: effective}
	} else if effective.prohibitsNewWork() || errors.Is(sessionAuthorityError(connectErr), ErrAuthorityStale) {
		manager.markNoNewWorkLocked(request.CurrentGeneration)
	}
	delete(manager.pendingRotations, request.Replacement.ReuseKey)
	pending.cancel()
	pending.result, pending.err = result, sessionAuthorityError(connectErr)
	close(pending.done)
	closeDrained := connectErr == nil && current != nil && len(current.channels) == 0
	manager.mu.Unlock()
	if closeDrained {
		_ = manager.CloseTransportSession(current.snapshot.Generation)
	}
	if connectErr != nil && transport != nil {
		_ = transport.Close()
	}
	return result, pending.err
}

func (manager *Manager) RecoverTransportSession(ctx context.Context, request RotationRequest) (RotationResult, error) {
	var result RotationResult
	var err error
	for attempt := 0; attempt < manager.limits.MaxRecoveryAttempts; attempt++ {
		result, err = manager.RotateTransportSession(ctx, request)
		if err == nil || errors.Is(err, ErrGenerationCapacity) || errors.Is(err, ErrAuthorityStale) || errors.Is(err, ErrProofBinding) {
			return result, err
		}
		if attempt+1 < manager.limits.MaxRecoveryAttempts && manager.limits.RecoveryBackoff > 0 {
			timer := time.NewTimer(manager.limits.RecoveryBackoff)
			select {
			case <-ctx.Done():
				timer.Stop()
				return RotationResult{}, ctx.Err()
			case <-timer.C:
			}
		}
	}
	return RotationResult{}, ErrRecoveryExhausted
}

func (manager *Manager) FailTransportSession(generation corestate.TSGeneration, trigger RotationTrigger) error {
	if !trigger.valid() || !trigger.prohibitsNewWork() {
		return ErrInvalidSession
	}
	manager.mu.Lock()
	defer manager.mu.Unlock()
	entry := manager.sessions[generation]
	if entry == nil {
		return ErrGenerationClosed
	}
	if trigger > manager.effectiveTriggers[entry.snapshot.ReuseKey] {
		manager.effectiveTriggers[entry.snapshot.ReuseKey] = trigger
	}
	manager.markNoNewWorkLocked(generation)
	return nil
}

func (manager *Manager) markNoNewWorkLocked(generation corestate.TSGeneration) {
	entry := manager.sessions[generation]
	if entry == nil {
		return
	}
	entry.snapshot.State = TransportDraining
	manager.invalidateUnusedCreditsLocked(entry)
	manager.startDrainTimerLocked(generation)
}

func (manager *Manager) invalidateUnusedCreditsLocked(entry *transportEntry) {
	for _, channel := range entry.channels {
		channel.credits.current.used = ^uint64(0)
		channel.credits.pendingRefill = 0
	}
}

func (manager *Manager) startDrainTimerLocked(generation corestate.TSGeneration) {
	if manager.drainTimers[generation] != nil {
		return
	}
	manager.drainTimers[generation] = time.AfterFunc(manager.limits.DrainTimeout, func() { _ = manager.CloseTransportSession(generation) })
}
