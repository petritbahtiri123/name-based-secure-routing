package corestate

import "math"

type Limits struct {
	MaxGenerations, MaxMappings, MaxServices, MaxStreams           int
	MaxMappingBytes, MaxServiceBytes, MaxStreamBytes               uint64
	MaxServiceIdentityBytes, MaxPolicyContextBytes                 int
	MaxCanonicalNameBytes, MaxRouteIntentBytes, MaxTargetEdgeBytes int
}

func (l Limits) Validate() error {
	if l.MaxGenerations <= 0 || l.MaxMappings <= 0 || l.MaxServices <= 0 || l.MaxStreams <= 0 ||
		l.MaxMappingBytes == 0 || l.MaxServiceBytes == 0 || l.MaxStreamBytes == 0 ||
		l.MaxServiceIdentityBytes <= 0 || l.MaxPolicyContextBytes <= 0 || l.MaxCanonicalNameBytes <= 0 ||
		l.MaxRouteIntentBytes <= 0 || l.MaxTargetEdgeBytes <= 0 {
		return &StateError{Code: CodeInvalidLimits, Resource: "all limits must be nonzero"}
	}
	return nil
}

const (
	mappingBaseBytes uint64 = 8 + 8 + 8 + 32 + 32 + 2 + 8 + 32 + 16 + 16 + 8 + 1
	serviceBaseBytes uint64 = 8 + 4 + 16 + 8 + 32 + 32 + 8 + 8 + 8 + 1
	streamBaseBytes  uint64 = 8 + 4 + 8 + 8 + 1 + 1
)

func mappingCost(spec MappingSpec) (uint64, error) {
	lengths := []int{len(spec.CanonicalName), len(spec.ServiceIdentity), len(spec.PolicyContext), len(spec.RouteIntent.Canonical),
		len(spec.RouteIntent.SourceOperator), len(spec.RouteIntent.SourceEdge), len(spec.RouteIntent.TargetOperator), len(spec.RouteIntent.Transport)}
	for _, edge := range spec.RouteIntent.TargetEdges {
		lengths = append(lengths, len(edge))
	}
	return checkedCost(mappingBaseBytes, lengths...)
}

func serviceCost(spec ServiceSpec) (uint64, error) {
	return checkedCost(serviceBaseBytes, len(spec.ServiceIdentity))
}

func streamCost(StreamSpec) uint64 { return streamBaseBytes }

func checkedCost(base uint64, variableLengths ...int) (uint64, error) {
	total := base
	for _, length := range variableLengths {
		if length < 0 || uint64(length) > math.MaxUint64-total {
			return 0, &StateError{Code: CodeAccountingOverflow, Resource: "logical byte cost"}
		}
		total += uint64(length)
	}
	return total, nil
}
