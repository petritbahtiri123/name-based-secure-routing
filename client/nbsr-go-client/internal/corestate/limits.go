package corestate

import "math"

type Limits struct {
	MaxGenerations, MaxMappings, MaxServices, MaxStreams int
	MaxMappingBytes, MaxServiceBytes, MaxStreamBytes     uint64
	MaxServiceIdentityBytes, MaxPolicyContextBytes       int
}

func (l Limits) Validate() error {
	if l.MaxGenerations <= 0 || l.MaxMappings <= 0 || l.MaxServices <= 0 || l.MaxStreams <= 0 ||
		l.MaxMappingBytes == 0 || l.MaxServiceBytes == 0 || l.MaxStreamBytes == 0 ||
		l.MaxServiceIdentityBytes <= 0 || l.MaxPolicyContextBytes <= 0 {
		return &StateError{Code: CodeInvalidLimits, Resource: "all limits must be nonzero"}
	}
	return nil
}

const (
	mappingBaseBytes uint64 = 8 + 8 + 8 + 1
	serviceBaseBytes uint64 = 8 + 4 + 16 + 8 + 32 + 32 + 8 + 8 + 8 + 1
	streamBaseBytes  uint64 = 8 + 4 + 8 + 8 + 1 + 1
)

func mappingCost(spec MappingSpec) (uint64, error) {
	return checkedCost(mappingBaseBytes, len(spec.ServiceIdentity), len(spec.PolicyContext))
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
