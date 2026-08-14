package authority

import (
	"context"
	"crypto/sha256"
	"encoding/binary"
	"sort"

	"nbsr.local/client/nbsr-go-client/internal/identity"
)

type AuthorityGeneration uint64
type TSGeneration uint64
type RequestID [16]byte
type RouteIntentDigest [32]byte
type RouteGrantDigest [32]byte
type ServiceDigest [32]byte
type PolicyDigest [32]byte
type ProofKeyThumbprint [32]byte
type CheckpointDigest [32]byte

type RouteIntent struct {
	Canonical       []byte
	Digest          RouteIntentDigest
	ServiceIdentity string
	SourceOperator  string
	SourceEdge      string
	TargetOperator  string
	TargetEdges     []string
	Transport       string
	Port            uint16
	RecordSequence  uint64
	PolicyHash      PolicyDigest
	RouteID         [16]byte
	LeaseID         [16]byte
	ExpiresAt       uint64
}

type AuthorityKey struct {
	IntentDigest        RouteIntentDigest
	ServiceDigest       ServiceDigest
	SourceOperator      string
	SourceEdge          string
	TargetOperator      string
	TargetEdgeSetDigest [32]byte
	Profile             string
	Transport           string
	Port                uint16
	DeviceID            [32]byte
	DeviceGeneration    uint64
	WorkloadDigest      [32]byte
	WorkloadGeneration  uint64
	TSGeneration        TSGeneration
	ProofThumbprint     ProofKeyThumbprint
	PolicyHash          PolicyDigest
	PolicyGeneration    uint64
	AuthorityGeneration AuthorityGeneration
}

type AcquireRequest struct {
	Key          AuthorityKey
	Intent       RouteIntent
	Device       identity.DeviceIdentity
	Workload     *identity.WorkloadPolicyContext
	RequestID    RequestID
	DeadlineUnix uint64
}

type RenewRequest struct {
	AcquireRequest
	PreviousGrant RouteGrantDigest
}

type FreshnessRequest struct {
	SourceOperator   string
	Profile          string
	DeviceID         [32]byte
	DeviceGeneration uint64
	AfterGeneration  AuthorityGeneration
	AfterCheckpoint  CheckpointDigest
	DeadlineUnix     uint64
}

type ProviderGrant struct {
	ExactRouteGrant     []byte
	Profile             string
	AuthorityGeneration AuthorityGeneration
	Checkpoint          CheckpointDigest
}

type ProviderFreshness struct {
	SourceOperator string
	Profile        string
	Evidence       []byte
}

type AuthorityProvider interface {
	Acquire(context.Context, AcquireRequest) (ProviderGrant, error)
	Renew(context.Context, RenewRequest) (ProviderGrant, error)
	Freshness(context.Context, FreshnessRequest) (ProviderFreshness, error)
	Close() error
}

type IssuerRecord struct {
	KID            []byte
	PublicKey      [32]byte
	Purpose        uint16
	Profile        string
	SourceOperator string
	Generation     uint64
	NotBefore      uint64
	ExpiresAt      uint64
	Revoked        bool
}

type IssuerResolver interface {
	ResolveRouteGrantIssuer(context.Context, []byte, string, string, uint64) (IssuerRecord, error)
}

type CheckpointClaims struct {
	SourceOperator string
	Profile        string
	Generation     AuthorityGeneration
	IssuedAt       uint64
	FreshUntil     uint64
	Digest         CheckpointDigest
	RevokedGrants  []RouteGrantDigest
}

type CheckpointEvidenceVerifier interface {
	VerifyFreshnessEvidence(context.Context, ProviderFreshness, FreshnessRequest, uint64) (CheckpointClaims, error)
}

type Verifier struct{ issuers IssuerResolver }

// verifiedAuthority is private so only verifier.go can construct an authority
// after checking the exact frozen RouteGrant bytes and all caller bindings.
type verifiedAuthority struct {
	key                 AuthorityKey
	grantDigest         RouteGrantDigest
	expiresAt           uint64
	checkpoint          CheckpointDigest
	authorityGeneration AuthorityGeneration
}

// verifiedCheckpoint is the sealed result of independently verified ACP
// freshness evidence. Its fields intentionally remain private: raw
// CheckpointClaims are provider/verifier candidates, never local authority.
type verifiedCheckpoint struct {
	sourceOperator string
	profile        string
	generation     AuthorityGeneration
	issuedAt       uint64
	freshUntil     uint64
	digest         CheckpointDigest
	revoked        []RouteGrantDigest
}
type VerifiedAuthority struct{ seal verifiedAuthority }
type VerifiedCheckpoint struct{ seal verifiedCheckpoint }

// Generation, FreshUntil, and Digest are the only public checkpoint facts
// needed by later authority consumers. They return values, never mutable
// backing storage.
func (checkpoint VerifiedCheckpoint) Generation() AuthorityGeneration {
	return checkpoint.seal.generation
}
func (checkpoint VerifiedCheckpoint) FreshUntil() uint64       { return checkpoint.seal.freshUntil }
func (checkpoint VerifiedCheckpoint) Digest() CheckpointDigest { return checkpoint.seal.digest }

func (checkpoint VerifiedCheckpoint) sourceOperator() string { return checkpoint.seal.sourceOperator }
func (checkpoint VerifiedCheckpoint) profile() string        { return checkpoint.seal.profile }
func (checkpoint VerifiedCheckpoint) issuedAt() uint64       { return checkpoint.seal.issuedAt }
func (checkpoint VerifiedCheckpoint) revokedDigests() []RouteGrantDigest {
	return append([]RouteGrantDigest(nil), checkpoint.seal.revoked...)
}
func (checkpoint VerifiedCheckpoint) hasRevoked(grant RouteGrantDigest) bool {
	for _, revoked := range checkpoint.seal.revoked {
		if revoked == grant {
			return true
		}
	}
	return false
}
func (checkpoint VerifiedCheckpoint) valid() bool {
	return validTextID(checkpoint.seal.sourceOperator) && validTextID(checkpoint.seal.profile) && checkpoint.seal.generation != 0 && checkpoint.seal.generation != ^AuthorityGeneration(0) && checkpoint.seal.issuedAt < checkpoint.seal.freshUntil && validUnixTime(checkpoint.seal.issuedAt) && validUnixTime(checkpoint.seal.freshUntil) && checkpoint.seal.digest != (CheckpointDigest{})
}

type Limits struct {
	MaxCacheEntries, MaxPending, MaxWaitersPerPending, MaxRequestRecords int
	MaxCacheBytes, MaxPendingBytes, MaxRequestBytes                      uint64
	MaxGrantBytes, MaxCheckpointEvidenceBytes, MaxServiceIdentityBytes   int
}

func (l Limits) Validate() error {
	if l.MaxCacheEntries <= 0 || l.MaxPending <= 0 || l.MaxWaitersPerPending <= 0 || l.MaxRequestRecords <= 0 ||
		l.MaxCacheBytes == 0 || l.MaxPendingBytes == 0 || l.MaxRequestBytes == 0 ||
		l.MaxGrantBytes <= 0 || l.MaxCheckpointEvidenceBytes <= 0 || l.MaxServiceIdentityBytes <= 0 {
		return &AuthorityError{Code: CodeInvalidLimits, Resource: "all limits must be nonzero"}
	}
	return nil
}

type Clock interface{ NowUnix() uint64 }
type RequestIDSource interface{ NewRequestID() (RequestID, error) }

type GenerationSnapshot struct{ generation AuthorityGeneration }
type Reservation struct {
	id    uint64
	key   AuthorityKey
	grant RouteGrantDigest
}
type AuthorityHandle struct {
	key        AuthorityKey
	grant      RouteGrantDigest
	generation AuthorityGeneration
	expiresAt  uint64
	checkpoint CheckpointDigest
}
type AdmissionOwner struct {
	TSGeneration TSGeneration
	ChannelID    [16]byte
}

type Usage struct {
	CacheEntries, PendingCalls, PendingWaiters, RequestRecords int
	CacheBytes, PendingBytes, RequestBytes                     uint64
}

type RequestStatus uint8

const (
	RequestPending RequestStatus = iota + 1
	RequestComplete
	RequestAmbiguous
)

type RequestSnapshot struct {
	ID                  RequestID
	RequestDigest       [32]byte
	ResultDigest        [32]byte
	Status              RequestStatus
	AuthorityGeneration AuthorityGeneration
	ExpiresAt           uint64
}

type SignedGenerationFloor struct {
	SourceOperator string
	Profile        string
	Generation     AuthorityGeneration
	Checkpoint     CheckpointDigest
	SignedEvidence []byte
}

type GenerationFloorStore interface {
	// Load returns ErrFloorNotFound only for authenticated, pristine storage for
	// the requested source-operator/profile enrollment. If a floor was ever
	// stored for that enrollment, deletion, loss, rollback, or any uncertainty
	// about its presence must return ErrFloorInvalid. Durable adapters are a
	// later concern, but must preserve this distinction.
	Load(context.Context, string, string) (SignedGenerationFloor, error)
	// StoreHigher durably records only a semantic floor that is higher than the
	// current floor, or byte-identical at the same generation.
	StoreHigher(context.Context, SignedGenerationFloor) error
}

func validateAcquireRequest(request AcquireRequest, limits Limits) (AcquireRequest, error) {
	if err := validateAuthorityKey(request.Key, request.Workload != nil); err != nil {
		return AcquireRequest{}, err
	}
	if request.RequestID == (RequestID{}) || request.DeadlineUnix == 0 {
		return AcquireRequest{}, &AuthorityError{Code: CodeInvalidAuthority, Resource: "request"}
	}
	if len(request.Intent.Canonical) == 0 || uint64(len(request.Intent.Canonical)) > limits.MaxRequestBytes ||
		len(request.Intent.ServiceIdentity) == 0 || len(request.Intent.ServiceIdentity) > limits.MaxServiceIdentityBytes ||
		request.Intent.SourceOperator == "" || request.Intent.SourceEdge == "" || request.Intent.TargetOperator == "" ||
		request.Intent.Transport == "" || request.Intent.Port == 0 || request.Intent.RecordSequence == 0 ||
		request.Intent.PolicyHash == (PolicyDigest{}) || request.Intent.RouteID == ([16]byte{}) ||
		request.Intent.LeaseID == ([16]byte{}) || request.Intent.ExpiresAt == 0 {
		return AcquireRequest{}, &AuthorityError{Code: CodeInvalidAuthority, Resource: "route intent"}
	}
	if RouteIntentDigest(sha256.Sum256(request.Intent.Canonical)) != request.Intent.Digest {
		return AcquireRequest{}, &AuthorityError{Code: CodeInvalidAuthority, Resource: "route intent digest"}
	}
	edges := append([]string(nil), request.Intent.TargetEdges...)
	if len(edges) == 0 {
		return AcquireRequest{}, &AuthorityError{Code: CodeInvalidAuthority, Resource: "target edges"}
	}
	for _, edge := range edges {
		if edge == "" {
			return AcquireRequest{}, &AuthorityError{Code: CodeInvalidAuthority, Resource: "target edge"}
		}
	}
	sort.Strings(edges)
	if request.Key.IntentDigest != request.Intent.Digest || request.Key.SourceOperator != request.Intent.SourceOperator ||
		request.Key.SourceEdge != request.Intent.SourceEdge || request.Key.TargetOperator != request.Intent.TargetOperator ||
		request.Key.Transport != request.Intent.Transport || request.Key.Port != request.Intent.Port ||
		request.Key.PolicyHash != request.Intent.PolicyHash || request.Key.TargetEdgeSetDigest != targetEdgeSetDigest(edges) {
		return AcquireRequest{}, &AuthorityError{Code: CodeBindingMismatch, Resource: "authority key"}
	}
	if request.Device.ID == ([32]byte{}) || request.Device.SourceOperatorID == "" || request.Device.CredentialGeneration == 0 ||
		request.Device.ID != request.Key.DeviceID || request.Device.CredentialGeneration != request.Key.DeviceGeneration ||
		request.Device.SourceOperatorID != request.Key.SourceOperator {
		return AcquireRequest{}, &AuthorityError{Code: CodeBindingMismatch, Resource: "device identity"}
	}
	if request.Workload == nil {
		if request.Key.WorkloadDigest != ([32]byte{}) || request.Key.WorkloadGeneration != 0 {
			return AcquireRequest{}, &AuthorityError{Code: CodeBindingMismatch, Resource: "workload policy"}
		}
	} else if request.Workload.SubjectDigest == ([32]byte{}) || request.Workload.PolicyGeneration == 0 ||
		request.Workload.SubjectDigest != request.Key.WorkloadDigest || request.Workload.PolicyGeneration != request.Key.WorkloadGeneration {
		return AcquireRequest{}, &AuthorityError{Code: CodeBindingMismatch, Resource: "workload policy"}
	}

	request.Intent.Canonical = append([]byte(nil), request.Intent.Canonical...)
	request.Intent.TargetEdges = edges
	if request.Workload != nil {
		workload := *request.Workload
		request.Workload = &workload
	}
	return request, nil
}

func validateAuthorityKey(key AuthorityKey, hasWorkload bool) error {
	if key.IntentDigest == (RouteIntentDigest{}) || key.ServiceDigest == (ServiceDigest{}) || key.SourceOperator == "" ||
		key.SourceEdge == "" || key.TargetOperator == "" || key.TargetEdgeSetDigest == ([32]byte{}) || key.Profile == "" ||
		key.Transport == "" || key.Port == 0 || key.DeviceID == ([32]byte{}) || key.DeviceGeneration == 0 ||
		key.TSGeneration == 0 || key.ProofThumbprint == (ProofKeyThumbprint{}) || key.PolicyHash == (PolicyDigest{}) ||
		key.PolicyGeneration == 0 || key.AuthorityGeneration == 0 {
		return &AuthorityError{Code: CodeInvalidAuthority, Resource: "authority key"}
	}
	if hasWorkload {
		if key.WorkloadDigest == ([32]byte{}) || key.WorkloadGeneration == 0 {
			return &AuthorityError{Code: CodeInvalidAuthority, Resource: "workload authority key"}
		}
	} else if key.WorkloadDigest != ([32]byte{}) || key.WorkloadGeneration != 0 {
		return &AuthorityError{Code: CodeInvalidAuthority, Resource: "workload authority key"}
	}
	return nil
}

func targetEdgeSetDigest(edges []string) [32]byte {
	canonical := append([]string(nil), edges...)
	sort.Strings(canonical)
	hash := sha256.New()
	var length [8]byte
	for _, edge := range canonical {
		binary.BigEndian.PutUint64(length[:], uint64(len(edge)))
		_, _ = hash.Write(length[:])
		_, _ = hash.Write([]byte(edge))
	}
	var digest [32]byte
	copy(digest[:], hash.Sum(nil))
	return digest
}

func copyProviderGrant(grant ProviderGrant, limits Limits) (ProviderGrant, error) {
	if len(grant.ExactRouteGrant) == 0 || len(grant.ExactRouteGrant) > limits.MaxGrantBytes || grant.Profile == "" ||
		grant.AuthorityGeneration == 0 || grant.Checkpoint == (CheckpointDigest{}) {
		return ProviderGrant{}, &AuthorityError{Code: CodeInvalidAuthority, Resource: "provider grant"}
	}
	grant.ExactRouteGrant = append([]byte(nil), grant.ExactRouteGrant...)
	return grant, nil
}

func copyProviderFreshness(freshness ProviderFreshness, limits Limits) (ProviderFreshness, error) {
	if freshness.SourceOperator == "" || freshness.Profile == "" || len(freshness.Evidence) == 0 ||
		len(freshness.Evidence) > limits.MaxCheckpointEvidenceBytes {
		return ProviderFreshness{}, &AuthorityError{Code: CodeInvalidAuthority, Resource: "provider freshness"}
	}
	freshness.Evidence = append([]byte(nil), freshness.Evidence...)
	return freshness, nil
}
