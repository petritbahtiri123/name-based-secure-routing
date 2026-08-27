package resolution_test

import (
	"bytes"
	"context"
	"crypto/sha256"
	"io"
	"net/netip"
	"strings"
	"sync"
	"testing"

	"nbsr.local/client/nbsr-go-client/internal/adapter/proxy"
	"nbsr.local/client/nbsr-go-client/internal/authority"
	"nbsr.local/client/nbsr-go-client/internal/corestate"
	"nbsr.local/client/nbsr-go-client/internal/resolution"
)

type integrationClock uint64

func (clock integrationClock) NowUnix() uint64 { return uint64(clock) }

type recordedRoutes struct {
	mu     sync.Mutex
	routes []resolution.RouteContext
}

func (opener *recordedRoutes) OpenVerifiedRoute(_ context.Context, mapped *resolution.MappedRoute) (io.ReadWriteCloser, error) {
	route, err := mapped.Context()
	if err != nil {
		return nil, err
	}
	opener.mu.Lock()
	opener.routes = append(opener.routes, route)
	opener.mu.Unlock()
	return &integrationWire{}, nil
}

type integrationWire struct{ bytes.Buffer }

func (*integrationWire) Close() error { return nil }

func TestSharedSyntheticIPCorrelatesSamePortServicesEndToEnd(t *testing.T) {
	store, err := corestate.NewStore(corestate.Limits{
		MaxGenerations: 1, MaxMappings: 4, MaxServices: 1, MaxStreams: 1,
		MaxMappingBytes: 32768, MaxServiceBytes: 1, MaxStreamBytes: 1,
		MaxServiceIdentityBytes: 64, MaxPolicyContextBytes: 64, MaxCanonicalNameBytes: 253,
		MaxRouteIntentBytes: 4096, MaxTargetEdgeBytes: 1024,
	}, integrationClock(100), nil)
	if err != nil {
		t.Fatal(err)
	}
	registry, _ := resolution.NewRegistry(store, 4)
	service, _ := resolution.NewService(registry, netip.MustParseAddr("127.80.0.1"))
	payments := publish(t, service, "payments.example", "payments.service", 1)
	storage := publish(t, service, "storage.example", "storage.service", 2)
	if payments.SyntheticIP != storage.SyntheticIP {
		t.Fatal("services received different synthetic IPs")
	}
	flows, _ := resolution.NewFlowStore(resolution.FlowLimits{MaxEntries: 2, MaxBytes: 32})
	correlator, _ := proxy.NewCorrelator(registry, flows)
	storageTarget, _ := proxy.ParseHTTPConnect(strings.NewReader("CONNECT storage.example:443 HTTP/1.1\r\nHost: ignored.example\r\n\r\n"), 1024)
	paymentsWire := append([]byte{5, 1, 0, 3, 16}, []byte("payments.example")...)
	paymentsWire = append(paymentsWire, 0x01, 0xbb)
	paymentsTarget, _ := proxy.ParseSOCKS5Connect(paymentsWire)
	storageFlow, err := correlator.Bind(storageTarget)
	if err != nil {
		t.Fatal(err)
	}
	paymentsFlow, err := correlator.Bind(paymentsTarget)
	if err != nil {
		t.Fatal(err)
	}
	opener := &recordedRoutes{}
	router, _ := resolution.NewRouter(store, flows, opener)
	first, err := router.OpenFlow(context.Background(), storageFlow.LocalFlowID)
	if err != nil {
		t.Fatal(err)
	}
	second, err := router.OpenFlow(context.Background(), paymentsFlow.LocalFlowID)
	if err != nil {
		t.Fatal(err)
	}
	if opener.routes[0].ServiceIdentity != "storage.service" || opener.routes[1].ServiceIdentity != "payments.service" ||
		opener.routes[0].ServiceDigest == opener.routes[1].ServiceDigest {
		t.Fatalf("routes crossed: %+v", opener.routes)
	}
	_ = first.Close()
	_ = second.Close()
	if err := store.RemoveMapping(storage.MappingID); err != nil {
		t.Fatal(err)
	}
	if err := store.RemoveMapping(payments.MappingID); err != nil {
		t.Fatal(err)
	}
}

func publish(t *testing.T, service *resolution.Service, name, identity string, seed byte) resolution.ResolutionAnswer {
	t.Helper()
	canonical := []byte("route-intent-" + name)
	intent := authority.RouteIntent{
		Canonical: canonical, Digest: authority.RouteIntentDigest(sha256.Sum256(canonical)), ServiceIdentity: identity,
		SourceOperator: "source", SourceEdge: "source-edge", TargetOperator: "target", TargetEdges: []string{"target-edge"},
		Transport: "tcp", Port: 443, RecordSequence: uint64(seed), PolicyHash: authority.PolicyDigest{seed},
		RouteID: [16]byte{seed}, LeaseID: [16]byte{seed + 1}, ExpiresAt: 180,
	}
	result, err := resolution.NewResult(resolution.ResultInput{PresentationName: name, ServiceIdentity: identity, Intent: intent, RecordExpiresAt: 180}, 100)
	if err != nil {
		t.Fatal(err)
	}
	answer, err := service.Publish(result, "policy")
	if err != nil {
		t.Fatal(err)
	}
	return answer
}
