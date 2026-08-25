package resolution

import (
	"errors"
	"sync"
	"testing"

	"nbsr.local/client/nbsr-go-client/internal/corestate"
)

func TestFlowUsageTracksCapacityAndCleanupWithoutIdentifiers(t *testing.T) {
	store, err := NewFlowStore(FlowLimits{MaxEntries: 2, MaxBytes: 32})
	if err != nil {
		t.Fatal(err)
	}
	if err := store.Bind(FlowContext{MappingID: 1, LocalFlowID: 1}); err != nil {
		t.Fatal(err)
	}
	if got := store.Usage(); got != (FlowUsage{Entries: 1, Bytes: 16, MaxEntries: 2, MaxBytes: 32}) {
		t.Fatalf("usage = %+v", got)
	}
	if _, err := store.Consume(1); err != nil {
		t.Fatal(err)
	}
	if got := store.Usage(); got.Entries != 0 || got.Bytes != 0 {
		t.Fatalf("usage after consume = %+v", got)
	}
}

func TestFlowStoreConsumesContextOnce(t *testing.T) {
	store, err := NewFlowStore(FlowLimits{MaxEntries: 2, MaxBytes: 64})
	if err != nil {
		t.Fatal(err)
	}
	context := FlowContext{MappingID: 7, LocalFlowID: 9}
	if err := store.Bind(context); err != nil {
		t.Fatal(err)
	}
	if got, err := store.Consume(9); err != nil || got != 7 {
		t.Fatalf("Consume = (%d, %v), want (7, nil)", got, err)
	}
	if _, err := store.Consume(9); !errors.Is(err, ErrUnknownFlow) {
		t.Fatalf("second Consume error = %v, want ErrUnknownFlow", err)
	}
}

func TestFlowStoreBoundsAndRejectsDuplicates(t *testing.T) {
	store, err := NewFlowStore(FlowLimits{MaxEntries: 1, MaxBytes: 32})
	if err != nil {
		t.Fatal(err)
	}
	if err := store.Bind(FlowContext{MappingID: 1, LocalFlowID: 1}); err != nil {
		t.Fatal(err)
	}
	if err := store.Bind(FlowContext{MappingID: 2, LocalFlowID: 1}); !errors.Is(err, ErrFlowConflict) {
		t.Fatalf("duplicate error = %v, want ErrFlowConflict", err)
	}
	if err := store.Bind(FlowContext{MappingID: 2, LocalFlowID: 2}); !errors.Is(err, ErrFlowCapacity) {
		t.Fatalf("capacity error = %v, want ErrFlowCapacity", err)
	}
}

func TestFlowStoreConcurrentConsumeHasOneWinner(t *testing.T) {
	store, _ := NewFlowStore(FlowLimits{MaxEntries: 1, MaxBytes: 32})
	_ = store.Bind(FlowContext{MappingID: 3, LocalFlowID: 4})
	var wait sync.WaitGroup
	winners := make(chan corestate.MappingID, 2)
	for range 2 {
		wait.Add(1)
		go func() {
			defer wait.Done()
			if id, err := store.Consume(4); err == nil {
				winners <- id
			}
		}()
	}
	wait.Wait()
	close(winners)
	if got := len(winners); got != 1 {
		t.Fatalf("consume winners = %d, want 1", got)
	}
}

func TestFlowStoreRestartIsEmpty(t *testing.T) {
	first, _ := NewFlowStore(FlowLimits{MaxEntries: 1, MaxBytes: 32})
	_ = first.Bind(FlowContext{MappingID: 1, LocalFlowID: 1})
	second, _ := NewFlowStore(FlowLimits{MaxEntries: 1, MaxBytes: 32})
	if _, err := second.Consume(1); !errors.Is(err, ErrUnknownFlow) {
		t.Fatalf("fresh store restored flow: %v", err)
	}
}
