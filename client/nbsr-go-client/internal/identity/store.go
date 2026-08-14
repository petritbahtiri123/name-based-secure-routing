package identity

import "time"

// MemoryRegistry is an immutable test registry. Callers receive value copies
// and it starts no goroutines.
type MemoryRegistry struct {
	device    DeviceIdentity
	workloads map[[32]byte]WorkloadPolicyContext
	tsProofs  map[uint64]TSProofKey
	local     LocalStateIntegrityKey
}

func NewMemoryRegistry(device DeviceIdentity, workloads []WorkloadPolicyContext, tsProofs []TSProofKey, local LocalStateIntegrityKey) (*MemoryRegistry, error) {
	now := uint64(time.Now().Unix())
	if err := validateDevice(device, now); err != nil {
		return nil, err
	}
	if err := validateKeyRef(local.Key, PurposeLocalStateIntegrity); err != nil {
		return nil, err
	}
	workloadSubjects := make(map[[32]byte]struct{}, len(workloads))
	for _, workload := range workloads {
		if err := validateWorkload(workload, now); err != nil {
			return nil, err
		}
		if _, duplicate := workloadSubjects[workload.SubjectDigest]; duplicate {
			return nil, &IdentityError{Code: CodeInvalidIdentity, Resource: "duplicate workload subject"}
		}
		workloadSubjects[workload.SubjectDigest] = struct{}{}
	}
	proofGenerations := make(map[uint64]struct{}, len(tsProofs))
	for _, proof := range tsProofs {
		if proof.TSGeneration == 0 {
			return nil, &IdentityError{Code: CodeInvalidGeneration, Resource: "TS proof generation"}
		}
		if err := validateKeyRef(proof.Key, PurposeTSProof); err != nil {
			return nil, err
		}
		if proof.TSGeneration != proof.Key.Generation {
			return nil, &IdentityError{Code: CodeInvalidGeneration, Resource: "TS proof generation"}
		}
		if _, duplicate := proofGenerations[proof.TSGeneration]; duplicate {
			return nil, &IdentityError{Code: CodeInvalidGeneration, Resource: "duplicate TS proof generation"}
		}
		proofGenerations[proof.TSGeneration] = struct{}{}
	}
	registry := &MemoryRegistry{
		device:    device,
		workloads: make(map[[32]byte]WorkloadPolicyContext, len(workloads)),
		tsProofs:  make(map[uint64]TSProofKey, len(tsProofs)),
		local:     local,
	}
	for _, workload := range workloads {
		registry.workloads[workload.SubjectDigest] = workload
	}
	for _, proof := range tsProofs {
		registry.tsProofs[proof.TSGeneration] = proof
	}
	return registry, nil
}

func (r *MemoryRegistry) Device() (DeviceIdentity, error) {
	if r == nil {
		return DeviceIdentity{}, ErrUnknownIdentity
	}
	return r.device, nil
}

func (r *MemoryRegistry) Workload(subject [32]byte) (WorkloadPolicyContext, error) {
	if r == nil {
		return WorkloadPolicyContext{}, ErrUnknownIdentity
	}
	workload, ok := r.workloads[subject]
	if !ok {
		return WorkloadPolicyContext{}, ErrUnknownIdentity
	}
	return workload, nil
}

func (r *MemoryRegistry) TSProof(generation uint64) (TSProofKey, error) {
	if r == nil {
		return TSProofKey{}, ErrUnknownIdentity
	}
	proof, ok := r.tsProofs[generation]
	if !ok {
		return TSProofKey{}, ErrUnknownIdentity
	}
	return proof, nil
}

func (r *MemoryRegistry) LocalStateIntegrity() (LocalStateIntegrityKey, error) {
	if r == nil {
		return LocalStateIntegrityKey{}, ErrUnknownIdentity
	}
	return r.local, nil
}

func validateDevice(device DeviceIdentity, now uint64) error {
	if isZero32(device.ID) || device.SourceOperatorID == "" {
		return &IdentityError{Code: CodeInvalidIdentity, Resource: "device identity"}
	}
	if device.CredentialGeneration == 0 {
		return &IdentityError{Code: CodeInvalidGeneration, Resource: "device credential generation"}
	}
	if device.CredentialNotBefore == 0 || device.CredentialExpiresAt == 0 || device.CredentialNotBefore >= device.CredentialExpiresAt {
		return &IdentityError{Code: CodeInvalidIdentity, Resource: "device credential lifetime"}
	}
	if device.CredentialExpiresAt <= now {
		return &IdentityError{Code: CodeExpiredIdentity, Resource: "device credential"}
	}
	return validateKeyRef(device.SigningKey, PurposeDeviceACPRequest)
}

func validateWorkload(workload WorkloadPolicyContext, now uint64) error {
	if isZero32(workload.SubjectDigest) {
		return &IdentityError{Code: CodeInvalidIdentity, Resource: "workload subject"}
	}
	if workload.PolicyGeneration == 0 {
		return &IdentityError{Code: CodeInvalidGeneration, Resource: "workload policy generation"}
	}
	if workload.CredentialExpiresAt == 0 || workload.PolicyExpiresAt == 0 {
		return &IdentityError{Code: CodeInvalidIdentity, Resource: "workload lifetime"}
	}
	if workload.CredentialExpiresAt <= now || workload.PolicyExpiresAt <= now {
		return &IdentityError{Code: CodeExpiredIdentity, Resource: "workload context"}
	}
	return nil
}

func validateKeyRef(ref KeyRef, purpose Purpose) error {
	if isZero32(ref.ID) {
		return &IdentityError{Code: CodeInvalidIdentity, Resource: "key reference ID"}
	}
	if !isKnownPurpose(ref.Purpose) || ref.Purpose != purpose {
		return &IdentityError{Code: CodeInvalidKeyPurpose, Resource: "key reference purpose"}
	}
	if ref.Generation == 0 {
		return &IdentityError{Code: CodeInvalidGeneration, Resource: "key reference generation"}
	}
	return nil
}

func isKnownPurpose(purpose Purpose) bool {
	return purpose == PurposeDeviceACPRequest || purpose == PurposeTSProof || purpose == PurposeLocalStateIntegrity
}

func isZero32(value [32]byte) bool {
	return value == [32]byte{}
}

var _ Registry = (*MemoryRegistry)(nil)
