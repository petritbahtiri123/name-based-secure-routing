package resolution

import (
	"errors"
	"sync"

	"nbsr.local/client/nbsr-go-client/internal/corestate"
)

var (
	ErrUnknownFlow  = errors.New("unknown flow")
	ErrFlowConflict = errors.New("flow conflict")
	ErrFlowCapacity = errors.New("flow capacity exceeded")
	ErrFlowClosed   = errors.New("flow store closed")
)

const flowContextBytes uint64 = 16

type FlowContext struct {
	MappingID   corestate.MappingID
	LocalFlowID corestate.LocalFlowID
}

type FlowLimits struct {
	MaxEntries int
	MaxBytes   uint64
}

type FlowStore struct {
	mu     sync.Mutex
	limits FlowLimits
	flows  map[corestate.LocalFlowID]corestate.MappingID
	closed bool
}

func NewFlowStore(limits FlowLimits) (*FlowStore, error) {
	if limits.MaxEntries <= 0 || limits.MaxBytes < flowContextBytes {
		return nil, ErrFlowCapacity
	}
	return &FlowStore{limits: limits, flows: make(map[corestate.LocalFlowID]corestate.MappingID)}, nil
}

func (store *FlowStore) Bind(context FlowContext) error {
	if context.MappingID == 0 || context.LocalFlowID == 0 {
		return ErrFlowConflict
	}
	store.mu.Lock()
	defer store.mu.Unlock()
	if store.closed {
		return ErrFlowClosed
	}
	if _, exists := store.flows[context.LocalFlowID]; exists {
		return ErrFlowConflict
	}
	if len(store.flows) >= store.limits.MaxEntries || uint64(len(store.flows)+1)*flowContextBytes > store.limits.MaxBytes {
		return ErrFlowCapacity
	}
	store.flows[context.LocalFlowID] = context.MappingID
	return nil
}

func (store *FlowStore) Consume(id corestate.LocalFlowID) (corestate.MappingID, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	if store.closed {
		return 0, ErrFlowClosed
	}
	mapping, exists := store.flows[id]
	if !exists {
		return 0, ErrUnknownFlow
	}
	delete(store.flows, id)
	return mapping, nil
}

func (store *FlowStore) Remove(id corestate.LocalFlowID) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	if _, exists := store.flows[id]; !exists {
		return ErrUnknownFlow
	}
	delete(store.flows, id)
	return nil
}

func (store *FlowStore) Close() error {
	store.mu.Lock()
	defer store.mu.Unlock()
	store.closed = true
	clear(store.flows)
	return nil
}
