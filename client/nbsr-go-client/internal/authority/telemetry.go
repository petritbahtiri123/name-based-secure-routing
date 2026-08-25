package authority

import "nbsr.local/client/nbsr-go-client/internal/observability"

type telemetryObserver struct{ recorder observability.Recorder }

// NewTelemetryObserver returns an identifier-free adapter for authority events.
func NewTelemetryObserver(recorder observability.Recorder) Observer {
	return telemetryObserver{recorder: recorder}
}

func (observer telemetryObserver) Observe(event Event) {
	if observer.recorder == nil {
		return
	}
	kind := observability.KindAdmitted
	outcome := observability.OutcomeSuccess
	if event.Result != 0 {
		kind = observability.KindRejected
		outcome = observability.OutcomeExpectedDenial
		if internalAuthorityError(event.Result) {
			kind = observability.KindFailedClosed
			outcome = observability.OutcomeInternalFailure
		}
	}
	switch event.Kind {
	case EventAcquireRequested, EventRenewalRequested, EventRetryDecision:
		kind = observability.KindStarted
	case EventAcquireCoalesced:
		kind = observability.KindCoalesced
	case EventCacheFull:
		kind = observability.KindExhausted
		outcome = observability.OutcomeExpectedDenial
	case EventFreshnessRejected, EventFreshnessExpired, EventAmbiguousQuarantine, EventRollbackFloorRejected:
		if outcome == observability.OutcomeSuccess {
			outcome = observability.OutcomeExpectedDenial
		}
		kind = observability.KindFailedClosed
	case EventAuthorityInvalidated:
		kind = observability.KindReleased
	}
	observer.recorder.Record(observability.Event{Domain: observability.DomainAuthority, Kind: kind, Outcome: outcome})
}

func internalAuthorityError(code ErrorCode) bool {
	switch code {
	case CodeProviderUnavailable, CodeInvalidLimits, CodeInvalidTransition, CodeAccountingOverflow,
		CodeStoragePathRejected, CodeStorageBusy, CodeStorageUnsupported:
		return true
	default:
		return false
	}
}
