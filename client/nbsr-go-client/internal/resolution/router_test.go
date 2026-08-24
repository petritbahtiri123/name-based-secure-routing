package resolution

import (
	"bytes"
	"context"
	"errors"
	"io"
	"testing"

	"nbsr.local/client/nbsr-go-client/internal/authority"
	"nbsr.local/client/nbsr-go-client/internal/corestate"
)

type routeClock uint64

func (clock routeClock) NowUnix() uint64 { return uint64(clock) }

type routeOpener struct {
	got RouteContext
	err error
}

func (opener *routeOpener) OpenVerifiedRoute(_ context.Context, route RouteContext) (io.ReadWriteCloser, error) {
	opener.got = route
	if opener.err != nil {
		return nil, opener.err
	}
	return &memoryRoute{}, nil
}

type memoryRoute struct{ bytes.Buffer }

func (*memoryRoute) Close() error { return nil }

func routerStore(t *testing.T) (*corestate.Store, corestate.MappingSnapshot) {
	t.Helper()
	limits := corestate.Limits{
		MaxGenerations: 1, MaxMappings: 2, MaxServices: 1, MaxStreams: 1,
		MaxMappingBytes: 8192, MaxServiceBytes: 1, MaxStreamBytes: 1,
		MaxServiceIdentityBytes: 64, MaxPolicyContextBytes: 64, MaxCanonicalNameBytes: 253,
		MaxRouteIntentBytes: 4096, MaxTargetEdgeBytes: 1024,
	}
	store, err := corestate.NewStore(limits, routeClock(100), nil)
	if err != nil {
		t.Fatal(err)
	}
	result, err := NewResult(ResultInput{PresentationName: "api.example", ServiceIdentity: "service.api", Intent: validIntent(), RecordExpiresAt: 180}, 100)
	if err != nil {
		t.Fatal(err)
	}
	mapping, err := store.AddMapping(result.MappingSpec("policy"))
	if err != nil {
		t.Fatal(err)
	}
	return store, mapping
}

func TestRouterRestoresMappingOwnedRouteContext(t *testing.T) {
	store, mapping := routerStore(t)
	flows, _ := NewFlowStore(FlowLimits{MaxEntries: 1, MaxBytes: 16})
	_ = flows.Bind(FlowContext{MappingID: mapping.ID, LocalFlowID: 1})
	opener := &routeOpener{}
	router, err := NewRouter(store, flows, opener)
	if err != nil {
		t.Fatal(err)
	}
	stream, err := router.OpenFlow(context.Background(), 1)
	if err != nil {
		t.Fatal(err)
	}
	if opener.got.MappingID != mapping.ID || opener.got.ServiceDigest != mapping.ServiceDigest || opener.got.ServiceIdentity != mapping.ServiceIdentity ||
		opener.got.Intent.Digest != authority.RouteIntentDigest(mapping.RouteIntent.Digest) || opener.got.Intent.Port != 443 {
		t.Fatalf("route context = %+v", opener.got)
	}
	if err := stream.Close(); err != nil {
		t.Fatal(err)
	}
	got, err := store.LookupMapping(mapping.ID)
	if err != nil || got.ActiveReferences != 0 {
		t.Fatalf("mapping after close = (%+v, %v)", got, err)
	}
}

func TestRouterFailsClosedAndReleasesMapping(t *testing.T) {
	store, mapping := routerStore(t)
	flows, _ := NewFlowStore(FlowLimits{MaxEntries: 1, MaxBytes: 16})
	_ = flows.Bind(FlowContext{MappingID: mapping.ID, LocalFlowID: 1})
	opener := &routeOpener{err: errors.New("authority rejected")}
	router, _ := NewRouter(store, flows, opener)
	if _, err := router.OpenFlow(context.Background(), 1); err == nil {
		t.Fatal("rejected route opened")
	}
	got, _ := store.LookupMapping(mapping.ID)
	if got.ActiveReferences != 0 {
		t.Fatalf("mapping references = %d, want 0", got.ActiveReferences)
	}
	if _, err := router.OpenFlow(context.Background(), 1); !errors.Is(err, ErrUnknownFlow) {
		t.Fatalf("reused flow error = %v", err)
	}
}

func TestBuildAcquireRequestPinsEveryMappingOwnedAuthorityField(t *testing.T) {
	_, mapping := routerStore(t)
	route, err := routeContext(mapping)
	if err != nil {
		t.Fatal(err)
	}
	template := authority.AcquireRequest{
		Key: authority.AuthorityKey{Profile: "profile", DeviceID: [32]byte{1}, DeviceGeneration: 1, TSGeneration: 1,
			ProofThumbprint: authority.ProofKeyThumbprint{1}, PolicyGeneration: 1, AuthorityGeneration: 1},
		RequestID: authority.RequestID{1}, DeadlineUnix: 150,
	}
	request, err := BuildAcquireRequest(route, template)
	if err != nil {
		t.Fatal(err)
	}
	if request.Key.ServiceDigest != authority.ServiceDigest(mapping.ServiceDigest) || request.Key.IntentDigest != authority.RouteIntentDigest(mapping.RouteIntent.Digest) ||
		request.Key.SourceOperator != mapping.RouteIntent.SourceOperator || request.Key.TargetOperator != mapping.RouteIntent.TargetOperator ||
		request.Key.Transport != mapping.RouteIntent.Transport || request.Key.Port != mapping.RouteIntent.Port || request.Key.PolicyHash != authority.PolicyDigest(mapping.RouteIntent.PolicyHash) ||
		request.Intent.ServiceIdentity != mapping.ServiceIdentity {
		t.Fatalf("acquire request not mapping-owned: %+v", request)
	}
}
