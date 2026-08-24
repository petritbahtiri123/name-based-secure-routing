package proxy

import (
	"errors"
	"math"
	"sync"

	"nbsr.local/client/nbsr-go-client/internal/corestate"
	"nbsr.local/client/nbsr-go-client/internal/resolution"
)

var (
	ErrUnresolvedTarget = errors.New("unresolved proxy target")
	ErrFlowIDExhausted  = errors.New("local flow ID exhausted")
)

type MappingResolver interface {
	MappingForTarget(resolution.CanonicalName, uint16) (corestate.MappingID, error)
}

type Correlator struct {
	mu       sync.Mutex
	resolver MappingResolver
	flows    *resolution.FlowStore
	next     corestate.LocalFlowID
}

func NewCorrelator(resolver MappingResolver, flows *resolution.FlowStore) (*Correlator, error) {
	if resolver == nil || flows == nil {
		return nil, ErrUnresolvedTarget
	}
	return &Correlator{resolver: resolver, flows: flows, next: 1}, nil
}

func (correlator *Correlator) Bind(target Target) (resolution.FlowContext, error) {
	if target.Name == "" || target.Port == 0 {
		return resolution.FlowContext{}, ErrUnresolvedTarget
	}
	mapping, err := correlator.resolver.MappingForTarget(target.Name, target.Port)
	if err != nil || mapping == 0 {
		return resolution.FlowContext{}, ErrUnresolvedTarget
	}
	correlator.mu.Lock()
	defer correlator.mu.Unlock()
	if correlator.next == 0 {
		return resolution.FlowContext{}, ErrFlowIDExhausted
	}
	context := resolution.FlowContext{MappingID: mapping, LocalFlowID: correlator.next}
	if err := correlator.flows.Bind(context); err != nil {
		return resolution.FlowContext{}, err
	}
	if correlator.next == corestate.LocalFlowID(math.MaxUint64) {
		correlator.next = 0
	} else {
		correlator.next++
	}
	return context, nil
}
