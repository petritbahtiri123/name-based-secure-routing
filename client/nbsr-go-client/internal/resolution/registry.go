package resolution

import (
	"errors"
	"net/netip"
	"sync"

	"nbsr.local/client/nbsr-go-client/internal/corestate"
)

var ErrUnresolvedMapping = errors.New("unresolved mapping")

type mappingRegistry interface {
	AddMapping(corestate.MappingSpec) (corestate.MappingSnapshot, error)
	LookupMapping(corestate.MappingID) (corestate.MappingSnapshot, error)
}

type Registry struct {
	mu         sync.RWMutex
	mappings   mappingRegistry
	maxEntries int
	byName     map[CanonicalName]corestate.MappingID
}

func NewRegistry(mappings mappingRegistry, maxEntries int) (*Registry, error) {
	if mappings == nil || maxEntries <= 0 {
		return nil, ErrUnresolvedMapping
	}
	return &Registry{mappings: mappings, maxEntries: maxEntries, byName: make(map[CanonicalName]corestate.MappingID)}, nil
}

func (registry *Registry) Publish(result Result, policy corestate.PolicyContext) (corestate.MappingSnapshot, error) {
	if result.CanonicalName == "" || result.ServiceDigest == (corestate.ServiceDigest{}) {
		return corestate.MappingSnapshot{}, ErrInvalidResolution
	}
	registry.mu.Lock()
	defer registry.mu.Unlock()
	if _, exists := registry.byName[result.CanonicalName]; !exists && len(registry.byName) >= registry.maxEntries {
		return corestate.MappingSnapshot{}, ErrUnresolvedMapping
	}
	mapping, err := registry.mappings.AddMapping(result.MappingSpec(policy))
	if err != nil {
		return corestate.MappingSnapshot{}, err
	}
	registry.byName[result.CanonicalName] = mapping.ID
	return mapping, nil
}

func (registry *Registry) MappingForTarget(name CanonicalName, port uint16) (corestate.MappingID, error) {
	registry.mu.RLock()
	id := registry.byName[name]
	registry.mu.RUnlock()
	if id == 0 {
		return 0, ErrUnresolvedMapping
	}
	mapping, err := registry.mappings.LookupMapping(id)
	if err != nil || mapping.CanonicalName != name.String() || mapping.RouteIntent.Port != port {
		return 0, ErrUnresolvedMapping
	}
	return id, nil
}

type ResolutionAnswer struct {
	SyntheticIP netip.Addr
	MappingID   corestate.MappingID
}

type Service struct {
	registry *Registry
	sharedIP netip.Addr
}

func NewService(registry *Registry, sharedIP netip.Addr) (*Service, error) {
	if registry == nil || !validSharedSyntheticIP(sharedIP) {
		return nil, ErrInvalidResolution
	}
	return &Service{registry: registry, sharedIP: sharedIP}, nil
}

func (service *Service) Publish(result Result, policy corestate.PolicyContext) (ResolutionAnswer, error) {
	mapping, err := service.registry.Publish(result, policy)
	if err != nil {
		return ResolutionAnswer{}, err
	}
	return ResolutionAnswer{SyntheticIP: service.sharedIP, MappingID: mapping.ID}, nil
}

func validSharedSyntheticIP(address netip.Addr) bool {
	if !address.IsValid() {
		return false
	}
	if address.Is4() {
		return netip.MustParsePrefix("127.0.0.0/8").Contains(address)
	}
	return netip.MustParsePrefix("fd00:6e62:7372::/48").Contains(address)
}
