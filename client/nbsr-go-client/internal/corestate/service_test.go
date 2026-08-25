package corestate

import (
	"errors"
	"math"
	"strings"
	"sync"
	"testing"
)

func serviceLimits(maxServices int, maxBytes uint64) Limits {
	l := validLimits()
	l.MaxGenerations = 2
	l.MaxServices = maxServices
	l.MaxServiceBytes = maxBytes
	l.MaxServiceIdentityBytes = 64
	return l
}

func serviceStoreWithObserver(t *testing.T, maxServices int, maxBytes uint64, observer Observer) *Store {
	t.Helper()
	s, err := NewStore(serviceLimits(maxServices, maxBytes), fakeClock{}, observer)
	if err != nil {
		t.Fatal(err)
	}
	return s
}

func serviceStore(t *testing.T, maxServices int, maxBytes uint64) *Store {
	t.Helper()
	return serviceStoreWithObserver(t, maxServices, maxBytes, nil)
}

func serviceSpec(generation TSGeneration, channelByte byte) ServiceSpec {
	var channel ChannelID
	channel[0] = channelByte
	var serviceDigest ServiceDigest
	serviceDigest[0] = 9
	var routeGrantDigest RouteGrantDigest
	routeGrantDigest[0] = channelByte + 1
	return ServiceSpec{
		Generation:          generation,
		ChannelID:           channel,
		ChannelGeneration:   uint64(channelByte) + 1,
		ServiceIdentity:     "service-" + string(rune('a'+channelByte-1)),
		ServiceDigest:       serviceDigest,
		RouteGrantDigest:    routeGrantDigest,
		AuthorityGeneration: 1,
		CreditState:         1,
	}
}

func exactServiceBytes(t *testing.T, count int) uint64 {
	t.Helper()
	cost, err := serviceCost(serviceSpec(1, 1))
	if err != nil {
		t.Fatal(err)
	}
	return uint64(count) * cost
}

func mustAddService(t *testing.T, s *Store, spec ServiceSpec) ServiceSnapshot {
	t.Helper()
	got, err := s.AddService(spec)
	if err != nil {
		t.Fatal(err)
	}
	return got
}

func mustCloseAndRemoveService(t *testing.T, s *Store, snapshot ServiceSnapshot) {
	t.Helper()
	if err := s.CloseService(snapshot.Generation, snapshot.Handle); err != nil {
		t.Fatal(err)
	}
	if err := s.RemoveService(snapshot.Generation, snapshot.Handle); err != nil {
		t.Fatal(err)
	}
}

func TestServiceEntryCapacityBelow(t *testing.T) {
	s := serviceStore(t, 2, exactServiceBytes(t, 2))
	mustOpen(t, s, 1)
	mustAddService(t, s, serviceSpec(1, 1))
}

func TestServiceEntryCapacityExact(t *testing.T) {
	s := serviceStore(t, 2, exactServiceBytes(t, 2))
	mustOpen(t, s, 1)
	mustAddService(t, s, serviceSpec(1, 1))
	mustAddService(t, s, serviceSpec(1, 2))
}

func TestServiceEntryCapacityAbove(t *testing.T) {
	s := serviceStore(t, 2, exactServiceBytes(t, 3))
	mustOpen(t, s, 1)
	mustAddService(t, s, serviceSpec(1, 1))
	mustAddService(t, s, serviceSpec(1, 2))
	before := s.Usage()
	if _, err := s.AddService(serviceSpec(1, 3)); !errors.Is(err, ErrCapacityExceeded) {
		t.Fatalf("third service error = %v, want ErrCapacityExceeded", err)
	}
	if s.Usage() != before {
		t.Fatal("entry-capacity rejection partially mutated usage")
	}
}

func TestServiceByteCapacityBelow(t *testing.T) {
	s := serviceStore(t, 2, exactServiceBytes(t, 2)+1)
	mustOpen(t, s, 1)
	mustAddService(t, s, serviceSpec(1, 1))
}

func TestServiceByteCapacityExact(t *testing.T) {
	s := serviceStore(t, 2, exactServiceBytes(t, 2))
	mustOpen(t, s, 1)
	mustAddService(t, s, serviceSpec(1, 1))
	mustAddService(t, s, serviceSpec(1, 2))
}

func TestServiceByteCapacityAbove(t *testing.T) {
	s := serviceStore(t, 2, exactServiceBytes(t, 2)-1)
	mustOpen(t, s, 1)
	mustAddService(t, s, serviceSpec(1, 1))
	before := s.Usage()
	if _, err := s.AddService(serviceSpec(1, 2)); !errors.Is(err, ErrByteCapacityExceeded) {
		t.Fatalf("second service error = %v, want ErrByteCapacityExceeded", err)
	}
	if s.Usage() != before {
		t.Fatal("byte-capacity rejection partially mutated usage")
	}
}

func TestServiceValidatesRequiredAndBoundedFields(t *testing.T) {
	valid := serviceSpec(1, 1)
	tests := []struct {
		name   string
		mutate func(*ServiceSpec)
	}{
		{"zero generation", func(s *ServiceSpec) { s.Generation = 0 }},
		{"zero channel", func(s *ServiceSpec) { s.ChannelID = ChannelID{} }},
		{"zero channel generation", func(s *ServiceSpec) { s.ChannelGeneration = 0 }},
		{"empty identity", func(s *ServiceSpec) { s.ServiceIdentity = "" }},
		{"identity too long", func(s *ServiceSpec) { s.ServiceIdentity = strings.Repeat("i", 65) }},
		{"zero route grant digest", func(s *ServiceSpec) { s.RouteGrantDigest = RouteGrantDigest{} }},
		{"zero authority generation", func(s *ServiceSpec) { s.AuthorityGeneration = 0 }},
		{"zero credit state", func(s *ServiceSpec) { s.CreditState = 0 }},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			s := serviceStore(t, 1, 1024)
			mustOpen(t, s, 1)
			spec := valid
			tt.mutate(&spec)
			before := s.Usage()
			if _, err := s.AddService(spec); err == nil {
				t.Fatal("invalid service accepted")
			}
			if s.Usage() != before {
				t.Fatal("invalid service partially mutated usage")
			}
		})
	}
}

func TestServiceRejectsClosedGeneration(t *testing.T) {
	s := serviceStore(t, 1, 1024)
	mustOpen(t, s, 1)
	if err := s.CloseGeneration(1); err != nil {
		t.Fatal(err)
	}
	if _, err := s.AddService(serviceSpec(1, 1)); !errors.Is(err, ErrGenerationClosed) {
		t.Fatalf("closed-generation error = %v, want ErrGenerationClosed", err)
	}
}

func TestServiceRejectsDuplicateChannelWithoutMutation(t *testing.T) {
	s := serviceStore(t, 2, 1024)
	mustOpen(t, s, 1)
	first := mustAddService(t, s, serviceSpec(1, 1))
	duplicate := serviceSpec(1, 1)
	duplicate.ServiceIdentity = "other"
	before := s.Usage()
	if _, err := s.AddService(duplicate); !errors.Is(err, ErrDuplicateService) {
		t.Fatalf("duplicate error = %v, want ErrDuplicateService", err)
	}
	if s.Usage() != before {
		t.Fatal("duplicate rejection partially mutated usage")
	}
	if got, err := s.LookupService(1, first.Handle); err != nil || got.ServiceIdentity != first.ServiceIdentity {
		t.Fatalf("first service changed: got=%+v err=%v", got, err)
	}
}

func TestStableDigestIsNotAuthority(t *testing.T) {
	s := serviceStore(t, 2, 1024)
	mustOpen(t, s, 1)
	a, b := serviceSpec(1, 1), serviceSpec(1, 2)
	b.ServiceDigest = a.ServiceDigest
	first := mustAddService(t, s, a)
	second := mustAddService(t, s, b)
	if first.Handle == second.Handle {
		t.Fatal("digest collapsed services")
	}
}

func TestServiceEqualDigestDoesNotCollapseCrossBindings(t *testing.T) {
	base := serviceSpec(1, 1)
	tests := []struct {
		name   string
		mutate func(*ServiceSpec)
	}{
		{"service identity", func(s *ServiceSpec) { s.ServiceIdentity = "other-service" }},
		{"route grant digest", func(s *ServiceSpec) { s.RouteGrantDigest[0]++ }},
		{"channel generation", func(s *ServiceSpec) { s.ChannelGeneration++ }},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			s := serviceStore(t, 2, 1024)
			mustOpen(t, s, 1)
			mustAddService(t, s, base)
			secondSpec := base
			tt.mutate(&secondSpec)
			before := s.Usage()
			if _, err := s.AddService(secondSpec); !errors.Is(err, ErrDuplicateService) {
				t.Fatalf("one-field variation error = %v, want ErrDuplicateService", err)
			}
			if s.Usage() != before {
				t.Fatal("one-field duplicate rejection partially mutated usage")
			}
			distinctChannel := base
			distinctChannel.ChannelID[0] = 2
			if got := mustAddService(t, s, distinctChannel); got.Handle != 2 {
				t.Fatalf("rejected duplicate consumed handle: got %d, want 2", got.Handle)
			}
		})
	}

	t.Run("channel ID", func(t *testing.T) {
		s := serviceStore(t, 2, 1024)
		mustOpen(t, s, 1)
		first := mustAddService(t, s, base)
		secondSpec := base
		secondSpec.ChannelID[0] = 2
		second := mustAddService(t, s, secondSpec)
		if first.Handle == second.Handle || first.ServiceDigest != second.ServiceDigest {
			t.Fatalf("equal digest affected distinct channel binding: first=%+v second=%+v", first, second)
		}
	})
}

func TestFailedServiceInsertDoesNotConsumeHandle(t *testing.T) {
	s := serviceStore(t, 1, 1024)
	mustOpen(t, s, 1)
	first := mustAddService(t, s, serviceSpec(1, 1))
	if _, err := s.AddService(serviceSpec(1, 2)); !errors.Is(err, ErrCapacityExceeded) {
		t.Fatal(err)
	}
	mustCloseAndRemoveService(t, s, first)
	if got := mustAddService(t, s, serviceSpec(1, 3)).Handle; got != 2 {
		t.Fatal(got)
	}
}

func TestServiceLookupKeyIsolationAndSnapshotOwnership(t *testing.T) {
	s := serviceStore(t, 2, 1024)
	mustOpen(t, s, 1)
	mustOpen(t, s, 2)
	identity := []byte("service-a")
	spec := serviceSpec(1, 1)
	spec.ServiceIdentity = string(identity)
	first := mustAddService(t, s, spec)
	identity[0] = 'X'
	first.ServiceIdentity = "changed"
	secondSpec := serviceSpec(2, 1)
	second := mustAddService(t, s, secondSpec)
	if first.Handle != second.Handle {
		t.Fatalf("generation namespaces not independent: %d != %d", first.Handle, second.Handle)
	}
	got, err := s.LookupService(1, first.Handle)
	if err != nil || got.ServiceIdentity != "service-a" {
		t.Fatalf("owned snapshot = %+v, err=%v", got, err)
	}
	if _, err := s.LookupService(2, first.Handle+1); !errors.Is(err, ErrUnknownService) {
		t.Fatalf("wrong-key lookup error = %v, want ErrUnknownService", err)
	}
	if _, err := s.LookupService(1, InvalidServiceHandle); !errors.Is(err, ErrInvalidHandle) {
		t.Fatalf("zero-handle lookup error = %v, want ErrInvalidHandle", err)
	}
}

func TestServiceCloseAndRemoveOrdering(t *testing.T) {
	s := serviceStore(t, 1, 1024)
	mustOpen(t, s, 1)
	added := mustAddService(t, s, serviceSpec(1, 1))
	if err := s.RemoveService(1, added.Handle); !errors.Is(err, ErrInvalidTransition) {
		t.Fatalf("active removal error = %v, want ErrInvalidTransition", err)
	}
	if err := s.CloseService(1, added.Handle); err != nil {
		t.Fatal(err)
	}
	if got, err := s.LookupService(1, added.Handle); err != nil || got.State != ServiceClosed {
		t.Fatalf("closed lookup = %+v, err=%v", got, err)
	}
	if err := s.CloseService(1, added.Handle); !errors.Is(err, ErrServiceClosed) {
		t.Fatalf("second close error = %v, want ErrServiceClosed", err)
	}
	if err := s.RemoveService(1, added.Handle); err != nil {
		t.Fatal(err)
	}
	if _, err := s.LookupService(1, added.Handle); !errors.Is(err, ErrUnknownService) {
		t.Fatalf("removed lookup error = %v, want ErrUnknownService", err)
	}
	if got := s.Usage(); got.Services != 0 || got.ServiceBytes != 0 {
		t.Fatalf("usage after removal = %+v", got)
	}
}

func TestServiceRemoveRejectsActiveStreamsAndPreservesReverseIndex(t *testing.T) {
	s := serviceStore(t, 1, 1024)
	mustOpen(t, s, 1)
	added := mustAddService(t, s, serviceSpec(1, 1))
	s.mu.Lock()
	if err := s.incrementStreamsLocked(1, added.Handle); err != nil {
		s.mu.Unlock()
		t.Fatal(err)
	}
	s.mu.Unlock()
	if err := s.CloseService(1, added.Handle); err != nil {
		t.Fatal(err)
	}
	if err := s.RemoveService(1, added.Handle); !errors.Is(err, ErrInvalidTransition) {
		t.Fatalf("streamed removal error = %v, want ErrInvalidTransition", err)
	}
	s.mu.Lock()
	if err := s.decrementStreamsLocked(1, added.Handle); err != nil {
		s.mu.Unlock()
		t.Fatal(err)
	}
	s.mu.Unlock()
	if err := s.RemoveService(1, added.Handle); err != nil {
		t.Fatal(err)
	}
	if got := mustAddService(t, s, serviceSpec(1, 1)); got.Handle != 2 {
		t.Fatalf("reinserted handle = %d, want 2", got.Handle)
	}
}

func TestServiceStreamCountOverflowUnderflowAndClosedProtection(t *testing.T) {
	s := serviceStore(t, 1, 1024)
	mustOpen(t, s, 1)
	added := mustAddService(t, s, serviceSpec(1, 1))
	key := serviceKey{generation: 1, handle: added.Handle}
	s.mu.Lock()
	entry := s.services[key]
	entry.ActiveStreams = math.MaxUint64
	s.services[key] = entry
	err := s.incrementStreamsLocked(1, added.Handle)
	entry = s.services[key]
	entry.ActiveStreams = 0
	s.services[key] = entry
	underflowErr := s.decrementStreamsLocked(1, added.Handle)
	s.mu.Unlock()
	if !errors.Is(err, ErrAccountingOverflow) || !errors.Is(underflowErr, ErrInvalidTransition) {
		t.Fatalf("count errors = (%v, %v)", err, underflowErr)
	}
	if err := s.CloseService(1, added.Handle); err != nil {
		t.Fatal(err)
	}
	s.mu.Lock()
	err = s.incrementStreamsLocked(1, added.Handle)
	s.mu.Unlock()
	if !errors.Is(err, ErrServiceClosed) {
		t.Fatalf("closed increment error = %v, want ErrServiceClosed", err)
	}
}

type reentrantServiceObserver struct {
	store  *Store
	events []Event
}

func (o *reentrantServiceObserver) Observe(event Event) {
	_ = o.store.Usage()
	o.events = append(o.events, event)
}

func TestServiceObserverRunsAfterUnlockForEveryMutation(t *testing.T) {
	observer := &reentrantServiceObserver{}
	s := serviceStoreWithObserver(t, 1, 1024, observer)
	observer.store = s
	mustOpen(t, s, 1)
	added := mustAddService(t, s, serviceSpec(1, 1))
	mustCloseAndRemoveService(t, s, added)
	want := []Event{
		{Kind: EventServiceInserted},
		{Kind: EventServiceClosed},
		{Kind: EventServiceRemoved},
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

func TestServiceConcurrentAddUsesUniqueMonotonicHandlesAndExactUsage(t *testing.T) {
	s := serviceStore(t, 8, exactServiceBytes(t, 8))
	mustOpen(t, s, 1)
	var wg sync.WaitGroup
	results := make(chan ServiceSnapshot, 8)
	errs := make(chan error, 8)
	for i := 1; i <= 8; i++ {
		wg.Add(1)
		go func(channelByte byte) {
			defer wg.Done()
			got, err := s.AddService(serviceSpec(1, channelByte))
			if err != nil {
				errs <- err
				return
			}
			results <- got
		}(byte(i))
	}
	wg.Wait()
	close(results)
	close(errs)
	for err := range errs {
		t.Fatal(err)
	}
	seen := make(map[ServiceHandle]bool)
	var bytes uint64
	for result := range results {
		seen[result.Handle] = true
		bytes += result.AccountedBytes
	}
	for want := ServiceHandle(1); want <= 8; want++ {
		if !seen[want] {
			t.Fatalf("missing monotonic handle %d from %#v", want, seen)
		}
	}
	if got := s.Usage(); got.Services != 8 || got.ServiceBytes != bytes {
		t.Fatalf("usage = %+v, want services=8 bytes=%d", got, bytes)
	}
}
