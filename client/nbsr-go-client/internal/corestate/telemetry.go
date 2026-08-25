package corestate

import "nbsr.local/client/nbsr-go-client/internal/observability"

type telemetryObserver struct{ recorder observability.Recorder }

// NewTelemetryObserver returns an identifier-free adapter for Store events.
func NewTelemetryObserver(recorder observability.Recorder) Observer {
	return telemetryObserver{recorder: recorder}
}

func (observer telemetryObserver) Observe(event Event) {
	if observer.recorder == nil {
		return
	}
	domain, kind := observability.DomainRuntime, observability.KindFailedClosed
	switch event.Kind {
	case EventMappingInserted:
		domain, kind = observability.DomainMapping, observability.KindAdmitted
	case EventMappingRemoved:
		domain, kind = observability.DomainMapping, observability.KindReleased
	case EventServiceInserted:
		domain, kind = observability.DomainChannel, observability.KindAdmitted
	case EventServiceClosed, EventServiceRemoved:
		domain, kind = observability.DomainChannel, observability.KindReleased
	case EventStreamInserted:
		domain, kind = observability.DomainStream, observability.KindAdmitted
	case EventStreamTerminal, EventStreamRemoved:
		domain, kind = observability.DomainStream, observability.KindReleased
	case EventGenerationClosed:
		domain, kind = observability.DomainSession, observability.KindReleased
	default:
		observer.recorder.Record(observability.Event{})
		return
	}
	observer.recorder.Record(observability.Event{Domain: domain, Kind: kind, Outcome: observability.OutcomeSuccess})
}
