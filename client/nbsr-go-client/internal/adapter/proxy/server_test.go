package proxy

import (
	"errors"
	"testing"

	"nbsr.local/client/nbsr-go-client/internal/corestate"
	"nbsr.local/client/nbsr-go-client/internal/resolution"
)

type staticResolver map[resolution.CanonicalName]corestate.MappingID

func (resolver staticResolver) MappingForTarget(name resolution.CanonicalName, port uint16) (corestate.MappingID, error) {
	if port != 443 {
		return 0, ErrUnresolvedTarget
	}
	id := resolver[name]
	if id == 0 {
		return 0, ErrUnresolvedTarget
	}
	return id, nil
}

func TestCorrelatorSeparatesSamePortServicesOnSharedIP(t *testing.T) {
	flows, _ := resolution.NewFlowStore(resolution.FlowLimits{MaxEntries: 2, MaxBytes: 32})
	correlator, err := NewCorrelator(staticResolver{"payments.example": 11, "storage.example": 12}, flows)
	if err != nil {
		t.Fatal(err)
	}
	payments, err := correlator.Bind(Target{Name: "payments.example", Port: 443})
	if err != nil {
		t.Fatal(err)
	}
	storage, err := correlator.Bind(Target{Name: "storage.example", Port: 443})
	if err != nil {
		t.Fatal(err)
	}
	if payments.MappingID != 11 || storage.MappingID != 12 || payments.LocalFlowID == storage.LocalFlowID {
		t.Fatalf("contexts = %+v %+v", payments, storage)
	}
	if got, _ := flows.Consume(storage.LocalFlowID); got != 12 {
		t.Fatalf("storage mapping = %d, want 12", got)
	}
	if got, _ := flows.Consume(payments.LocalFlowID); got != 11 {
		t.Fatalf("payments mapping = %d, want 11", got)
	}
}

func TestCorrelatorFailsClosedForUnknownAndCapacity(t *testing.T) {
	flows, _ := resolution.NewFlowStore(resolution.FlowLimits{MaxEntries: 1, MaxBytes: 16})
	correlator, _ := NewCorrelator(staticResolver{"api.example": 1}, flows)
	if _, err := correlator.Bind(Target{Name: "missing.example", Port: 443}); !errors.Is(err, ErrUnresolvedTarget) {
		t.Fatalf("unknown error = %v", err)
	}
	if _, err := correlator.Bind(Target{Name: "api.example", Port: 443}); err != nil {
		t.Fatal(err)
	}
	if _, err := correlator.Bind(Target{Name: "api.example", Port: 443}); !errors.Is(err, resolution.ErrFlowCapacity) {
		t.Fatalf("capacity error = %v", err)
	}
}
