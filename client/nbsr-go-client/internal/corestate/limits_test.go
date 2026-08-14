package corestate

import (
	"errors"
	"math"
	"testing"
	"unsafe"
)

type fakeClock struct {
	now uint64
}

func (c fakeClock) NowUnix() uint64 { return c.now }

func validLimits() Limits {
	return Limits{1, 1, 1, 1, 1, 1, 1, 1, 1}
}

func TestServiceHandleIsUint32AndZeroInvalid(t *testing.T) {
	if unsafe.Sizeof(ServiceHandle(0)) != 4 {
		t.Fatal("wrong width")
	}
	if InvalidServiceHandle != 0 {
		t.Fatal("zero not reserved")
	}
}

func TestLimitsRequireEveryBound(t *testing.T) {
	if err := validLimits().Validate(); err != nil {
		t.Fatal(err)
	}

	tests := []struct {
		name   string
		mutate func(*Limits)
	}{
		{"generations", func(l *Limits) { l.MaxGenerations = 0 }},
		{"mappings", func(l *Limits) { l.MaxMappings = 0 }},
		{"services", func(l *Limits) { l.MaxServices = 0 }},
		{"streams", func(l *Limits) { l.MaxStreams = 0 }},
		{"mapping bytes", func(l *Limits) { l.MaxMappingBytes = 0 }},
		{"service bytes", func(l *Limits) { l.MaxServiceBytes = 0 }},
		{"stream bytes", func(l *Limits) { l.MaxStreamBytes = 0 }},
		{"service identity bytes", func(l *Limits) { l.MaxServiceIdentityBytes = 0 }},
		{"policy context bytes", func(l *Limits) { l.MaxPolicyContextBytes = 0 }},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			limits := validLimits()
			tt.mutate(&limits)
			if !errors.Is(limits.Validate(), ErrInvalidLimits) {
				t.Fatal("zero accepted")
			}
		})
	}
}

func TestStateErrorMatchesEverySentinel(t *testing.T) {
	tests := []struct {
		code     ErrorCode
		sentinel error
	}{
		{CodeInvalidHandle, ErrInvalidHandle},
		{CodeUnknownMapping, ErrUnknownMapping},
		{CodeExpiredMapping, ErrExpiredMapping},
		{CodeMappingConflict, ErrMappingConflict},
		{CodeUnknownService, ErrUnknownService},
		{CodeDuplicateService, ErrDuplicateService},
		{CodeDuplicateStream, ErrDuplicateStream},
		{CodeCapacityExceeded, ErrCapacityExceeded},
		{CodeByteCapacityExceeded, ErrByteCapacityExceeded},
		{CodeGenerationClosed, ErrGenerationClosed},
		{CodeServiceClosed, ErrServiceClosed},
		{CodeHandleExhausted, ErrHandleExhausted},
		{CodeMappingIDExhausted, ErrMappingIDExhausted},
		{CodeInvalidTransition, ErrInvalidTransition},
		{CodeInvalidLimits, ErrInvalidLimits},
		{CodeAccountingOverflow, ErrAccountingOverflow},
	}

	for _, tt := range tests {
		err := &StateError{Code: tt.code, Resource: "test resource"}
		if !errors.Is(err, tt.sentinel) {
			t.Fatalf("code %d did not match sentinel", tt.code)
		}
		if err.Error() == "" {
			t.Fatalf("code %d returned an empty error", tt.code)
		}
	}
}

func TestStateErrorDoesNotPanicForTypedNilTarget(t *testing.T) {
	actual := &StateError{Code: CodeInvalidHandle}
	var target *StateError

	if errors.Is(actual, target) {
		t.Fatal("StateError matched a typed-nil target")
	}
}

func TestLogicalCostIsDeterministic(t *testing.T) {
	mapping, err := mappingCost(MappingSpec{
		ServiceIdentity: "service",
		PolicyContext:   PolicyContext("policy"),
	})
	if err != nil {
		t.Fatal(err)
	}
	if mapping != 38 {
		t.Fatalf("mapping cost = %d, want 38", mapping)
	}

	service, err := serviceCost(ServiceSpec{ServiceIdentity: "service"})
	if err != nil {
		t.Fatal(err)
	}
	if service != 132 {
		t.Fatalf("service cost = %d, want 132", service)
	}

	if stream := streamCost(StreamSpec{}); stream != 30 {
		t.Fatalf("stream cost = %d, want 30", stream)
	}
}

func TestLogicalCostRejectsCheckedAdditionOverflow(t *testing.T) {
	if _, err := checkedCost(math.MaxUint64, 1); !errors.Is(err, ErrAccountingOverflow) {
		t.Fatalf("overflow error = %v, want ErrAccountingOverflow", err)
	}
}

func TestNewStoreRejectsNilClock(t *testing.T) {
	if _, err := NewStore(validLimits(), nil, nil); !errors.Is(err, ErrInvalidLimits) {
		t.Fatalf("nil clock error = %v, want ErrInvalidLimits", err)
	}
}

func TestNewStoreUsesInjectedClockAndAcceptsNilObserver(t *testing.T) {
	clock := fakeClock{now: 42}
	store, err := NewStore(validLimits(), clock, nil)
	if err != nil {
		t.Fatal(err)
	}
	if got := store.clock.NowUnix(); got != 42 {
		t.Fatalf("clock time = %d, want 42", got)
	}
	if store.observer == nil {
		t.Fatal("nil observer was not replaced")
	}
}

var (
	_ MappingRegistry = (*Store)(nil)
	_ ServiceRegistry = (*Store)(nil)
	_ StreamRegistry  = (*Store)(nil)
)
