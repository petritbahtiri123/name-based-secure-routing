package identity

import "context"

type Purpose uint8

const (
	PurposeDeviceACPRequest Purpose = iota + 1
	PurposeTSProof
	PurposeLocalStateIntegrity
)

type KeyRef struct {
	ID         [32]byte
	Purpose    Purpose
	Generation uint64
	Thumbprint [32]byte
}

type DeviceIdentity struct {
	ID                   [32]byte
	SourceOperatorID     string
	CredentialGeneration uint64
	CredentialNotBefore  uint64
	CredentialExpiresAt  uint64
	SigningKey           KeyRef
}

type WorkloadPolicyContext struct {
	SubjectDigest       [32]byte
	PolicyGeneration    uint64
	CredentialExpiresAt uint64
	PolicyExpiresAt     uint64
}

type TSProofKey struct {
	TSGeneration uint64
	Key          KeyRef
}

type LocalStateIntegrityKey struct{ Key KeyRef }

type Signer interface {
	KeyRef() KeyRef
	PublicKey(context.Context) ([]byte, error)
	SignPurposeBound(context.Context, Purpose, []byte) ([]byte, error)
}

type Registry interface {
	Device() (DeviceIdentity, error)
	Workload([32]byte) (WorkloadPolicyContext, error)
	TSProof(uint64) (TSProofKey, error)
	LocalStateIntegrity() (LocalStateIntegrityKey, error)
}
