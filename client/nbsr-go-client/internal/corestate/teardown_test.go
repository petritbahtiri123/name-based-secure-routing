package corestate

import (
	"errors"
	"testing"
)

type teardownObserver struct {
	events  []Event
	block   EventKind
	reached chan struct{}
	release chan struct{}
	panicOn EventKind
}

func (o *teardownObserver) Observe(event Event) {
	o.events = append(o.events, event)
	if event.Kind == o.block {
		o.reached <- struct{}{}
		<-o.release
	}
	if event.Kind == o.panicOn {
		panic("teardown observer panic")
	}
}

func teardownStore(t *testing.T, observer Observer) *Store {
	t.Helper()
	l := validLimits()
	l.MaxGenerations = 4
	l.MaxMappings = 8
	l.MaxServices = 16
	l.MaxStreams = 32
	l.MaxMappingBytes = 4096
	l.MaxServiceBytes = 4096
	l.MaxStreamBytes = 4096
	l.MaxServiceIdentityBytes = 64
	l.MaxPolicyContextBytes = 64
	s, err := NewStore(l, newFakeClock(1), observer)
	if err != nil {
		t.Fatal(err)
	}
	return s
}

func populatedGeneration(t *testing.T, generation TSGeneration, services, streamsPerService int) (*Store, []ServiceSnapshot) {
	t.Helper()
	s := teardownStore(t, nil)
	mustOpen(t, s, generation)
	mustAddMapping(t, s, mappingSpec(1))
	owners := make([]ServiceSnapshot, 0, services)
	for i := 1; i <= services; i++ {
		spec := serviceSpec(generation, byte(i))
		owner := mustAddService(t, s, spec)
		owners = append(owners, owner)
		for stream := 0; stream < streamsPerService; stream++ {
			mustInsertStream(t, s, StreamSpec{Generation: generation, Handle: owner.Handle, StreamID: StreamID(stream), LocalFlowID: LocalFlowID(stream + 1)})
		}
	}
	return s, owners
}

func TestGenerationTeardownReturnsToMappingOnlyUsage(t *testing.T) {
	s, _ := populatedGeneration(t, 7, 3, 4)
	before := s.Usage()
	want := Usage{Mappings: before.Mappings, MappingBytes: before.MappingBytes}
	if err := s.CloseGeneration(7); err != nil {
		t.Fatal(err)
	}
	if got := s.Usage(); got != want {
		t.Fatalf("usage = %#v, want %#v", got, want)
	}
	if err := s.ValidateInvariants(); err != nil {
		t.Fatal(err)
	}
	if _, err := s.LookupMapping(1); err != nil {
		t.Fatalf("independent mapping was removed: %v", err)
	}
}

func TestGenerationTeardownEmitsOneAggregateEventAfterCommit(t *testing.T) {
	o := &teardownObserver{}
	s := teardownStore(t, o)
	mustOpen(t, s, 7)
	owner := mustAddService(t, s, serviceSpec(7, 1))
	mustInsertStream(t, s, streamSpec(owner, 1))
	o.events = nil
	if err := s.CloseGeneration(7); err != nil {
		t.Fatal(err)
	}
	want := []Event{{Kind: EventGenerationClosed, Generation: 7}}
	if len(o.events) != 1 || o.events[0] != want[0] {
		t.Fatalf("events = %#v, want %#v", o.events, want)
	}
}

func TestGenerationTeardownObserverPanicPropagatesAfterCommit(t *testing.T) {
	o := &teardownObserver{panicOn: EventGenerationClosed}
	s := teardownStore(t, o)
	mustOpen(t, s, 7)
	owner := mustAddService(t, s, serviceSpec(7, 1))
	mustInsertStream(t, s, streamSpec(owner, 1))
	func() {
		defer func() {
			if recover() == nil {
				t.Fatal("observer panic did not propagate")
			}
		}()
		_ = s.CloseGeneration(7)
	}()
	if got := s.Usage(); got.Services != 0 || got.Streams != 0 {
		t.Fatalf("teardown was not committed: %+v", got)
	}
	if err := s.OpenGeneration(7); !errors.Is(err, ErrGenerationClosed) {
		t.Fatalf("generation resurrected after observer panic: %v", err)
	}
}

func TestServiceTeardownDoesNotTouchUnrelatedService(t *testing.T) {
	s := teardownStore(t, nil)
	mustOpen(t, s, 7)
	a := mustAddService(t, s, serviceSpec(7, 1))
	b := mustAddService(t, s, serviceSpec(7, 2))
	for i := 0; i < 2; i++ {
		mustInsertStream(t, s, StreamSpec{Generation: 7, Handle: a.Handle, StreamID: StreamID(i), LocalFlowID: LocalFlowID(i + 1)})
		mustInsertStream(t, s, StreamSpec{Generation: 7, Handle: b.Handle, StreamID: StreamID(i), LocalFlowID: LocalFlowID(i + 11)})
	}
	if err := s.CloseService(7, a.Handle); err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 2; i++ {
		if err := s.FinishStream(7, a.Handle, StreamID(i), TerminalCompleted); err != nil {
			t.Fatal(err)
		}
		if err := s.RemoveStream(7, a.Handle, StreamID(i)); err != nil {
			t.Fatal(err)
		}
	}
	if err := s.RemoveService(7, a.Handle); err != nil {
		t.Fatal(err)
	}
	got, err := s.LookupService(7, b.Handle)
	if err != nil || got.ActiveStreams != 2 || got.State != ServiceActive {
		t.Fatalf("unrelated service = %#v, err=%v", got, err)
	}
	if err := s.ValidateInvariants(); err != nil {
		t.Fatal(err)
	}
}

func TestRepeatedLifecycleTeardownNeverResurrectsStaleGeneration(t *testing.T) {
	s := teardownStore(t, nil)
	for generation := TSGeneration(1); generation <= 16; generation++ {
		mustOpen(t, s, generation)
		owner := mustAddService(t, s, serviceSpec(generation, byte(generation)))
		mustInsertStream(t, s, streamSpec(owner, StreamID(generation)))
		if err := s.CloseGeneration(generation); err != nil {
			t.Fatal(err)
		}
		if err := s.OpenGeneration(generation); !errors.Is(err, ErrGenerationClosed) {
			t.Fatalf("generation %d reopened: %v", generation, err)
		}
	}
	if got := s.Usage(); got != (Usage{}) {
		t.Fatalf("usage = %+v", got)
	}
	if err := s.ValidateInvariants(); err != nil {
		t.Fatal(err)
	}
}

func TestLargeBoundedPopulation(t *testing.T) {
	s := teardownStore(t, nil)
	operations := 0
	for cycle := 0; cycle < 512; cycle++ {
		generation := TSGeneration(cycle + 1)
		channel := byte(cycle%254 + 1)
		if err := s.OpenGeneration(generation); err != nil {
			t.Fatal(err)
		}
		operations++
		assertStoreHealthy(t, s)

		owner := mustAddService(t, s, serviceSpec(generation, channel))
		operations++
		assertStoreHealthy(t, s)

		stream := StreamSpec{Generation: generation, Handle: owner.Handle, StreamID: 1, LocalFlowID: 1}
		mustInsertStream(t, s, stream)
		operations++
		assertStoreHealthy(t, s)

		if err := s.FinishStream(generation, owner.Handle, stream.StreamID, TerminalCompleted); err != nil {
			t.Fatal(err)
		}
		operations++
		assertStoreHealthy(t, s)

		if err := s.RemoveStream(generation, owner.Handle, stream.StreamID); err != nil {
			t.Fatal(err)
		}
		operations++
		assertStoreHealthy(t, s)

		if err := s.CloseService(generation, owner.Handle); err != nil {
			t.Fatal(err)
		}
		operations++
		assertStoreHealthy(t, s)

		if err := s.RemoveService(generation, owner.Handle); err != nil {
			t.Fatal(err)
		}
		operations++
		assertStoreHealthy(t, s)

		if err := s.CloseGeneration(generation); err != nil {
			t.Fatal(err)
		}
		operations++
		assertStoreHealthy(t, s)
	}
	if operations != 4096 {
		t.Fatalf("operations = %d, want 4096", operations)
	}
}

func TestGenerationTeardownRejectsStaleUseWithoutPartialState(t *testing.T) {
	s := teardownStore(t, nil)
	mustOpen(t, s, 7)
	if err := s.CloseGeneration(7); err != nil {
		t.Fatal(err)
	}
	before := s.Usage()
	if _, err := s.AddService(serviceSpec(7, 1)); !errors.Is(err, ErrGenerationClosed) {
		t.Fatalf("stale insertion error = %v, want ErrGenerationClosed", err)
	}
	if s.Usage() != before || len(s.services) != 0 || len(s.servicesByChannel) != 0 {
		t.Fatal("failed stale insertion partially mutated state")
	}
}

func TestValidateInvariantsDetectsCorruptionWithoutRepair(t *testing.T) {
	tests := []struct {
		name    string
		corrupt func(*Store, ServiceSnapshot)
	}{
		{"usage", func(s *Store, _ ServiceSnapshot) { s.usage.Services++ }},
		{"reverse index", func(s *Store, owner ServiceSnapshot) {
			delete(s.servicesByChannel, channelKey{generation: owner.Generation, channelID: owner.ChannelID})
		}},
		{"owner count", func(s *Store, owner ServiceSnapshot) {
			key := serviceKey{generation: owner.Generation, handle: owner.Handle}
			e := s.services[key]
			e.ActiveStreams++
			s.services[key] = e
		}},
		{"generation ownership", func(s *Store, owner ServiceSnapshot) { delete(s.generations, owner.Generation) }},
		{"service handle", func(s *Store, owner ServiceSnapshot) {
			key := serviceKey{generation: owner.Generation, handle: owner.Handle}
			e := s.services[key]
			e.Handle++
			s.services[key] = e
		}},
		{"stream lifecycle", func(s *Store, owner ServiceSnapshot) {
			key := streamKey{generation: owner.Generation, handle: owner.Handle, streamID: 1}
			e := s.streams[key]
			e.State = StreamFinished
			e.TerminalReason = TerminalNone
			s.streams[key] = e
		}},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			s := teardownStore(t, nil)
			mustOpen(t, s, 7)
			owner := mustAddService(t, s, serviceSpec(7, 1))
			mustInsertStream(t, s, streamSpec(owner, 1))
			s.mu.Lock()
			tt.corrupt(s, owner)
			s.mu.Unlock()
			before := s.Usage()
			if err := s.ValidateInvariants(); err == nil {
				t.Fatal("corruption was not detected")
			}
			if s.Usage() != before {
				t.Fatal("validation repaired corrupted state")
			}
		})
	}
}

func TestServiceCloseOrderingInsertCommitsBeforeClose(t *testing.T) {
	o := &teardownObserver{block: EventStreamInserted, reached: make(chan struct{}), release: make(chan struct{})}
	s := teardownStore(t, o)
	mustOpen(t, s, 7)
	owner := mustAddService(t, s, serviceSpec(7, 1))
	errCh := make(chan error, 1)
	go func() { errCh <- s.InsertStream(streamSpec(owner, 1)) }()
	<-o.reached
	if err := s.CloseService(7, owner.Handle); err != nil {
		t.Fatal(err)
	}
	close(o.release)
	if err := <-errCh; err != nil {
		t.Fatal(err)
	}
	got, err := s.LookupService(7, owner.Handle)
	if err != nil || got.State != ServiceClosed || got.ActiveStreams != 1 {
		t.Fatalf("owner=%+v err=%v", got, err)
	}
}

func TestServiceCloseOrderingCloseCommitsBeforeInsert(t *testing.T) {
	o := &teardownObserver{block: EventServiceClosed, reached: make(chan struct{}), release: make(chan struct{})}
	s := teardownStore(t, o)
	mustOpen(t, s, 7)
	owner := mustAddService(t, s, serviceSpec(7, 1))
	errCh := make(chan error, 1)
	go func() { errCh <- s.CloseService(7, owner.Handle) }()
	<-o.reached
	if err := s.InsertStream(streamSpec(owner, 1)); !errors.Is(err, ErrServiceClosed) {
		t.Fatalf("insert error=%v", err)
	}
	close(o.release)
	if err := <-errCh; err != nil {
		t.Fatal(err)
	}
	if got := s.Usage(); got.Streams != 0 {
		t.Fatalf("usage=%+v", got)
	}
}

func TestGenerationCloseOrderingServiceInsertCommitsBeforeClose(t *testing.T) {
	o := &teardownObserver{block: EventServiceInserted, reached: make(chan struct{}), release: make(chan struct{})}
	s := teardownStore(t, o)
	mustOpen(t, s, 7)
	result := make(chan error, 1)
	go func() { _, err := s.AddService(serviceSpec(7, 1)); result <- err }()
	<-o.reached
	closeErr := s.CloseGeneration(7)
	close(o.release)
	if err := <-result; err != nil {
		t.Fatal(err)
	}
	if closeErr != nil {
		t.Fatal(closeErr)
	}
	if got := s.Usage(); got.Services != 0 {
		t.Fatalf("usage=%+v", got)
	}
}

func TestGenerationCloseOrderingCloseCommitsBeforeServiceInsert(t *testing.T) {
	o := &teardownObserver{block: EventGenerationClosed, reached: make(chan struct{}), release: make(chan struct{})}
	s := teardownStore(t, o)
	mustOpen(t, s, 7)
	result := make(chan error, 1)
	go func() { result <- s.CloseGeneration(7) }()
	select {
	case <-o.reached:
	case err := <-result:
		t.Fatalf("generation close returned before aggregate event: %v", err)
	}
	if _, err := s.AddService(serviceSpec(7, 1)); !errors.Is(err, ErrGenerationClosed) {
		t.Fatalf("insert error=%v", err)
	}
	close(o.release)
	if err := <-result; err != nil {
		t.Fatal(err)
	}
	if got := s.Usage(); got.Services != 0 {
		t.Fatalf("usage=%+v", got)
	}
}
