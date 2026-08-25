package corestate

import (
	"errors"
	"sync"
	"testing"
)

func streamStoreWithObserver(t *testing.T, maxStreams int, maxBytes uint64, observer Observer) (*Store, ServiceSnapshot) {
	t.Helper()
	limits := serviceLimits(2, 2048)
	limits.MaxStreams = maxStreams
	limits.MaxStreamBytes = maxBytes
	s, err := NewStore(limits, fakeClock{}, observer)
	if err != nil {
		t.Fatal(err)
	}
	mustOpen(t, s, 1)
	return s, mustAddService(t, s, serviceSpec(1, 1))
}

func streamStore(t *testing.T, maxStreams int, maxBytes uint64) (*Store, ServiceSnapshot) {
	t.Helper()
	return streamStoreWithObserver(t, maxStreams, maxBytes, nil)
}

func streamSpec(service ServiceSnapshot, streamID StreamID) StreamSpec {
	return StreamSpec{Generation: service.Generation, Handle: service.Handle, StreamID: streamID, LocalFlowID: LocalFlowID(streamID) + 1}
}

func mustInsertStream(t *testing.T, s *Store, spec StreamSpec) {
	t.Helper()
	if err := s.InsertStream(spec); err != nil {
		t.Fatal(err)
	}
}

func TestStreamEntryCapacityBelow(t *testing.T) {
	s, service := streamStore(t, 2, 2*streamBaseBytes)
	mustInsertStream(t, s, streamSpec(service, 1))
}

func TestStreamEntryCapacityExact(t *testing.T) {
	s, service := streamStore(t, 2, 2*streamBaseBytes)
	mustInsertStream(t, s, streamSpec(service, 1))
	mustInsertStream(t, s, streamSpec(service, 2))
}

func TestStreamEntryCapacityAbove(t *testing.T) {
	s, service := streamStore(t, 2, 3*streamBaseBytes)
	mustInsertStream(t, s, streamSpec(service, 1))
	mustInsertStream(t, s, streamSpec(service, 2))
	before := s.Usage()
	if err := s.InsertStream(streamSpec(service, 3)); !errors.Is(err, ErrCapacityExceeded) {
		t.Fatalf("third stream error = %v, want ErrCapacityExceeded", err)
	}
	if s.Usage() != before {
		t.Fatal("entry-capacity rejection partially mutated usage")
	}
}

func TestStreamByteCapacityBelow(t *testing.T) {
	s, service := streamStore(t, 2, 2*streamBaseBytes+1)
	mustInsertStream(t, s, streamSpec(service, 1))
}

func TestStreamByteCapacityExact(t *testing.T) {
	s, service := streamStore(t, 2, 2*streamBaseBytes)
	mustInsertStream(t, s, streamSpec(service, 1))
	mustInsertStream(t, s, streamSpec(service, 2))
}

func TestStreamByteCapacityAbove(t *testing.T) {
	s, service := streamStore(t, 2, 2*streamBaseBytes-1)
	mustInsertStream(t, s, streamSpec(service, 1))
	before := s.Usage()
	if err := s.InsertStream(streamSpec(service, 2)); !errors.Is(err, ErrByteCapacityExceeded) {
		t.Fatalf("second stream error = %v, want ErrByteCapacityExceeded", err)
	}
	if s.Usage() != before {
		t.Fatal("byte-capacity rejection partially mutated usage")
	}
}

func TestStreamPinnedToGenerationAndService(t *testing.T) {
	s, service := streamStore(t, 2, 2*streamBaseBytes)
	spec := StreamSpec{Generation: service.Generation, Handle: service.Handle, StreamID: 4, LocalFlowID: 9}
	mustInsertStream(t, s, spec)
	if _, err := s.LookupStream(service.Generation+1, service.Handle, 4); !errors.Is(err, ErrUnknownService) {
		t.Fatalf("cross-generation lookup error = %v, want ErrUnknownService", err)
	}
}

func TestStreamValidatesIdentifiersButAllowsZeroStreamID(t *testing.T) {
	s, service := streamStore(t, 2, 2*streamBaseBytes)
	zeroID := streamSpec(service, 0)
	mustInsertStream(t, s, zeroID)
	if got, err := s.LookupStream(service.Generation, service.Handle, 0); err != nil || got.StreamID != 0 {
		t.Fatalf("zero StreamID lookup = %+v, err=%v", got, err)
	}
	tests := []struct {
		name string
		spec StreamSpec
		want error
	}{
		{"zero generation", StreamSpec{Handle: service.Handle, StreamID: 2, LocalFlowID: 1}, ErrInvalidTransition},
		{"zero handle", StreamSpec{Generation: 1, StreamID: 2, LocalFlowID: 1}, ErrInvalidHandle},
		{"zero local flow", StreamSpec{Generation: 1, Handle: service.Handle, StreamID: 2}, ErrInvalidTransition},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			before := s.Usage()
			if err := s.InsertStream(tt.spec); !errors.Is(err, tt.want) {
				t.Fatalf("error = %v, want %v", err, tt.want)
			}
			if s.Usage() != before {
				t.Fatal("invalid insertion partially mutated usage")
			}
		})
	}
}

func TestStreamRejectsUnknownAndClosedOwner(t *testing.T) {
	s, service := streamStore(t, 2, 2*streamBaseBytes)
	unknown := streamSpec(service, 1)
	unknown.Handle++
	if err := s.InsertStream(unknown); !errors.Is(err, ErrUnknownService) {
		t.Fatalf("unknown owner error = %v, want ErrUnknownService", err)
	}
	if err := s.CloseService(service.Generation, service.Handle); err != nil {
		t.Fatal(err)
	}
	if err := s.InsertStream(streamSpec(service, 2)); !errors.Is(err, ErrServiceClosed) {
		t.Fatalf("closed owner error = %v, want ErrServiceClosed", err)
	}
}

func TestStreamDuplicateIsAtomic(t *testing.T) {
	s, service := streamStore(t, 2, 2*streamBaseBytes)
	spec := streamSpec(service, 4)
	mustInsertStream(t, s, spec)
	before := s.Usage()
	if err := s.InsertStream(spec); !errors.Is(err, ErrDuplicateStream) {
		t.Fatalf("duplicate error = %v, want ErrDuplicateStream", err)
	}
	if s.Usage() != before {
		t.Fatal("duplicate insertion partially mutated usage")
	}
	owner, err := s.LookupService(service.Generation, service.Handle)
	if err != nil || owner.ActiveStreams != 1 {
		t.Fatalf("owner = %+v, err=%v", owner, err)
	}
}

func TestStreamKeyIsolation(t *testing.T) {
	s, first := streamStore(t, 3, 3*streamBaseBytes)
	second := mustAddService(t, s, serviceSpec(1, 2))
	mustInsertStream(t, s, streamSpec(first, 7))
	mustInsertStream(t, s, streamSpec(second, 7))
	got, err := s.LookupStream(1, second.Handle, 7)
	if err != nil || got.Handle != second.Handle {
		t.Fatalf("isolated lookup = %+v, err=%v", got, err)
	}
}

func TestStreamCancellationTransitionsOnce(t *testing.T) {
	s, service := streamStore(t, 1, streamBaseBytes)
	spec := streamSpec(service, 1)
	mustInsertStream(t, s, spec)
	if err := s.CancelStream(1, service.Handle, 1); err != nil {
		t.Fatal(err)
	}
	got, err := s.LookupStream(1, service.Handle, 1)
	if err != nil || got.State != StreamCancelled || got.TerminalReason != TerminalCancelled {
		t.Fatalf("cancelled stream = %+v, err=%v", got, err)
	}
	if err := s.CancelStream(1, service.Handle, 1); !errors.Is(err, ErrInvalidTransition) {
		t.Fatalf("second cancel error = %v, want ErrInvalidTransition", err)
	}
	if err := s.FinishStream(1, service.Handle, 1, TerminalCompleted); !errors.Is(err, ErrInvalidTransition) {
		t.Fatalf("finish after cancel error = %v, want ErrInvalidTransition", err)
	}
}

func TestStreamFinishValidatesTerminalReasonAndTransitionsOnce(t *testing.T) {
	s, service := streamStore(t, 1, streamBaseBytes)
	spec := streamSpec(service, 1)
	mustInsertStream(t, s, spec)
	for _, reason := range []TerminalReason{TerminalNone, TerminalCancelled, TerminalReason(255)} {
		if err := s.FinishStream(1, service.Handle, 1, reason); !errors.Is(err, ErrInvalidTransition) {
			t.Fatalf("reason %d error = %v, want ErrInvalidTransition", reason, err)
		}
	}
	if err := s.FinishStream(1, service.Handle, 1, TerminalFailed); err != nil {
		t.Fatal(err)
	}
	got, err := s.LookupStream(1, service.Handle, 1)
	if err != nil || got.State != StreamFinished || got.TerminalReason != TerminalFailed {
		t.Fatalf("finished stream = %+v, err=%v", got, err)
	}
	if err := s.FinishStream(1, service.Handle, 1, TerminalCompleted); !errors.Is(err, ErrInvalidTransition) {
		t.Fatalf("second finish error = %v, want ErrInvalidTransition", err)
	}
}

func TestTerminalRemovalReconcilesCountAndBytes(t *testing.T) {
	s, service := streamStore(t, 1, streamBaseBytes)
	spec := streamSpec(service, 4)
	before := s.Usage()
	mustInsertStream(t, s, spec)
	if err := s.RemoveStream(spec.Generation, spec.Handle, spec.StreamID); !errors.Is(err, ErrInvalidTransition) {
		t.Fatalf("active removal error = %v, want ErrInvalidTransition", err)
	}
	if err := s.FinishStream(spec.Generation, spec.Handle, spec.StreamID, TerminalCompleted); err != nil {
		t.Fatal(err)
	}
	if err := s.RemoveStream(spec.Generation, spec.Handle, spec.StreamID); err != nil {
		t.Fatal(err)
	}
	if s.Usage() != before {
		t.Fatal("usage mismatch")
	}
	owner, err := s.LookupService(service.Generation, service.Handle)
	if err != nil || owner.ActiveStreams != 0 {
		t.Fatalf("owner = %+v, err=%v", owner, err)
	}
}

type reentrantStreamObserver struct {
	store  *Store
	events []Event
}

func (o *reentrantStreamObserver) Observe(event Event) {
	if o.store != nil {
		_ = o.store.Usage()
	}
	o.events = append(o.events, event)
}

func TestStreamObserverRunsAfterUnlockForEveryMutation(t *testing.T) {
	observer := &reentrantStreamObserver{}
	s, service := streamStoreWithObserver(t, 1, streamBaseBytes, observer)
	observer.store = s
	observer.events = nil // Ignore setup events from generation and service insertion.
	spec := streamSpec(service, 4)
	mustInsertStream(t, s, spec)
	if err := s.FinishStream(1, service.Handle, 4, TerminalCompleted); err != nil {
		t.Fatal(err)
	}
	if err := s.RemoveStream(1, service.Handle, 4); err != nil {
		t.Fatal(err)
	}
	want := []Event{
		{Kind: EventStreamInserted},
		{Kind: EventStreamTerminal},
		{Kind: EventStreamRemoved},
	}
	if len(observer.events) != len(want) {
		t.Fatalf("events = %#v, want %#v", observer.events, want)
	}
	for i := range want {
		if observer.events[i] != want[i] {
			t.Fatalf("event %d = %#v, want %#v", i, observer.events[i], want[i])
		}
	}
}

func TestStreamConcurrentDuplicateHasOneWinnerAndExactAccounting(t *testing.T) {
	s, service := streamStore(t, 16, 16*streamBaseBytes)
	spec := streamSpec(service, 4)
	var wg sync.WaitGroup
	errs := make(chan error, 16)
	for i := 0; i < 16; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			errs <- s.InsertStream(spec)
		}()
	}
	wg.Wait()
	close(errs)
	successes, duplicates := 0, 0
	for err := range errs {
		switch {
		case err == nil:
			successes++
		case errors.Is(err, ErrDuplicateStream):
			duplicates++
		default:
			t.Fatalf("unexpected insertion error: %v", err)
		}
	}
	if successes != 1 || duplicates != 15 {
		t.Fatalf("successes=%d duplicates=%d, want 1 and 15", successes, duplicates)
	}
	if got := s.Usage(); got.Streams != 1 || got.StreamBytes != streamBaseBytes {
		t.Fatalf("usage = %+v", got)
	}
	owner, err := s.LookupService(1, service.Handle)
	if err != nil || owner.ActiveStreams != 1 {
		t.Fatalf("owner = %+v, err=%v", owner, err)
	}
	if err := s.ValidateInvariants(); err != nil {
		t.Fatal(err)
	}
}
