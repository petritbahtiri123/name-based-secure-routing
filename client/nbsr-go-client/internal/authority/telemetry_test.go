package authority

import (
	"testing"

	"nbsr.local/client/nbsr-go-client/internal/observability"
)

func TestTelemetryObserverSeparatesExpectedDenialFromInternalFailure(t *testing.T) {
	collector := observability.NewCollector()
	observer := NewTelemetryObserver(collector)
	observer.Observe(Event{Kind: EventAcquireResult, Result: CodeRevoked})
	observer.Observe(Event{Kind: EventAcquireResult, Result: CodeProviderUnavailable})

	snapshot := collector.Snapshot()
	if got := snapshot.Count(observability.DomainAuthority, observability.KindRejected, observability.OutcomeExpectedDenial); got != 1 {
		t.Fatalf("expected denials = %d, want 1", got)
	}
	if got := snapshot.Count(observability.DomainAuthority, observability.KindFailedClosed, observability.OutcomeInternalFailure); got != 1 {
		t.Fatalf("internal failures = %d, want 1", got)
	}
}
