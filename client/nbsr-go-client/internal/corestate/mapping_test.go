package corestate

import (
	"errors"
	"math"
	"strings"
	"sync"
	"testing"
)

type mutableClock struct {
	mu  sync.Mutex
	now uint64
}

func newFakeClock(now uint64) *mutableClock { return &mutableClock{now: now} }

func (c *mutableClock) NowUnix() uint64 {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.now
}

func (c *mutableClock) set(now uint64) {
	c.mu.Lock()
	c.now = now
	c.mu.Unlock()
}

func mappingSpec(n int) MappingSpec {
	return MappingSpec{
		ServiceIdentity: "service-" + string(rune('a'+n-1)),
		ExpiresAtUnix:   100,
		PolicyContext:   PolicyContext("policy"),
	}
}

func mappingLimits(maxMappings int, maxBytes uint64) Limits {
	l := validLimits()
	l.MaxMappings = maxMappings
	l.MaxMappingBytes = maxBytes
	l.MaxServiceIdentityBytes = 64
	l.MaxPolicyContextBytes = 64
	return l
}

func mappingStoreAt(t *testing.T, clock Clock, maxMappings int, maxBytes uint64) *Store {
	t.Helper()
	s, err := NewStore(mappingLimits(maxMappings, maxBytes), clock, nil)
	if err != nil {
		t.Fatal(err)
	}
	return s
}

func mappingStore(t *testing.T, maxMappings int, maxBytes uint64) *Store {
	t.Helper()
	return mappingStoreAt(t, newFakeClock(1), maxMappings, maxBytes)
}

func exactMappingBytes(t *testing.T, count int) uint64 {
	t.Helper()
	cost, err := mappingCost(mappingSpec(1))
	if err != nil {
		t.Fatal(err)
	}
	return uint64(count) * cost
}

func mustAddMapping(t *testing.T, s *Store, spec MappingSpec) MappingSnapshot {
	t.Helper()
	got, err := s.AddMapping(spec)
	if err != nil {
		t.Fatal(err)
	}
	return got
}

func TestMappingEntryCapacityBelow(t *testing.T) {
	s := mappingStore(t, 2, exactMappingBytes(t, 2))
	mustAddMapping(t, s, mappingSpec(1))
}

func TestMappingEntryCapacityExact(t *testing.T) {
	s := mappingStore(t, 2, exactMappingBytes(t, 2))
	mustAddMapping(t, s, mappingSpec(1))
	mustAddMapping(t, s, mappingSpec(2))
}

func TestMappingEntryCapacityAbove(t *testing.T) {
	s := mappingStore(t, 2, exactMappingBytes(t, 3))
	mustAddMapping(t, s, mappingSpec(1))
	mustAddMapping(t, s, mappingSpec(2))
	before := s.Usage()
	if _, err := s.AddMapping(mappingSpec(3)); !errors.Is(err, ErrCapacityExceeded) {
		t.Fatalf("third mapping error = %v, want ErrCapacityExceeded", err)
	}
	if s.Usage() != before {
		t.Fatal("entry-capacity rejection partially mutated usage")
	}
}

func TestMappingByteCapacityBelow(t *testing.T) {
	s := mappingStore(t, 2, exactMappingBytes(t, 2)+1)
	mustAddMapping(t, s, mappingSpec(1))
}

func TestMappingByteCapacityExact(t *testing.T) {
	s := mappingStore(t, 2, exactMappingBytes(t, 2))
	mustAddMapping(t, s, mappingSpec(1))
	mustAddMapping(t, s, mappingSpec(2))
}

func TestMappingByteCapacityAbove(t *testing.T) {
	s := mappingStore(t, 2, exactMappingBytes(t, 2)-1)
	mustAddMapping(t, s, mappingSpec(1))
	before := s.Usage()
	if _, err := s.AddMapping(mappingSpec(2)); !errors.Is(err, ErrByteCapacityExceeded) {
		t.Fatalf("second mapping error = %v, want ErrByteCapacityExceeded", err)
	}
	if s.Usage() != before {
		t.Fatal("byte-capacity rejection partially mutated usage")
	}
}

func TestMappingValidatesRequiredAndBoundedFields(t *testing.T) {
	s := mappingStore(t, 4, 1024)
	tests := []struct {
		name string
		spec MappingSpec
	}{
		{"empty identity", MappingSpec{ExpiresAtUnix: 100}},
		{"zero expiry", MappingSpec{ServiceIdentity: "service"}},
		{"identity too long", MappingSpec{ServiceIdentity: strings.Repeat("i", 65), ExpiresAtUnix: 100}},
		{"policy too long", MappingSpec{ServiceIdentity: "service", ExpiresAtUnix: 100, PolicyContext: PolicyContext(strings.Repeat("p", 65))}},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			before := s.Usage()
			if _, err := s.AddMapping(tt.spec); err == nil {
				t.Fatal("invalid mapping accepted")
			}
			if s.Usage() != before {
				t.Fatal("invalid mapping partially mutated usage")
			}
		})
	}
}

func TestMappingConflictDoesNotReplaceIdentity(t *testing.T) {
	s := mappingStore(t, 2, 1024)
	added := mustAddMapping(t, s, mappingSpec(1))
	different := mappingSpec(2)
	cost, err := mappingCost(different)
	if err != nil {
		t.Fatal(err)
	}
	s.mu.Lock()
	err = s.insertMappingWithIDLocked(added.ID, different, cost)
	s.mu.Unlock()
	if !errors.Is(err, ErrMappingConflict) {
		t.Fatalf("conflict error = %v, want ErrMappingConflict", err)
	}
	got, err := s.LookupMapping(added.ID)
	if err != nil {
		t.Fatal(err)
	}
	if got.ServiceIdentity != added.ServiceIdentity {
		t.Fatalf("identity replaced with %q", got.ServiceIdentity)
	}
}

func TestMappingExactExpiryCannotBeReturnedOrAcquired(t *testing.T) {
	clock := newFakeClock(50)
	s := mappingStoreAt(t, clock, 1, 1024)
	spec := mappingSpec(1)
	spec.ExpiresAtUnix = 50
	added := mustAddMapping(t, s, spec)
	if _, err := s.LookupMapping(added.ID); !errors.Is(err, ErrExpiredMapping) {
		t.Fatalf("lookup error = %v, want ErrExpiredMapping", err)
	}
	if _, err := s.AcquireMapping(added.ID); !errors.Is(err, ErrExpiredMapping) {
		t.Fatalf("acquire error = %v, want ErrExpiredMapping", err)
	}
	if got := s.Usage(); got.Mappings != 1 {
		t.Fatalf("expiry performed implicit cleanup: mappings = %d", got.Mappings)
	}
}

func TestMappingAcquireReleaseCountsExactly(t *testing.T) {
	s := mappingStore(t, 1, 1024)
	added := mustAddMapping(t, s, mappingSpec(1))
	acquired, err := s.AcquireMapping(added.ID)
	if err != nil {
		t.Fatal(err)
	}
	if acquired.ActiveReferences != 1 {
		t.Fatalf("references = %d, want 1", acquired.ActiveReferences)
	}
	if err := s.ReleaseMapping(added.ID); err != nil {
		t.Fatal(err)
	}
	got, err := s.LookupMapping(added.ID)
	if err != nil {
		t.Fatal(err)
	}
	if got.ActiveReferences != 0 {
		t.Fatalf("references = %d, want 0", got.ActiveReferences)
	}
	if err := s.ReleaseMapping(added.ID); !errors.Is(err, ErrInvalidTransition) {
		t.Fatalf("underflow error = %v, want ErrInvalidTransition", err)
	}
}

func TestMappingAcquireOverflowFailsClosed(t *testing.T) {
	s := mappingStore(t, 1, 1024)
	added := mustAddMapping(t, s, mappingSpec(1))
	s.mu.Lock()
	entry := s.mappings[added.ID]
	entry.snapshot.ActiveReferences = math.MaxUint64
	s.mappings[added.ID] = entry
	s.mu.Unlock()
	if _, err := s.AcquireMapping(added.ID); !errors.Is(err, ErrAccountingOverflow) {
		t.Fatalf("overflow error = %v, want ErrAccountingOverflow", err)
	}
}

func TestMappingRemovalRejectsLiveReference(t *testing.T) {
	s := mappingStore(t, 1, 1024)
	added := mustAddMapping(t, s, mappingSpec(1))
	if _, err := s.AcquireMapping(added.ID); err != nil {
		t.Fatal(err)
	}
	before := s.Usage()
	if err := s.RemoveMapping(added.ID); !errors.Is(err, ErrInvalidTransition) {
		t.Fatalf("remove error = %v, want ErrInvalidTransition", err)
	}
	if s.Usage() != before {
		t.Fatal("rejected removal partially mutated usage")
	}
}

func TestMappingStaleIDNeverAliasesLaterInsertion(t *testing.T) {
	s := mappingStore(t, 1, 1024)
	first := mustAddMapping(t, s, mappingSpec(1))
	if err := s.RemoveMapping(first.ID); err != nil {
		t.Fatal(err)
	}
	second := mustAddMapping(t, s, mappingSpec(2))
	if second.ID <= first.ID {
		t.Fatalf("mapping ID reused: first=%d second=%d", first.ID, second.ID)
	}
	if _, err := s.LookupMapping(first.ID); !errors.Is(err, ErrUnknownMapping) {
		t.Fatalf("stale lookup error = %v, want ErrUnknownMapping", err)
	}
}

func TestMappingRepeatedAddRemoveCyclesNeverReuseIDs(t *testing.T) {
	s := mappingStore(t, 1, 1024)
	for want := MappingID(1); want <= 32; want++ {
		added := mustAddMapping(t, s, mappingSpec(1))
		if added.ID != want {
			t.Fatalf("cycle ID = %d, want %d", added.ID, want)
		}
		if err := s.RemoveMapping(added.ID); err != nil {
			t.Fatal(err)
		}
	}
}

func TestMappingIDOverflowFailsClosed(t *testing.T) {
	s := mappingStore(t, 1, 1024)
	s.mu.Lock()
	s.highestMappingID = MappingID(math.MaxUint64)
	s.mu.Unlock()
	before := s.Usage()
	if _, err := s.AddMapping(mappingSpec(1)); !errors.Is(err, ErrMappingIDExhausted) {
		t.Fatalf("overflow error = %v, want ErrMappingIDExhausted", err)
	}
	if s.Usage() != before {
		t.Fatal("ID overflow partially mutated usage")
	}
}

type reentrantMappingObserver struct {
	store  *Store
	events []Event
}

func (o *reentrantMappingObserver) Observe(event Event) {
	_ = o.store.Usage()
	o.events = append(o.events, event)
}

func TestMappingObserverRunsAfterUnlockForInsertAndRemoveOnly(t *testing.T) {
	observer := &reentrantMappingObserver{}
	s, err := NewStore(mappingLimits(1, 1024), newFakeClock(1), observer)
	if err != nil {
		t.Fatal(err)
	}
	observer.store = s
	added := mustAddMapping(t, s, mappingSpec(1))
	if _, err := s.AcquireMapping(added.ID); err != nil {
		t.Fatal(err)
	}
	if err := s.ReleaseMapping(added.ID); err != nil {
		t.Fatal(err)
	}
	if err := s.RemoveMapping(added.ID); err != nil {
		t.Fatal(err)
	}
	if len(observer.events) != 2 || observer.events[0] != (Event{Kind: EventMappingInserted, MappingID: added.ID}) || observer.events[1] != (Event{Kind: EventMappingRemoved, MappingID: added.ID}) {
		t.Fatalf("events = %#v, want insert then remove", observer.events)
	}
}

type panicMappingObserver struct{ calls int }

func (o *panicMappingObserver) Observe(Event) {
	o.calls++
	panic("observer panic")
}

func TestMappingObserverPanicPropagatesAfterCommit(t *testing.T) {
	observer := &panicMappingObserver{}
	s, err := NewStore(mappingLimits(1, 1024), newFakeClock(1), observer)
	if err != nil {
		t.Fatal(err)
	}
	func() {
		defer func() {
			if recover() == nil {
				t.Fatal("observer panic did not propagate")
			}
		}()
		_, _ = s.AddMapping(mappingSpec(1))
	}()
	if observer.calls != 1 || s.Usage().Mappings != 1 {
		t.Fatalf("committed state after panic: calls=%d usage=%+v", observer.calls, s.Usage())
	}
}

type firstPanicMappingObserver struct {
	events       []Event
	panicOnFirst bool
}

func (o *firstPanicMappingObserver) Observe(event Event) {
	o.events = append(o.events, event)
	if o.panicOnFirst && len(o.events) == 1 {
		panic("first observer panic")
	}
}

func TestMappingExpiryDispatchesEveryCommittedRemovalBeforeRepanicking(t *testing.T) {
	clock := newFakeClock(1)
	observer := &firstPanicMappingObserver{}
	s, err := NewStore(mappingLimits(2, 1024), clock, observer)
	if err != nil {
		t.Fatal(err)
	}
	first := mustAddMapping(t, s, mappingSpec(1))
	second := mustAddMapping(t, s, mappingSpec(2))
	observer.events = nil
	observer.panicOnFirst = true
	clock.set(100)

	var recovered any
	func() {
		defer func() { recovered = recover() }()
		_, _ = s.ExpireMappings()
	}()
	if recovered != "first observer panic" {
		t.Fatalf("recovered = %v, want first observer panic", recovered)
	}
	if len(observer.events) != 2 {
		t.Fatalf("removal events = %d, want 2", len(observer.events))
	}
	seen := map[MappingID]bool{}
	for _, event := range observer.events {
		if event.Kind != EventMappingRemoved {
			t.Fatalf("event kind = %d, want EventMappingRemoved", event.Kind)
		}
		seen[event.MappingID] = true
	}
	if !seen[first.ID] || !seen[second.ID] {
		t.Fatalf("events = %#v, want removals for %d and %d", observer.events, first.ID, second.ID)
	}
	if got := s.Usage(); got.Mappings != 0 || got.MappingBytes != 0 {
		t.Fatalf("usage after observer panic = %+v, want zero mappings", got)
	}
}

func TestMappingExpiryIsSynchronousAndReferenceSafe(t *testing.T) {
	clock := newFakeClock(1)
	s := mappingStoreAt(t, clock, 2, 1024)
	first := mustAddMapping(t, s, mappingSpec(1))
	second := mustAddMapping(t, s, mappingSpec(2))
	if _, err := s.AcquireMapping(second.ID); err != nil {
		t.Fatal(err)
	}
	clock.set(100)
	if removed, err := s.ExpireMappings(); !errors.Is(err, ErrInvalidTransition) || removed != 1 {
		t.Fatalf("ExpireMappings = (%d, %v), want (1, ErrInvalidTransition)", removed, err)
	}
	if _, err := s.LookupMapping(first.ID); !errors.Is(err, ErrUnknownMapping) {
		t.Fatalf("first lookup error = %v, want ErrUnknownMapping", err)
	}
	if err := s.ReleaseMapping(second.ID); err != nil {
		t.Fatal(err)
	}
	if removed, err := s.ExpireMappings(); err != nil || removed != 1 {
		t.Fatalf("second ExpireMappings = (%d, %v), want (1, nil)", removed, err)
	}
}

func TestMappingAccountingReconcilesAfterRemoval(t *testing.T) {
	s := mappingStore(t, 2, 1024)
	a := mustAddMapping(t, s, mappingSpec(1))
	b := mustAddMapping(t, s, mappingSpec(2))
	wantBytes := a.AccountedBytes + b.AccountedBytes
	if got := s.Usage(); got.Mappings != 2 || got.MappingBytes != wantBytes {
		t.Fatalf("usage = %+v, want mappings=2 bytes=%d", got, wantBytes)
	}
	if err := s.RemoveMapping(a.ID); err != nil {
		t.Fatal(err)
	}
	if got := s.Usage(); got.Mappings != 1 || got.MappingBytes != b.AccountedBytes {
		t.Fatalf("usage after removal = %+v, want mappings=1 bytes=%d", got, b.AccountedBytes)
	}
}

func TestMappingCopiesOwnedStringsAndReturnedSnapshots(t *testing.T) {
	s := mappingStore(t, 1, 1024)
	identityBytes := []byte("service-a")
	policyBytes := []byte("policy")
	added := mustAddMapping(t, s, MappingSpec{ServiceIdentity: string(identityBytes), ExpiresAtUnix: 100, PolicyContext: PolicyContext(string(policyBytes))})
	identityBytes[0] = 'X'
	policyBytes[0] = 'X'
	added.ServiceIdentity = "changed"
	added.PolicyContext = "changed"
	got, err := s.LookupMapping(added.ID)
	if err != nil {
		t.Fatal(err)
	}
	if got.ServiceIdentity != "service-a" || got.PolicyContext != "policy" {
		t.Fatalf("stored strings changed: identity=%q policy=%q", got.ServiceIdentity, got.PolicyContext)
	}
}

func TestMappingConcurrentAcquireReleaseEndsAtZero(t *testing.T) {
	s := mappingStore(t, 1, 1024)
	added := mustAddMapping(t, s, mappingSpec(1))
	var wg sync.WaitGroup
	errs := make(chan error, 8)
	for range 8 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for range 250 {
				if _, err := s.AcquireMapping(added.ID); err != nil {
					errs <- err
					return
				}
				if err := s.ReleaseMapping(added.ID); err != nil {
					errs <- err
					return
				}
			}
		}()
	}
	wg.Wait()
	close(errs)
	for err := range errs {
		t.Fatal(err)
	}
	got, err := s.LookupMapping(added.ID)
	if err != nil {
		t.Fatal(err)
	}
	if got.ActiveReferences != 0 {
		t.Fatalf("final references = %d, want 0", got.ActiveReferences)
	}
}
