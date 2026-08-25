package observability

import (
	"reflect"
	"sync"
	"testing"
)

func TestCollectorRecordsClosedDimensionsConcurrently(t *testing.T) {
	collector := NewCollector()
	const workers = 16
	const iterations = 250
	var group sync.WaitGroup
	for range workers {
		group.Add(1)
		go func() {
			defer group.Done()
			for range iterations {
				collector.Record(Event{Domain: DomainStream, Kind: KindRejected, Outcome: OutcomeExpectedDenial})
			}
		}()
	}
	group.Wait()

	snapshot := collector.Snapshot()
	if got := snapshot.Count(DomainStream, KindRejected, OutcomeExpectedDenial); got != workers*iterations {
		t.Fatalf("rejected stream count = %d, want %d", got, workers*iterations)
	}
	if snapshot.InvalidEvents != 0 {
		t.Fatalf("invalid events = %d, want 0", snapshot.InvalidEvents)
	}
}

func TestCollectorCollapsesInvalidInputIntoOneBoundedBucket(t *testing.T) {
	collector := NewCollector()
	collector.Record(Event{})
	collector.Record(Event{Domain: Domain(domainCount + 10), Kind: KindReleased, Outcome: OutcomeSuccess})

	snapshot := collector.Snapshot()
	if snapshot.InvalidEvents != 2 {
		t.Fatalf("invalid events = %d, want 2", snapshot.InvalidEvents)
	}
	if got := snapshot.Count(DomainInvalid, KindInvalid, OutcomeInvalid); got != 0 {
		t.Fatalf("invalid dimension count = %d, want 0", got)
	}
}

func TestEventCannotCarryHighCardinalityOrSensitiveValues(t *testing.T) {
	typeOfEvent := reflect.TypeOf(Event{})
	if typeOfEvent.NumField() != 3 {
		t.Fatalf("Event has %d fields, want exactly the three closed dimensions", typeOfEvent.NumField())
	}
	for index := range typeOfEvent.NumField() {
		field := typeOfEvent.Field(index)
		if field.Type.Kind() == reflect.String || field.Type.Kind() == reflect.Slice || field.Type.Kind() == reflect.Map || field.Type.Kind() == reflect.Array {
			t.Fatalf("Event field %s can carry unbounded or identifying data: %s", field.Name, field.Type)
		}
	}
}

func TestHealthSnapshotIsFixedSizeAndSeparatesDenialFromFailure(t *testing.T) {
	collector := NewCollector()
	collector.Record(Event{Domain: DomainMapping, Kind: KindExhausted, Outcome: OutcomeExpectedDenial})
	collector.Record(Event{Domain: DomainAuthority, Kind: KindFailedClosed, Outcome: OutcomeInternalFailure})

	health := collector.Health([resourceCount]ResourceUsage{
		ResourceMappings: {Used: 4, Capacity: 4},
		ResourceFlows:    {Used: 1, Capacity: 8},
	})
	if health.State != HealthDegraded || health.Reason != HealthInternalFailure {
		t.Fatalf("health = (%d, %d), want degraded/internal failure", health.State, health.Reason)
	}
	if health.ExpectedDenials != 1 || health.InternalFailures != 1 {
		t.Fatalf("health outcomes = (%d, %d), want (1, 1)", health.ExpectedDenials, health.InternalFailures)
	}
	if health.Resources[ResourceMappings] != (ResourceUsage{Used: 4, Capacity: 4}) {
		t.Fatalf("mapping usage = %+v", health.Resources[ResourceMappings])
	}
}

func TestSnapshotIsImmutableValueCopy(t *testing.T) {
	collector := NewCollector()
	collector.Record(Event{Domain: DomainFlow, Kind: KindAdmitted, Outcome: OutcomeSuccess})
	first := collector.Snapshot()
	collector.Record(Event{Domain: DomainFlow, Kind: KindReleased, Outcome: OutcomeSuccess})

	if got := first.Count(DomainFlow, KindReleased, OutcomeSuccess); got != 0 {
		t.Fatalf("old snapshot changed after recording: %d", got)
	}
}
