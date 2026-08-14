package corestate

import (
	"os"
	"strings"
	"testing"
)

func TestPackageDocumentationStatesSecurityBoundaries(t *testing.T) {
	documentation, err := os.ReadFile("doc.go")
	if err != nil {
		t.Fatal(err)
	}
	for _, statement := range []string{
		"ServiceHandle is a local-only",
		"channel_id remains the wire identity",
		"logical bytes are not heap bytes",
		"no network behavior",
	} {
		if !strings.Contains(string(documentation), statement) {
			t.Fatalf("package documentation must state %q", statement)
		}
	}
}

// BASELINE ONLY — NOT ACCEPTANCE CAPACITY.
func BenchmarkBaselineOnlyMappingLookup(b *testing.B) {
	s := benchmarkStore(b)
	mapping := mustAddMappingB(b, s, mappingSpec(1))
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		if _, err := s.LookupMapping(mapping.ID); err != nil {
			b.Fatal(err)
		}
	}
}

// BASELINE ONLY — NOT ACCEPTANCE CAPACITY.
func BenchmarkBaselineOnlyMappingInsertRemove(b *testing.B) {
	s := benchmarkStore(b)
	spec := mappingSpec(1)
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		mapping := mustAddMappingB(b, s, spec)
		mustRemoveMappingB(b, s, mapping.ID)
	}
}

// BASELINE ONLY — NOT ACCEPTANCE CAPACITY.
func BenchmarkBaselineOnlyServiceLookup(b *testing.B) {
	s, service := benchmarkStoreWithService(b)
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		if _, err := s.LookupService(service.Generation, service.Handle); err != nil {
			b.Fatal(err)
		}
	}
}

// BASELINE ONLY — NOT ACCEPTANCE CAPACITY.
func BenchmarkBaselineOnlyServiceInsertRemove(b *testing.B) {
	s := benchmarkStore(b)
	mustOpenB(b, s, 1)
	spec := serviceSpec(1, 1)
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		service := mustAddServiceB(b, s, spec)
		mustCloseAndRemoveServiceB(b, s, service)
	}
}

// BASELINE ONLY — NOT ACCEPTANCE CAPACITY.
func BenchmarkBaselineOnlyStreamLookup(b *testing.B) {
	s, service := benchmarkStoreWithService(b)
	spec := streamSpec(service, 4)
	mustInsertStreamB(b, s, spec)
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		if _, err := s.LookupStream(spec.Generation, spec.Handle, spec.StreamID); err != nil {
			b.Fatal(err)
		}
	}
}

// BASELINE ONLY — NOT ACCEPTANCE CAPACITY.
func BenchmarkBaselineOnlyStreamInsertRemove(b *testing.B) {
	s, service := benchmarkStoreWithService(b)
	spec := streamSpec(service, 4)
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		mustInsertStreamB(b, s, spec)
		mustCancelAndRemoveStreamB(b, s, spec)
	}
}

func benchmarkStore(b *testing.B) *Store {
	b.Helper()
	limits := validLimits()
	limits.MaxGenerations = 1
	limits.MaxMappings = 1
	limits.MaxServices = 1
	limits.MaxStreams = 1
	limits.MaxMappingBytes = 1024
	limits.MaxServiceBytes = 1024
	limits.MaxStreamBytes = 1024
	limits.MaxServiceIdentityBytes = 64
	limits.MaxPolicyContextBytes = 64
	s, err := NewStore(limits, fakeClock{}, nil)
	if err != nil {
		b.Fatal(err)
	}
	return s
}

func benchmarkStoreWithService(b *testing.B) (*Store, ServiceSnapshot) {
	b.Helper()
	s := benchmarkStore(b)
	mustOpenB(b, s, 1)
	return s, mustAddServiceB(b, s, serviceSpec(1, 1))
}

func mustAddMappingB(b *testing.B, s *Store, spec MappingSpec) MappingSnapshot {
	b.Helper()
	mapping, err := s.AddMapping(spec)
	if err != nil {
		b.Fatal(err)
	}
	return mapping
}

func mustRemoveMappingB(b *testing.B, s *Store, id MappingID) {
	b.Helper()
	if err := s.RemoveMapping(id); err != nil {
		b.Fatal(err)
	}
}

func mustOpenB(b *testing.B, s *Store, generation TSGeneration) {
	b.Helper()
	if err := s.OpenGeneration(generation); err != nil {
		b.Fatal(err)
	}
}

func mustAddServiceB(b *testing.B, s *Store, spec ServiceSpec) ServiceSnapshot {
	b.Helper()
	service, err := s.AddService(spec)
	if err != nil {
		b.Fatal(err)
	}
	return service
}

func mustCloseServiceB(b *testing.B, s *Store, service ServiceSnapshot) {
	b.Helper()
	if err := s.CloseService(service.Generation, service.Handle); err != nil {
		b.Fatal(err)
	}
}

func mustCloseAndRemoveServiceB(b *testing.B, s *Store, service ServiceSnapshot) {
	b.Helper()
	mustCloseServiceB(b, s, service)
	mustRemoveServiceB(b, s, service)
}

func mustRemoveServiceB(b *testing.B, s *Store, service ServiceSnapshot) {
	b.Helper()
	if err := s.RemoveService(service.Generation, service.Handle); err != nil {
		b.Fatal(err)
	}
}

func mustInsertStreamB(b *testing.B, s *Store, spec StreamSpec) {
	b.Helper()
	if err := s.InsertStream(spec); err != nil {
		b.Fatal(err)
	}
}

func mustCancelStreamB(b *testing.B, s *Store, spec StreamSpec) {
	b.Helper()
	if err := s.CancelStream(spec.Generation, spec.Handle, spec.StreamID); err != nil {
		b.Fatal(err)
	}
}

func mustCancelAndRemoveStreamB(b *testing.B, s *Store, spec StreamSpec) {
	b.Helper()
	mustCancelStreamB(b, s, spec)
	mustRemoveStreamB(b, s, spec)
}

func mustRemoveStreamB(b *testing.B, s *Store, spec StreamSpec) {
	b.Helper()
	if err := s.RemoveStream(spec.Generation, spec.Handle, spec.StreamID); err != nil {
		b.Fatal(err)
	}
}
