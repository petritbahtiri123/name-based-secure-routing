package resolution

import (
	"context"
	"errors"
	"testing"

	"nbsr.local/client/nbsr-go-client/internal/corestate"
)

func TestMappedRouteCapabilityCannotBeSynthesizedFromRouteContext(t *testing.T) {
	for _, candidate := range []*MappedRoute{nil, &MappedRoute{}} {
		if _, err := candidate.Context(); !errors.Is(err, ErrRouteBinding) {
			t.Fatalf("synthetic capability error = %v", err)
		}
	}
}

func TestRouterCapabilityRequiresLiveSingleUseFlowAndReleasesOnce(t *testing.T) {
	store, mapping := routerStore(t)
	flows, _ := NewFlowStore(FlowLimits{MaxEntries: 1, MaxBytes: 16})
	_ = flows.Bind(FlowContext{MappingID: mapping.ID, LocalFlowID: 1})
	opener := &routeOpener{}
	router, _ := NewRouter(store, flows, opener)
	stream, err := router.OpenFlow(context.Background(), 1)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := router.OpenFlow(context.Background(), 1); !errors.Is(err, ErrUnknownFlow) {
		t.Fatalf("reused flow error = %v", err)
	}
	if err := stream.Close(); err != nil {
		t.Fatal(err)
	}
	if _, err := opener.last.Context(); !errors.Is(err, ErrRouteBinding) {
		t.Fatalf("released capability remained usable: %v", err)
	}
	if err := stream.Close(); err != nil {
		t.Fatal(err)
	}
	got, err := store.LookupMapping(mapping.ID)
	if err != nil || got.ActiveReferences != 0 {
		t.Fatalf("mapping after double close = (%+v, %v)", got, err)
	}
	if err := store.RemoveMapping(corestate.MappingID(mapping.ID)); err != nil {
		t.Fatal(err)
	}
}
