package corestate

import (
	"errors"
	"math"
	"testing"
)

type propertySeed struct {
	name string
	ops  []byte
	seam func(*testing.T)
}

var propertyCorpus = []propertySeed{
	{name: "mapping-add", ops: []byte{0x00}},
	{name: "mapping-acquire", ops: []byte{0x00, 0x01}},
	{name: "mapping-acquire-release-remove-then-add", ops: []byte{0x00, 0x01, 0x02, 0x03, 0x00}},
	{name: "mapping-acquire-remove-rejects", ops: []byte{0x00, 0x01, 0x03}},
	{name: "mapping-acquire-release-remove", ops: []byte{0x00, 0x01, 0x02, 0x03}},
	{name: "mapping-expire-then-add", ops: []byte{0x00, 0xdf, 0x00}},
	{name: "mapping-exhaustion-seam", ops: []byte{0x00}, seam: assertMappingIDExhaustionSeam},
	{name: "service-add", ops: []byte{0x20}},
	{name: "service-close", ops: []byte{0x20, 0x60}},
	{name: "service-remove", ops: []byte{0x20, 0x60, 0xc1}},
	{name: "stream-add", ops: []byte{0x20, 0x40}},
	{name: "stream-finish", ops: []byte{0x20, 0x40, 0x80}},
	{name: "stream-cancel", ops: []byte{0x20, 0x40, 0xa0}},
	{name: "stream-remove", ops: []byte{0x20, 0x40, 0x80, 0xc2}},
	{name: "service-removal-after-stream-removal", ops: []byte{0x20, 0x40, 0x80, 0xc2, 0x60, 0xc1}},
	{name: "generation-close", ops: []byte{0xe0}},
	{name: "generation-close-rejects-stale-service", ops: []byte{0xe0, 0x20}},
	{name: "generation-capacity-below-exact-above", ops: []byte{0x20}, seam: assertGenerationCapacitySeam},
	{name: "mixed-lifecycle", ops: []byte{0x00, 0x20, 0x40, 0x80, 0xc2, 0x60, 0xc1, 0x03}},
	{name: "all-operation-classes", ops: []byte{0x00, 0x01, 0x02, 0x20, 0x40, 0x60, 0x80, 0xa0, 0xc0, 0xe0}},
}

func TestPropertyCorpus(t *testing.T) {
	for _, seed := range propertyCorpus {
		t.Run(seed.name, func(t *testing.T) {
			if seed.seam != nil {
				seed.seam(t)
			}
			s := fuzzStore(t)
			runOperations(t, s, seed.ops)
			assertStoreHealthy(t, s)
		})
	}
}

func FuzzBoundedLifecycle(f *testing.F) {
	f.Add([]byte{0x00, 0x21, 0x42, 0x63, 0x84, 0xa5, 0xc6})
	f.Add([]byte{0xff, 0xff, 0x00, 0x40, 0x80, 0xc0})
	f.Fuzz(func(t *testing.T, ops []byte) {
		if len(ops) > 256 {
			ops = ops[:256]
		}
		s := fuzzStore(t)
		runOperations(t, s, ops)
		assertWithinLimits(t, s)
		if err := s.ValidateInvariants(); err != nil {
			t.Fatal(err)
		}
	})
}

func fuzzStore(t *testing.T) *Store {
	t.Helper()
	limits := validLimits()
	limits.MaxGenerations = 4
	limits.MaxMappings = 8
	limits.MaxServices = 8
	limits.MaxStreams = 32
	limits.MaxMappingBytes = 4096
	limits.MaxServiceBytes = 4096
	limits.MaxStreamBytes = 4096
	limits.MaxServiceIdentityBytes = 64
	limits.MaxPolicyContextBytes = 64
	s, err := NewStore(limits, newFakeClock(1), nil)
	if err != nil {
		t.Fatal(err)
	}
	for generation := TSGeneration(1); generation <= TSGeneration(limits.MaxGenerations); generation++ {
		if err := s.OpenGeneration(generation); err != nil {
			t.Fatal(err)
		}
	}
	return s
}

type lifecycleObservations struct {
	handles  map[TSGeneration]map[ServiceHandle]struct{}
	mappings map[MappingID]struct{}
}

func runOperations(t *testing.T, s *Store, ops []byte) {
	t.Helper()
	observed := lifecycleObservations{
		handles:  make(map[TSGeneration]map[ServiceHandle]struct{}),
		mappings: make(map[MappingID]struct{}),
	}
	for index, op := range ops {
		arg := op & 0x1f
		var err error
		switch op >> 5 {
		case 0:
			err = runMappingOperation(t, s, &observed, arg)
		case 1:
			var snapshot ServiceSnapshot
			snapshot, err = s.AddService(fuzzServiceSpec(arg))
			if err == nil {
				seen := observed.handles[snapshot.Generation]
				if seen == nil {
					seen = make(map[ServiceHandle]struct{})
					observed.handles[snapshot.Generation] = seen
				}
				if _, duplicate := seen[snapshot.Handle]; duplicate {
					t.Fatalf("operation %d reused service handle %d in generation %d", index, snapshot.Handle, snapshot.Generation)
				}
				seen[snapshot.Handle] = struct{}{}
			}
		case 2:
			err = s.InsertStream(fuzzStreamSpec(arg))
		case 3:
			err = s.CloseService(fuzzGeneration(arg), fuzzHandle(arg))
		case 4:
			err = s.FinishStream(fuzzGeneration(arg), fuzzHandle(arg), fuzzStreamID(arg), TerminalCompleted)
		case 5:
			err = s.CancelStream(fuzzGeneration(arg), fuzzHandle(arg), fuzzStreamID(arg))
		case 6:
			err = runRemoveOperation(t, s, arg)
		case 7:
			err = s.CloseGeneration(fuzzGeneration(arg))
		}
		assertAllowedRejection(t, err)
		assertStoreHealthy(t, s)
	}
}

func runMappingOperation(t *testing.T, s *Store, observed *lifecycleObservations, arg byte) error {
	id := MappingID(arg>>2) + 1
	switch arg & 3 {
	case 0:
		snapshot, err := s.AddMapping(fuzzMappingSpec(arg))
		if err != nil {
			return err
		}
		if _, duplicate := observed.mappings[snapshot.ID]; duplicate {
			t.Fatalf("mapping ID %d reused after removal or expiry", snapshot.ID)
		}
		observed.mappings[snapshot.ID] = struct{}{}
		return nil
	case 1:
		_, err := s.AcquireMapping(id)
		return err
	case 2:
		return s.ReleaseMapping(id)
	default:
		return s.RemoveMapping(id)
	}
}

func runRemoveOperation(t *testing.T, s *Store, arg byte) error {
	switch arg & 3 {
	case 0:
		return s.RemoveMapping(MappingID(arg>>2) + 1)
	case 1:
		return s.RemoveService(fuzzRemoveGeneration(arg), fuzzRemoveHandle(arg))
	case 2:
		return s.RemoveStream(fuzzRemoveGeneration(arg), fuzzRemoveHandle(arg), StreamID(arg>>4))
	default:
		clock, ok := s.clock.(*mutableClock)
		if !ok {
			t.Fatal("fuzz store does not use mutable clock")
		}
		clock.set(100)
		_, err := s.ExpireMappings()
		return err
	}
}

func fuzzMappingSpec(arg byte) MappingSpec {
	return MappingSpec{
		ServiceIdentity: "fuzz-mapping-" + string(rune('a'+arg)),
		ExpiresAtUnix:   10,
		PolicyContext:   PolicyContext("fuzz-policy"),
	}
}

func fuzzServiceSpec(arg byte) ServiceSpec {
	return serviceSpec(fuzzGeneration(arg), arg+1)
}

func fuzzStreamSpec(arg byte) StreamSpec {
	return StreamSpec{
		Generation:  fuzzGeneration(arg),
		Handle:      fuzzHandle(arg),
		StreamID:    fuzzStreamID(arg),
		LocalFlowID: LocalFlowID(arg) + 1,
	}
}

func fuzzGeneration(arg byte) TSGeneration { return TSGeneration(arg>>3) + 1 }

func fuzzHandle(arg byte) ServiceHandle { return ServiceHandle(arg&7) + 1 }

func fuzzStreamID(arg byte) StreamID { return StreamID(arg >> 3) }

func fuzzRemoveGeneration(arg byte) TSGeneration { return TSGeneration((arg>>2)&3) + 1 }

func fuzzRemoveHandle(arg byte) ServiceHandle { return ServiceHandle(arg>>4) + 1 }

func assertAllowedRejection(t *testing.T, err error) {
	t.Helper()
	if err == nil {
		return
	}
	for _, allowed := range []error{
		ErrUnknownMapping,
		ErrExpiredMapping,
		ErrUnknownService,
		ErrDuplicateService,
		ErrDuplicateStream,
		ErrCapacityExceeded,
		ErrByteCapacityExceeded,
		ErrGenerationClosed,
		ErrServiceClosed,
		ErrInvalidTransition,
	} {
		if errors.Is(err, allowed) {
			return
		}
	}
	t.Fatalf("operation returned undocumented rejection: %v", err)
}

func assertWithinLimits(t *testing.T, s *Store) {
	t.Helper()
	usage := s.Usage()
	if usage.Mappings < 0 || usage.Services < 0 || usage.Streams < 0 ||
		usage.Mappings > s.limits.MaxMappings || usage.Services > s.limits.MaxServices || usage.Streams > s.limits.MaxStreams ||
		usage.MappingBytes > s.limits.MaxMappingBytes || usage.ServiceBytes > s.limits.MaxServiceBytes || usage.StreamBytes > s.limits.MaxStreamBytes {
		t.Fatalf("usage outside limits: %+v", usage)
	}
}

func assertStoreHealthy(t *testing.T, s *Store) {
	t.Helper()
	assertWithinLimits(t, s)
	if err := s.ValidateInvariants(); err != nil {
		t.Fatal(err)
	}
}

func assertMappingIDExhaustionSeam(t *testing.T) {
	t.Helper()
	s := fuzzStore(t)
	s.mu.Lock()
	s.highestMappingID = MappingID(math.MaxUint64)
	s.mu.Unlock()
	if _, err := s.AddMapping(fuzzMappingSpec(0)); !errors.Is(err, ErrMappingIDExhausted) {
		t.Fatalf("mapping exhaustion error = %v, want ErrMappingIDExhausted", err)
	}
	assertStoreHealthy(t, s)
}

func assertGenerationCapacitySeam(t *testing.T) {
	t.Helper()
	limits := validLimits()
	limits.MaxGenerations = 2
	s, err := NewStore(limits, newFakeClock(1), nil)
	if err != nil {
		t.Fatal(err)
	}
	if err := s.OpenGeneration(1); err != nil {
		t.Fatalf("below capacity: %v", err)
	}
	assertStoreHealthy(t, s)
	if err := s.OpenGeneration(2); err != nil {
		t.Fatalf("exact capacity: %v", err)
	}
	assertStoreHealthy(t, s)
	if err := s.OpenGeneration(3); !errors.Is(err, ErrCapacityExceeded) {
		t.Fatalf("above capacity error = %v, want ErrCapacityExceeded", err)
	}
	assertStoreHealthy(t, s)
}
