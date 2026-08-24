package resolution

import (
	"errors"
	"net/netip"
	"testing"

	"nbsr.local/client/nbsr-go-client/internal/corestate"
)

func TestServiceReturnsOneSharedSyntheticIPAndNewMappingOnReplacement(t *testing.T) {
	store := emptyRegistryStore(t, 3)
	registry, err := NewRegistry(store, 2)
	if err != nil {
		t.Fatal(err)
	}
	service, err := NewService(registry, netip.MustParseAddr("127.80.0.1"))
	if err != nil {
		t.Fatal(err)
	}
	firstResult, _ := NewResult(ResultInput{PresentationName: "api.example", ServiceIdentity: "service.api", Intent: validIntent(), RecordExpiresAt: 180}, 100)
	first, err := service.Publish(firstResult, "policy")
	if err != nil {
		t.Fatal(err)
	}
	changedIntent := validIntent()
	changedIntent.RecordSequence = 2
	changedIntent.Canonical = []byte("changed route intent")
	changedIntent.Digest = digestIntent(changedIntent.Canonical)
	secondResult, _ := NewResult(ResultInput{PresentationName: "api.example", ServiceIdentity: "service.api", Intent: changedIntent, RecordExpiresAt: 180}, 100)
	second, err := service.Publish(secondResult, "policy")
	if err != nil {
		t.Fatal(err)
	}
	if first.SyntheticIP != second.SyntheticIP || first.SyntheticIP.String() != "127.80.0.1" || second.MappingID <= first.MappingID {
		t.Fatalf("answers = %+v %+v", first, second)
	}
	if got, err := registry.MappingForTarget("api.example", 443); err != nil || got != second.MappingID {
		t.Fatalf("current mapping = (%d, %v), want %d", got, err, second.MappingID)
	}
}

func TestRegistryRestartAndWrongPortFailClosed(t *testing.T) {
	store := emptyRegistryStore(t, 2)
	registry, _ := NewRegistry(store, 1)
	result, _ := NewResult(ResultInput{PresentationName: "api.example", ServiceIdentity: "service.api", Intent: validIntent(), RecordExpiresAt: 180}, 100)
	_, _ = registry.Publish(result, "policy")
	if _, err := registry.MappingForTarget("api.example", 80); !errors.Is(err, ErrUnresolvedMapping) {
		t.Fatalf("wrong port error = %v", err)
	}
	fresh, _ := NewRegistry(store, 1)
	if _, err := fresh.MappingForTarget("api.example", 443); !errors.Is(err, ErrUnresolvedMapping) {
		t.Fatalf("fresh registry restored mapping: %v", err)
	}
}

func digestIntent(value []byte) [32]byte { return [32]byte(corestateDigest(value)) }

func corestateDigest(value []byte) corestate.ServiceDigest {
	return DigestCanonicalName(CanonicalName(value))
}

func emptyRegistryStore(t *testing.T, mappings int) *corestate.Store {
	t.Helper()
	store, err := corestate.NewStore(corestate.Limits{
		MaxGenerations: 1, MaxMappings: mappings, MaxServices: 1, MaxStreams: 1,
		MaxMappingBytes: 16384, MaxServiceBytes: 1, MaxStreamBytes: 1,
		MaxServiceIdentityBytes: 64, MaxPolicyContextBytes: 64, MaxCanonicalNameBytes: 253,
		MaxRouteIntentBytes: 4096, MaxTargetEdgeBytes: 1024,
	}, routeClock(100), nil)
	if err != nil {
		t.Fatal(err)
	}
	return store
}
