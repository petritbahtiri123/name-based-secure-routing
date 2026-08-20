package authority

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/sha256"

	"nbsr.local/client/nbsr-go-client/internal/identity"
)

const (
	acpProtocolVersion             uint64 = 1
	maxACPAcquireRequestBodySize          = 64 * 1024
	maxACPRenewRequestBodySize            = 64 * 1024
	maxACPFreshnessRequestBodySize        = 16 * 1024
	maxACPAcquireResultBodySize           = 128 * 1024
	maxACPRenewResultBodySize             = 128 * 1024
	maxACPFreshnessResultBodySize         = 1 * 1024 * 1024
	maxACPRequestDeadlineWindow           = uint64(30)
	acpResultSigningPurpose        uint16 = 15
)

type ACPOperation string

const (
	ACPOperationAcquire   ACPOperation = "acquire_route_grant"
	ACPOperationRenew     ACPOperation = "renew_route_grant"
	ACPOperationFreshness ACPOperation = "freshness"
)

type ACPResultStatus string

const (
	ACPResultStatusSuccess            ACPResultStatus = "success"
	ACPResultStatusInvalidRequest     ACPResultStatus = "invalid_request"
	ACPResultStatusUnsupportedVersion ACPResultStatus = "unsupported_version"
	ACPResultStatusUnsupportedProfile ACPResultStatus = "unsupported_profile"
	ACPResultStatusRequestIDConflict  ACPResultStatus = "request_id_conflict"
	ACPResultStatusRequestExpired     ACPResultStatus = "request_expired"
	ACPResultStatusResourceExhausted  ACPResultStatus = "resource_exhausted"
	ACPResultStatusStaleGeneration    ACPResultStatus = "stale_generation"
	ACPResultStatusStaleFreshness     ACPResultStatus = "stale_freshness"
	ACPResultStatusPolicyDenied       ACPResultStatus = "policy_denied"
	ACPResultStatusRevoked            ACPResultStatus = "revoked"
	ACPResultStatusBindingError       ACPResultStatus = "binding_error"
	ACPResultStatusSignatureError     ACPResultStatus = "signature_error"
	ACPResultStatusInternalError      ACPResultStatus = "internal_error"
)

var validACPResultStatuses = map[ACPResultStatus]struct{}{
	ACPResultStatusSuccess:            {},
	ACPResultStatusInvalidRequest:     {},
	ACPResultStatusUnsupportedVersion: {},
	ACPResultStatusUnsupportedProfile: {},
	ACPResultStatusRequestIDConflict:  {},
	ACPResultStatusRequestExpired:     {},
	ACPResultStatusResourceExhausted:  {},
	ACPResultStatusStaleGeneration:    {},
	ACPResultStatusStaleFreshness:     {},
	ACPResultStatusPolicyDenied:       {},
	ACPResultStatusRevoked:            {},
	ACPResultStatusBindingError:       {},
	ACPResultStatusSignatureError:     {},
	ACPResultStatusInternalError:      {},
}

// SignedACPRequest is immutable request correlation state plus the complete
// COSE body. Only the signing functions below can construct a valid value.
type SignedACPRequest struct {
	operation           ACPOperation
	requestID           RequestID
	deadlineUnix        uint64
	sourceOperator      string
	profile             string
	authorityGeneration AuthorityGeneration
	payload             []byte
	digest              [32]byte
	body                []byte
}

func (request SignedACPRequest) Operation() ACPOperation { return request.operation }
func (request SignedACPRequest) RequestID() RequestID    { return request.requestID }
func (request SignedACPRequest) DeadlineUnix() uint64    { return request.deadlineUnix }
func (request SignedACPRequest) SourceOperator() string  { return request.sourceOperator }
func (request SignedACPRequest) Profile() string         { return request.profile }
func (request SignedACPRequest) AuthorityGeneration() AuthorityGeneration {
	return request.authorityGeneration
}
func (request SignedACPRequest) Payload() []byte  { return append([]byte(nil), request.payload...) }
func (request SignedACPRequest) Digest() [32]byte { return request.digest }
func (request SignedACPRequest) Body() []byte     { return append([]byte(nil), request.body...) }

type ACPResultPayload struct {
	ProtocolVersion     uint64
	Operation           ACPOperation
	RequestID           RequestID
	RequestDigest       [32]byte
	SourceOperator      string
	Profile             string
	AuthorityGeneration AuthorityGeneration
	Status              ACPResultStatus
	Artifact            []byte
}

// VerifiedACPResult authenticates and binds only the outer ACP result. Its
// artifact remains an untrusted candidate for the independent inner verifier.
type VerifiedACPResult struct{ result ACPResultPayload }

func (result VerifiedACPResult) Status() ACPResultStatus { return result.result.Status }
func (result VerifiedACPResult) AuthorityGeneration() AuthorityGeneration {
	return result.result.AuthorityGeneration
}
func (result VerifiedACPResult) Artifact() []byte {
	return append([]byte(nil), result.result.Artifact...)
}

type ACPResultIssuerResolver interface {
	ResolveACPResultIssuer(context.Context, []byte, string, string, uint64) (IssuerRecord, error)
}

func ACPRequestDigest(payload []byte) [32]byte { return sha256.Sum256(payload) }

func ACPResultSigningPurpose() (uint16, error) {
	return acpResultSigningPurpose, nil
}

func SignACPAcquireRequest(ctx context.Context, request AcquireRequest, signer identity.Signer, now uint64) (SignedACPRequest, error) {
	validated, err := validateACPGrantRequest(request, signer, now)
	if err != nil {
		return SignedACPRequest{}, err
	}
	return signACPRequest(ctx, ACPOperationAcquire, validated.RequestID, validated.DeadlineUnix, validated.Key.SourceOperator, validated.Key.Profile, validated.Key.AuthorityGeneration, encodeACPGrantPayload(validated, nil), signer, maxACPAcquireRequestBodySize)
}

func SignACPRenewRequest(ctx context.Context, request RenewRequest, signer identity.Signer, now uint64) (SignedACPRequest, error) {
	if request.PreviousGrant == (RouteGrantDigest{}) {
		return SignedACPRequest{}, ErrInvalidAuthority
	}
	validated, err := validateACPGrantRequest(request.AcquireRequest, signer, now)
	if err != nil {
		return SignedACPRequest{}, err
	}
	previous := [32]byte(request.PreviousGrant)
	return signACPRequest(ctx, ACPOperationRenew, validated.RequestID, validated.DeadlineUnix, validated.Key.SourceOperator, validated.Key.Profile, validated.Key.AuthorityGeneration, encodeACPGrantPayload(validated, &previous), signer, maxACPRenewRequestBodySize)
}

func SignACPFreshnessRequest(ctx context.Context, request FreshnessRequest, requestID RequestID, signer identity.Signer, now uint64) (SignedACPRequest, error) {
	if ctx == nil || requestID == (RequestID{}) || isNilDependency(signer) {
		return SignedACPRequest{}, ErrInvalidAuthority
	}
	if signer.KeyRef().Purpose != identity.PurposeDeviceACPRequest {
		return SignedACPRequest{}, ErrInvalidKeyPurpose
	}
	if err := validateFreshnessRequest(request); err != nil {
		return SignedACPRequest{}, err
	}
	if err := validateACPDeadline(request.DeadlineUnix, now); err != nil {
		return SignedACPRequest{}, err
	}
	payload := map[uint64]any{
		0: request.DeviceID[:],
		1: request.DeviceGeneration,
		2: uint64(request.AfterGeneration),
		3: request.AfterCheckpoint[:],
	}
	return signACPRequest(ctx, ACPOperationFreshness, requestID, request.DeadlineUnix, request.SourceOperator, request.Profile, request.AfterGeneration, payload, signer, maxACPFreshnessRequestBodySize)
}

func signACPRequest(ctx context.Context, operation ACPOperation, requestID RequestID, deadlineUnix uint64, sourceOperator, profile string, authorityGeneration AuthorityGeneration, operationPayload map[uint64]any, signer identity.Signer, maximum int) (SignedACPRequest, error) {
	if ctx == nil || !validACPOperation(operation) || requestID == (RequestID{}) || !validTextID(sourceOperator) || !validTextID(profile) || isNilDependency(signer) {
		return SignedACPRequest{}, ErrInvalidAuthority
	}
	payload, err := encodeCBOR(map[uint64]any{
		0: acpProtocolVersion,
		1: string(operation),
		2: requestID[:],
		3: deadlineUnix,
		4: sourceOperator,
		5: profile,
		6: operationPayload,
	})
	if err != nil {
		return SignedACPRequest{}, ErrInvalidAuthority
	}
	ref := signer.KeyRef()
	if ref.Purpose != identity.PurposeDeviceACPRequest {
		return SignedACPRequest{}, ErrInvalidKeyPurpose
	}
	if ref.ID == ([32]byte{}) || ref.Generation == 0 || ref.Thumbprint == ([32]byte{}) {
		return SignedACPRequest{}, ErrUnknownIdentity
	}
	protected, err := encodeCBOR(map[uint64]any{1: int64(-8), 4: ref.ID[:]})
	if err != nil {
		return SignedACPRequest{}, ErrInvalidAuthority
	}
	structure, err := encodeCBOR([]any{"Signature1", protected, []byte{}, payload})
	if err != nil {
		return SignedACPRequest{}, ErrInvalidAuthority
	}
	signature, err := signer.SignPurposeBound(ctx, identity.PurposeDeviceACPRequest, structure)
	if err != nil {
		return SignedACPRequest{}, err
	}
	if len(signature) != ed25519.SignatureSize {
		return SignedACPRequest{}, ErrSignatureFailure
	}
	body, err := buildSign1Envelope(protected, payload, signature)
	if err != nil || len(body) == 0 || len(body) > maximum {
		return SignedACPRequest{}, ErrInvalidAuthority
	}
	return SignedACPRequest{
		operation: operation, requestID: requestID, deadlineUnix: deadlineUnix,
		sourceOperator: sourceOperator, profile: profile, authorityGeneration: authorityGeneration,
		payload: append([]byte(nil), payload...), digest: ACPRequestDigest(payload), body: append([]byte(nil), body...),
	}, nil
}

func validateACPGrantRequest(request AcquireRequest, signer identity.Signer, now uint64) (AcquireRequest, error) {
	if isNilDependency(signer) {
		return AcquireRequest{}, ErrUnknownIdentity
	}
	if signer.KeyRef().Purpose != identity.PurposeDeviceACPRequest || request.Device.SigningKey.Purpose != identity.PurposeDeviceACPRequest {
		return AcquireRequest{}, ErrInvalidKeyPurpose
	}
	if !validTextIDs(request.Intent.TargetEdges) {
		return AcquireRequest{}, ErrInvalidAuthority
	}
	seenEdges := make(map[string]struct{}, len(request.Intent.TargetEdges))
	for _, edge := range request.Intent.TargetEdges {
		if _, duplicate := seenEdges[edge]; duplicate {
			return AcquireRequest{}, ErrInvalidAuthority
		}
		seenEdges[edge] = struct{}{}
	}
	validated, err := validateAcquireRequest(request, Limits{MaxRequestBytes: maxACPAcquireRequestBodySize, MaxServiceIdentityBytes: 64})
	if err != nil {
		return AcquireRequest{}, err
	}
	if err := validateACPDeadline(validated.DeadlineUnix, now); err != nil {
		return AcquireRequest{}, err
	}
	if !validTextID(validated.Intent.ServiceIdentity) || !validTextID(validated.Intent.SourceOperator) || !validTextID(validated.Intent.SourceEdge) || !validTextID(validated.Intent.TargetOperator) || !validTextIDs(validated.Intent.TargetEdges) || !validTextID(validated.Intent.Transport) || !validTextID(validated.Key.Profile) {
		return AcquireRequest{}, ErrInvalidAuthority
	}
	for index := 1; index < len(validated.Intent.TargetEdges); index++ {
		if validated.Intent.TargetEdges[index] == validated.Intent.TargetEdges[index-1] {
			return AcquireRequest{}, ErrInvalidAuthority
		}
	}
	if !validUnixTime(validated.Intent.ExpiresAt) || validated.Intent.ExpiresAt <= now ||
		!validUnixTime(validated.Device.CredentialNotBefore) || !validUnixTime(validated.Device.CredentialExpiresAt) ||
		validated.Device.CredentialNotBefore >= validated.Device.CredentialExpiresAt || now < validated.Device.CredentialNotBefore || now >= validated.Device.CredentialExpiresAt {
		return AcquireRequest{}, ErrExpired
	}
	ref := signer.KeyRef()
	if validated.Device.SigningKey.ID != ref.ID || validated.Device.SigningKey.Generation != ref.Generation || validated.Device.SigningKey.Thumbprint != ref.Thumbprint {
		return AcquireRequest{}, ErrBindingMismatch
	}
	if validated.Workload != nil {
		if (validated.Workload.CredentialExpiresAt != 0 && (!validUnixTime(validated.Workload.CredentialExpiresAt) || validated.Workload.CredentialExpiresAt <= now)) ||
			(validated.Workload.PolicyExpiresAt != 0 && (!validUnixTime(validated.Workload.PolicyExpiresAt) || validated.Workload.PolicyExpiresAt <= now)) {
			return AcquireRequest{}, ErrExpired
		}
	}
	return validated, nil
}

func validateACPDeadline(deadlineUnix, now uint64) error {
	if deadlineUnix == 0 || now == 0 || !validUnixTime(deadlineUnix) || !validUnixTime(now) {
		return ErrInvalidAuthority
	}
	if now >= deadlineUnix {
		return ErrExpired
	}
	if deadlineUnix-now > maxACPRequestDeadlineWindow {
		return ErrInvalidAuthority
	}
	return nil
}

func encodeACPGrantPayload(request AcquireRequest, previousGrant *[32]byte) map[uint64]any {
	key := map[uint64]any{
		0: request.Key.IntentDigest[:], 1: request.Key.ServiceDigest[:], 2: request.Key.SourceOperator,
		3: request.Key.SourceEdge, 4: request.Key.TargetOperator, 5: request.Key.TargetEdgeSetDigest[:],
		6: request.Key.Profile, 7: request.Key.Transport, 8: uint64(request.Key.Port), 9: request.Key.DeviceID[:],
		10: request.Key.DeviceGeneration, 13: uint64(request.Key.TSGeneration), 14: request.Key.ProofThumbprint[:],
		15: request.Key.PolicyHash[:], 16: request.Key.PolicyGeneration, 17: uint64(request.Key.AuthorityGeneration),
	}
	if request.Workload != nil {
		key[11] = request.Key.WorkloadDigest[:]
		key[12] = request.Key.WorkloadGeneration
	}
	edges := make([]any, len(request.Intent.TargetEdges))
	for index, edge := range request.Intent.TargetEdges {
		edges[index] = edge
	}
	payload := map[uint64]any{
		0: key,
		1: map[uint64]any{
			0: request.Intent.Canonical, 1: request.Intent.Digest[:], 2: request.Intent.ServiceIdentity,
			3: request.Intent.SourceOperator, 4: request.Intent.SourceEdge, 5: request.Intent.TargetOperator,
			6: edges, 7: request.Intent.Transport, 8: uint64(request.Intent.Port), 9: request.Intent.RecordSequence,
			10: request.Intent.PolicyHash[:], 11: request.Intent.RouteID[:], 12: request.Intent.LeaseID[:], 13: request.Intent.ExpiresAt,
		},
		2: map[uint64]any{
			0: request.Device.ID[:], 1: request.Device.SourceOperatorID, 2: request.Device.CredentialGeneration,
			3: request.Device.CredentialNotBefore, 4: request.Device.CredentialExpiresAt,
			5: map[uint64]any{0: request.Device.SigningKey.ID[:], 1: uint64(request.Device.SigningKey.Purpose), 2: request.Device.SigningKey.Generation, 3: request.Device.SigningKey.Thumbprint[:]},
		},
	}
	if request.Workload != nil {
		workload := map[uint64]any{0: request.Workload.SubjectDigest[:], 1: request.Workload.PolicyGeneration}
		if request.Workload.CredentialExpiresAt != 0 {
			workload[2] = request.Workload.CredentialExpiresAt
		}
		if request.Workload.PolicyExpiresAt != 0 {
			workload[3] = request.Workload.PolicyExpiresAt
		}
		payload[3] = workload
	}
	if previousGrant != nil {
		payload[4] = previousGrant[:]
	}
	return payload
}

func EncodeACPResultPayload(result ACPResultPayload) ([]byte, error) {
	if err := validateACPResultPayload(result); err != nil {
		return nil, err
	}
	fields := map[uint64]any{
		0: result.ProtocolVersion, 1: string(result.Operation), 2: result.RequestID[:], 3: result.RequestDigest[:],
		4: result.SourceOperator, 5: result.Profile, 6: uint64(result.AuthorityGeneration), 7: string(result.Status),
	}
	if result.Status == ACPResultStatusSuccess {
		fields[8] = result.Artifact
	}
	return encodeCBOR(fields)
}

func ParseVerifiedACPResult(ctx context.Context, wire []byte, request SignedACPRequest, issuers ACPResultIssuerResolver, now uint64) (VerifiedACPResult, error) {
	if ctx == nil || isNilDependency(issuers) || !request.valid() || now == 0 || !validUnixTime(now) {
		return VerifiedACPResult{}, ErrInvalidAuthority
	}
	maximum := acpResultBodyLimit(request.operation)
	if len(wire) == 0 || len(wire) > maximum {
		return VerifiedACPResult{}, ErrInvalidAuthority
	}
	wire = append([]byte(nil), wire...)
	sign1, err := parseRouteGrantSign1(wire)
	if err != nil {
		return VerifiedACPResult{}, ErrInvalidAuthority
	}
	value, err := decodeCBORExact(sign1.payload, defaultCBORLimits())
	if err != nil {
		return VerifiedACPResult{}, ErrInvalidAuthority
	}
	result, err := decodeACPResultPayload(value)
	if err != nil {
		return VerifiedACPResult{}, err
	}
	canonical, err := EncodeACPResultPayload(result)
	if err != nil || !bytes.Equal(canonical, sign1.payload) {
		return VerifiedACPResult{}, ErrInvalidAuthority
	}
	issuer, err := issuers.ResolveACPResultIssuer(ctx, sign1.kid, request.profile, request.sourceOperator, now)
	if err != nil {
		return VerifiedACPResult{}, normalizeIssuerError(err)
	}
	if err := validateACPResultIssuer(issuer, sign1.kid, request, now); err != nil {
		return VerifiedACPResult{}, err
	}
	if err := sign1.verify(issuer.PublicKey); err != nil {
		return VerifiedACPResult{}, err
	}
	if err := validateACPResultBinding(result, request); err != nil {
		return VerifiedACPResult{}, err
	}
	result.Artifact = append([]byte(nil), result.Artifact...)
	return VerifiedACPResult{result: result}, nil
}

func (request SignedACPRequest) valid() bool {
	if !validACPOperation(request.operation) || request.requestID == (RequestID{}) || request.deadlineUnix == 0 ||
		!validTextID(request.sourceOperator) || !validTextID(request.profile) || len(request.payload) == 0 || len(request.body) == 0 {
		return false
	}
	return request.digest == ACPRequestDigest(request.payload)
}

func validateACPResultPayload(result ACPResultPayload) error {
	if result.ProtocolVersion != acpProtocolVersion || !validACPOperation(result.Operation) || result.RequestID == (RequestID{}) ||
		result.RequestDigest == ([32]byte{}) || !validTextID(result.SourceOperator) || !validTextID(result.Profile) ||
		result.AuthorityGeneration == 0 || result.AuthorityGeneration == ^AuthorityGeneration(0) || !validACPResultStatus(result.Status) {
		return ErrInvalidAuthority
	}
	if result.Status == ACPResultStatusSuccess {
		if len(result.Artifact) == 0 {
			return ErrInvalidAuthority
		}
	} else if result.Artifact != nil {
		return ErrInvalidAuthority
	}
	return nil
}

func decodeACPResultPayload(value any) (ACPResultPayload, error) {
	fields, ok := value.(map[uint64]any)
	if !ok || (!keysZeroThrough(fields, 7) && !keysZeroThrough(fields, 8)) {
		return ACPResultPayload{}, ErrInvalidAuthority
	}
	version, versionOK := fields[0].(uint64)
	operationValue, operationOK := fields[1].(string)
	requestID, requestIDOK := fixed16(fields[2])
	requestDigest, requestDigestOK := fixed32(fields[3])
	sourceOperator, sourceOperatorOK := fields[4].(string)
	profile, profileOK := fields[5].(string)
	generation, generationOK := fields[6].(uint64)
	statusValue, statusOK := fields[7].(string)
	result := ACPResultPayload{
		ProtocolVersion: version, Operation: ACPOperation(operationValue), RequestID: requestID, RequestDigest: requestDigest,
		SourceOperator: sourceOperator, Profile: profile, AuthorityGeneration: AuthorityGeneration(generation), Status: ACPResultStatus(statusValue),
	}
	if !versionOK || !operationOK || !requestIDOK || !requestDigestOK || !sourceOperatorOK || !profileOK || !generationOK || !statusOK {
		return ACPResultPayload{}, ErrInvalidAuthority
	}
	if artifact, present := fields[8]; present {
		raw, ok := artifact.([]byte)
		if !ok {
			return ACPResultPayload{}, ErrInvalidAuthority
		}
		result.Artifact = raw
	}
	if err := validateACPResultPayload(result); err != nil {
		return ACPResultPayload{}, err
	}
	return result, nil
}

func validateACPResultBinding(result ACPResultPayload, request SignedACPRequest) error {
	if result.Operation != request.operation || result.RequestID != request.requestID || result.RequestDigest != request.digest ||
		result.SourceOperator != request.sourceOperator || result.Profile != request.profile {
		return ErrBindingMismatch
	}
	if request.operation != ACPOperationFreshness && result.AuthorityGeneration != request.authorityGeneration {
		return ErrStaleGeneration
	}
	return nil
}

func validateACPResultIssuer(issuer IssuerRecord, kid []byte, request SignedACPRequest, now uint64) error {
	if len(issuer.KID) < 1 || len(issuer.KID) > 64 || !sameKID(issuer.KID, kid) || !validPublicKey(issuer.PublicKey) ||
		issuer.Profile != request.profile || issuer.SourceOperator != request.sourceOperator || issuer.Generation == 0 || issuer.NotBefore >= issuer.ExpiresAt {
		return ErrUnknownIdentity
	}
	purpose, err := ACPResultSigningPurpose()
	if err != nil {
		return ErrInvalidAuthority
	}
	if issuer.Purpose != purpose {
		return ErrInvalidKeyPurpose
	}
	if issuer.Revoked {
		return ErrRevoked
	}
	if now < issuer.NotBefore || now >= issuer.ExpiresAt {
		return ErrExpired
	}
	return nil
}

func validACPOperation(operation ACPOperation) bool {
	return operation == ACPOperationAcquire || operation == ACPOperationRenew || operation == ACPOperationFreshness
}

func validACPResultStatus(status ACPResultStatus) bool {
	_, ok := validACPResultStatuses[status]
	return ok
}

func acpResultBodyLimit(operation ACPOperation) int {
	switch operation {
	case ACPOperationAcquire:
		return maxACPAcquireResultBodySize
	case ACPOperationRenew:
		return maxACPRenewResultBodySize
	case ACPOperationFreshness:
		return maxACPFreshnessResultBodySize
	default:
		return 0
	}
}
