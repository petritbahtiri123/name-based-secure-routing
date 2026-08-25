package corestate

import (
	"testing"

	"nbsr.local/client/nbsr-go-client/internal/observability"
)

func TestTelemetryObserverRedactsCoreLifecycleIntoClosedCounters(t *testing.T) {
	collector := observability.NewCollector()
	observer := NewTelemetryObserver(collector)
	observer.Observe(Event{Kind: EventMappingInserted})
	observer.Observe(Event{Kind: EventMappingRemoved})
	observer.Observe(Event{Kind: EventStreamInserted})

	snapshot := collector.Snapshot()
	if got := snapshot.Count(observability.DomainMapping, observability.KindAdmitted, observability.OutcomeSuccess); got != 1 {
		t.Fatalf("mapping admitted = %d, want 1", got)
	}
	if got := snapshot.Count(observability.DomainMapping, observability.KindReleased, observability.OutcomeSuccess); got != 1 {
		t.Fatalf("mapping released = %d, want 1", got)
	}
	if got := snapshot.Count(observability.DomainStream, observability.KindAdmitted, observability.OutcomeSuccess); got != 1 {
		t.Fatalf("stream admitted = %d, want 1", got)
	}
}
