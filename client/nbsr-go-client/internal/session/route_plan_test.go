package session

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"io"
	"testing"

	"nbsr.local/client/nbsr-go-client/internal/authority"
	"nbsr.local/client/nbsr-go-client/internal/corestate"
	"nbsr.local/client/nbsr-go-client/internal/identity"
	"nbsr.local/client/nbsr-go-client/internal/resolution"
)

type plannedRouteOpener struct {
	manager *Manager
	spec    TransportSessionSpec
	public  []byte
	plan    *RoutePlan
}

func (opener *plannedRouteOpener) OpenVerifiedRoute(_ context.Context, route *resolution.MappedRoute) (io.ReadWriteCloser, error) {
	plan, err := opener.manager.PlanRoute(route, opener.spec, opener.public)
	opener.plan = plan
	return &routePlanWire{}, err
}

type routePlanWire struct{ bytes.Buffer }

func (*routePlanWire) Close() error { return nil }

func TestRoutePlanUsesOneSessionOwnedProofForAuthorityAndTransport(t *testing.T) {
	fixture := newFixture(t)
	public := ed25519.NewKeyFromSeed(make([]byte, ed25519.SeedSize)).Public().(ed25519.PublicKey)
	thumbprint := sha256.Sum256(public)
	proof := identity.TSProofKey{TSGeneration: 1, Key: identity.KeyRef{ID: bytes32(11), Purpose: identity.PurposeTSProof, Generation: 1, Thumbprint: thumbprint}}
	device, _ := fixture.registry.Device()
	local, _ := fixture.registry.LocalStateIntegrity()
	registry, err := identity.NewMemoryRegistry(device, nil, []identity.TSProofKey{proof}, local)
	if err != nil {
		t.Fatal(err)
	}
	fixture.manager.registry = registry
	spec := fixture.sessionSpec(1)
	spec.Proof = proof

	store, mapping := routePlanMapping(t, fixture.clock.now)
	flows, _ := resolution.NewFlowStore(resolution.FlowLimits{MaxEntries: 1, MaxBytes: 16})
	_ = flows.Bind(resolution.FlowContext{MappingID: mapping.ID, LocalFlowID: 1})
	opener := &plannedRouteOpener{manager: fixture.manager, spec: spec, public: public}
	router, _ := resolution.NewRouter(store, flows, opener)
	stream, err := router.OpenFlow(context.Background(), 1)
	if err != nil {
		t.Fatal(err)
	}
	template := authority.AcquireRequest{Key: authority.AuthorityKey{Profile: "nbsr", DeviceID: device.ID, DeviceGeneration: 1, PolicyGeneration: 1, AuthorityGeneration: 7}, RequestID: authority.RequestID{1}, DeadlineUnix: fixture.clock.now + 30}
	request, err := opener.plan.BuildAcquireRequest(template)
	if err != nil {
		t.Fatal(err)
	}
	if request.Key.TSGeneration != 1 || request.Key.ProofThumbprint != thumbprint || request.Key.ServiceDigest != authority.ServiceDigest(mapping.ServiceDigest) {
		t.Fatalf("authority request proof/route binding = %+v", request.Key)
	}
	// Mutating the caller's original spec cannot substitute proof B into the sealed plan.
	spec.Proof.Key.ID = bytes32(99)
	if _, err := opener.plan.CreateTransportSession(context.Background()); err != nil {
		t.Fatal(err)
	}
	fixture.connector.mu.Lock()
	attempt := fixture.connector.attempts[len(fixture.connector.attempts)-1]
	fixture.connector.mu.Unlock()
	if attempt.ProofKey != proof.Key {
		t.Fatalf("transport proof = %+v, want plan proof %+v", attempt.ProofKey, proof.Key)
	}
	if err := stream.Close(); err != nil {
		t.Fatal(err)
	}
	if _, err := opener.plan.CreateTransportSession(context.Background()); err != resolution.ErrRouteBinding {
		t.Fatalf("released route plan error = %v, want ErrRouteBinding", err)
	}
}

func routePlanMapping(t *testing.T, now uint64) (*corestate.Store, corestate.MappingSnapshot) {
	t.Helper()
	store, err := corestate.NewStore(corestate.Limits{MaxGenerations: 1, MaxMappings: 1, MaxServices: 1, MaxStreams: 1, MaxMappingBytes: 8192, MaxServiceBytes: 1, MaxStreamBytes: 1, MaxServiceIdentityBytes: 64, MaxPolicyContextBytes: 64, MaxCanonicalNameBytes: 253, MaxRouteIntentBytes: 4096, MaxTargetEdgeBytes: 1024}, &testClock{now}, nil)
	if err != nil {
		t.Fatal(err)
	}
	canonical := []byte("session route intent")
	intent := authority.RouteIntent{Canonical: canonical, Digest: authority.RouteIntentDigest(sha256.Sum256(canonical)), ServiceIdentity: "service.api", SourceOperator: "source", SourceEdge: "source-edge", TargetOperator: "target", TargetEdges: []string{"target-edge"}, Transport: "tcp", Port: 443, RecordSequence: 1, PolicyHash: authority.PolicyDigest{1}, RouteID: [16]byte{1}, LeaseID: [16]byte{2}, ExpiresAt: now + 300}
	result, err := resolution.NewResult(resolution.ResultInput{PresentationName: "api.example", ServiceIdentity: intent.ServiceIdentity, Intent: intent, RecordExpiresAt: now + 300}, now)
	if err != nil {
		t.Fatal(err)
	}
	mapping, err := store.AddMapping(result.MappingSpec("policy"))
	if err != nil {
		t.Fatal(err)
	}
	return store, mapping
}
