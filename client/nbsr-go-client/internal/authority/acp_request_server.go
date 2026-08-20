package authority

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"errors"

	"nbsr.local/client/nbsr-go-client/internal/identity"
)

var (
	errACPRequestMalformed    = errors.New("malformed ACP request")
	errACPRequestUnauthorized = errors.New("unauthorized ACP request")
	errACPRequestBodyTooLarge = errors.New("ACP request body exceeds operation limit")
)

type DeviceACPRequestKey struct {
	KID                  [32]byte
	PublicKey            [32]byte
	Purpose              identity.Purpose
	Thumbprint           [32]byte
	KeyGeneration        uint64
	DeviceID             [32]byte
	CredentialGeneration uint64
	CredentialNotBefore  uint64
	CredentialExpiresAt  uint64
	SourceOperator       string
	NotBefore            uint64
	ExpiresAt            uint64
	Revoked              bool
}

type ACPRequestKeyResolver interface {
	ResolveDeviceACPRequestKey(context.Context, []byte, uint64) (DeviceACPRequestKey, error)
}

type authenticatedACPEnvelope struct {
	protocolVersion uint64
	operation       ACPOperation
	requestID       RequestID
	deadlineUnix    uint64
	sourceOperator  string
	profile         string
	operationFields map[uint64]any
	payload         []byte
	digest          [32]byte
	key             DeviceACPRequestKey
}

type VerifiedACPRequest struct {
	operation           ACPOperation
	requestID           RequestID
	deadlineUnix        uint64
	sourceOperator      string
	profile             string
	digest              [32]byte
	deviceID            [32]byte
	deviceGeneration    uint64
	authorityGeneration AuthorityGeneration
	acquire             *AcquireRequest
	renew               *RenewRequest
	freshness           *FreshnessRequest
}

func (request VerifiedACPRequest) Operation() ACPOperation  { return request.operation }
func (request VerifiedACPRequest) RequestID() RequestID     { return request.requestID }
func (request VerifiedACPRequest) DeadlineUnix() uint64     { return request.deadlineUnix }
func (request VerifiedACPRequest) SourceOperator() string   { return request.sourceOperator }
func (request VerifiedACPRequest) Profile() string          { return request.profile }
func (request VerifiedACPRequest) Digest() [32]byte         { return request.digest }
func (request VerifiedACPRequest) DeviceID() [32]byte       { return request.deviceID }
func (request VerifiedACPRequest) DeviceGeneration() uint64 { return request.deviceGeneration }
func (request VerifiedACPRequest) AuthorityGeneration() AuthorityGeneration {
	return request.authorityGeneration
}
func (request VerifiedACPRequest) Acquire() (AcquireRequest, bool) {
	if request.acquire == nil {
		return AcquireRequest{}, false
	}
	return cloneACPServerAcquire(*request.acquire), true
}
func (request VerifiedACPRequest) Renew() (RenewRequest, bool) {
	if request.renew == nil {
		return RenewRequest{}, false
	}
	value := *request.renew
	value.AcquireRequest = cloneACPServerAcquire(value.AcquireRequest)
	return value, true
}
func (request VerifiedACPRequest) Freshness() (FreshnessRequest, bool) {
	if request.freshness == nil {
		return FreshnessRequest{}, false
	}
	return *request.freshness, true
}

func authenticateACPEnvelope(ctx context.Context, wire []byte, resolver ACPRequestKeyResolver, now uint64) (authenticatedACPEnvelope, error) {
	if ctx == nil || isNilDependency(resolver) || now == 0 || len(wire) == 0 || len(wire) > maxACPAcquireRequestBodySize {
		return authenticatedACPEnvelope{}, errACPRequestMalformed
	}
	sign1, err := parseRouteGrantSign1(wire)
	if err != nil {
		return authenticatedACPEnvelope{}, errACPRequestMalformed
	}
	value, err := decodeCBORExact(sign1.payload, defaultCBORLimits())
	if err != nil {
		return authenticatedACPEnvelope{}, errACPRequestMalformed
	}
	canonical, err := encodeCBOR(value)
	if err != nil || !bytes.Equal(canonical, sign1.payload) {
		return authenticatedACPEnvelope{}, errACPRequestMalformed
	}
	protected, err := encodeCBOR(map[uint64]any{1: int64(-8), 4: sign1.kid})
	if err != nil || !bytes.Equal(protected, sign1.protected) {
		return authenticatedACPEnvelope{}, errACPRequestMalformed
	}
	fields, ok := value.(map[uint64]any)
	if !ok || !keysZeroThrough(fields, 6) {
		return authenticatedACPEnvelope{}, errACPRequestMalformed
	}
	version, versionOK := fields[0].(uint64)
	operationValue, operationOK := fields[1].(string)
	requestID, requestIDOK := fixed16(fields[2])
	deadline, deadlineOK := fields[3].(uint64)
	sourceOperator, sourceOK := fields[4].(string)
	profile, profileOK := fields[5].(string)
	operationFields, payloadOK := fields[6].(map[uint64]any)
	operation := ACPOperation(operationValue)
	if !versionOK || !operationOK || !validACPOperation(operation) || !requestIDOK || requestID == (RequestID{}) ||
		!deadlineOK || deadline == 0 || !validUnixTime(deadline) || !sourceOK || !validTextID(sourceOperator) ||
		!profileOK || !validTextID(profile) || !payloadOK {
		return authenticatedACPEnvelope{}, errACPRequestMalformed
	}
	if operation == ACPOperationFreshness && len(wire) > maxACPFreshnessRequestBodySize {
		return authenticatedACPEnvelope{}, errACPRequestBodyTooLarge
	}
	key, err := resolver.ResolveDeviceACPRequestKey(ctx, append([]byte(nil), sign1.kid...), now)
	if err != nil || !validDeviceACPRequestKey(key, sign1.kid, now) {
		return authenticatedACPEnvelope{}, errACPRequestUnauthorized
	}
	structure, err := encodeCBOR([]any{"Signature1", sign1.protected, []byte{}, sign1.payload})
	if err != nil || !ed25519.Verify(ed25519.PublicKey(key.PublicKey[:]), appendEnrollmentRequestSignaturePayload(structure), sign1.signature) {
		return authenticatedACPEnvelope{}, errACPRequestUnauthorized
	}
	return authenticatedACPEnvelope{
		protocolVersion: version, operation: operation, requestID: requestID, deadlineUnix: deadline,
		sourceOperator: sourceOperator, profile: profile, operationFields: operationFields,
		payload: append([]byte(nil), sign1.payload...), digest: ACPRequestDigest(sign1.payload), key: key,
	}, nil
}

func validDeviceACPRequestKey(key DeviceACPRequestKey, kid []byte, now uint64) bool {
	return key.KID != ([32]byte{}) && bytes.Equal(key.KID[:], kid) && validPublicKey(key.PublicKey) &&
		key.Purpose == identity.PurposeDeviceACPRequest && key.Thumbprint != ([32]byte{}) &&
		sha256.Sum256(key.PublicKey[:]) == key.Thumbprint && key.KeyGeneration != 0 && key.DeviceID != ([32]byte{}) &&
		key.CredentialGeneration != 0 && key.CredentialNotBefore != 0 && key.CredentialExpiresAt > key.CredentialNotBefore &&
		validUnixTime(key.CredentialNotBefore) && validUnixTime(key.CredentialExpiresAt) &&
		validTextID(key.SourceOperator) && key.NotBefore != 0 && key.ExpiresAt > key.NotBefore &&
		validUnixTime(key.NotBefore) && validUnixTime(key.ExpiresAt) && !key.Revoked &&
		now >= key.NotBefore && now < key.ExpiresAt && now >= key.CredentialNotBefore && now < key.CredentialExpiresAt
}

func verifyAuthenticatedACPEnvelope(envelope authenticatedACPEnvelope, sourceOperator, profile string, now uint64) (VerifiedACPRequest, ACPResultStatus) {
	if envelope.protocolVersion != acpProtocolVersion {
		return VerifiedACPRequest{}, ACPResultStatusUnsupportedVersion
	}
	if envelope.profile != profile {
		return VerifiedACPRequest{}, ACPResultStatusUnsupportedProfile
	}
	if envelope.sourceOperator != sourceOperator || envelope.sourceOperator != envelope.key.SourceOperator {
		return VerifiedACPRequest{}, ACPResultStatusBindingError
	}
	if now >= envelope.deadlineUnix {
		return VerifiedACPRequest{}, ACPResultStatusRequestExpired
	}
	if envelope.deadlineUnix-now > maxACPRequestDeadlineWindow {
		return VerifiedACPRequest{}, ACPResultStatusInvalidRequest
	}
	base := VerifiedACPRequest{
		operation: envelope.operation, requestID: envelope.requestID, deadlineUnix: envelope.deadlineUnix,
		sourceOperator: envelope.sourceOperator, profile: envelope.profile, digest: envelope.digest,
		deviceID: envelope.key.DeviceID, deviceGeneration: envelope.key.CredentialGeneration,
	}
	switch envelope.operation {
	case ACPOperationAcquire:
		request, _, err := decodeACPGrantRequest(envelope, false, now)
		if err != nil {
			return VerifiedACPRequest{}, acpRequestValidationStatus(err)
		}
		base.authorityGeneration = request.Key.AuthorityGeneration
		base.acquire = &request
	case ACPOperationRenew:
		request, previous, err := decodeACPGrantRequest(envelope, true, now)
		if err != nil {
			return VerifiedACPRequest{}, acpRequestValidationStatus(err)
		}
		renew := RenewRequest{AcquireRequest: request, PreviousGrant: RouteGrantDigest(previous)}
		base.authorityGeneration = request.Key.AuthorityGeneration
		base.renew = &renew
	case ACPOperationFreshness:
		request, err := decodeACPFreshnessRequest(envelope)
		if err != nil {
			return VerifiedACPRequest{}, acpRequestValidationStatus(err)
		}
		base.authorityGeneration = request.AfterGeneration
		base.freshness = &request
	default:
		return VerifiedACPRequest{}, ACPResultStatusInvalidRequest
	}
	return base, ""
}

func acpRequestValidationStatus(err error) ACPResultStatus {
	if errors.Is(err, ErrBindingMismatch) {
		return ACPResultStatusBindingError
	}
	return ACPResultStatusInvalidRequest
}

func decodeACPGrantRequest(envelope authenticatedACPEnvelope, renew bool, now uint64) (AcquireRequest, [32]byte, error) {
	fields := envelope.operationFields
	allowed := map[uint64]struct{}{0: {}, 1: {}, 2: {}, 3: {}}
	wantMinimum, wantMaximum := 3, 4
	if renew {
		allowed[4] = struct{}{}
		wantMinimum, wantMaximum = 4, 5
	}
	if len(fields) < wantMinimum || len(fields) > wantMaximum || !onlyAllowedUintKeys(fields, allowed) {
		return AcquireRequest{}, [32]byte{}, ErrInvalidAuthority
	}
	keyFields, keyOK := fields[0].(map[uint64]any)
	intentFields, intentOK := fields[1].(map[uint64]any)
	deviceFields, deviceOK := fields[2].(map[uint64]any)
	if !keyOK || !intentOK || !deviceOK {
		return AcquireRequest{}, [32]byte{}, ErrInvalidAuthority
	}
	workloadFields, hasWorkload := fields[3].(map[uint64]any)
	if _, present := fields[3]; present != hasWorkload {
		return AcquireRequest{}, [32]byte{}, ErrInvalidAuthority
	}
	key, err := decodeACPAuthorityKey(keyFields, hasWorkload)
	if err != nil {
		return AcquireRequest{}, [32]byte{}, err
	}
	intent, err := decodeACPRouteIntent(intentFields)
	if err != nil {
		return AcquireRequest{}, [32]byte{}, err
	}
	device, err := decodeACPDeviceIdentity(deviceFields)
	if err != nil {
		return AcquireRequest{}, [32]byte{}, err
	}
	var workload *identity.WorkloadPolicyContext
	if hasWorkload {
		value, err := decodeACPWorkload(workloadFields)
		if err != nil {
			return AcquireRequest{}, [32]byte{}, err
		}
		workload = &value
	}
	request := AcquireRequest{
		Key: key, Intent: intent, Device: device, Workload: workload,
		RequestID: envelope.requestID, DeadlineUnix: envelope.deadlineUnix,
	}
	if err := validateACPServerGrantRequest(request, envelope, now); err != nil {
		return AcquireRequest{}, [32]byte{}, err
	}
	var previous [32]byte
	if renew {
		value, ok := fixed32(fields[4])
		if !ok || value == ([32]byte{}) {
			return AcquireRequest{}, [32]byte{}, ErrInvalidAuthority
		}
		previous = value
	}
	return request, previous, nil
}

func decodeACPAuthorityKey(fields map[uint64]any, hasWorkload bool) (AuthorityKey, error) {
	allowed := make(map[uint64]struct{}, 18)
	for key := uint64(0); key <= 17; key++ {
		allowed[key] = struct{}{}
	}
	want := 16
	if hasWorkload {
		want = 18
	} else {
		delete(allowed, 11)
		delete(allowed, 12)
	}
	if len(fields) != want || !onlyAllowedUintKeys(fields, allowed) {
		return AuthorityKey{}, ErrInvalidAuthority
	}
	intentDigest, ok0 := fixed32(fields[0])
	serviceDigest, ok1 := fixed32(fields[1])
	source, ok2 := fields[2].(string)
	sourceEdge, ok3 := fields[3].(string)
	target, ok4 := fields[4].(string)
	targetEdges, ok5 := fixed32(fields[5])
	profile, ok6 := fields[6].(string)
	transport, ok7 := fields[7].(string)
	port, ok8 := fields[8].(uint64)
	deviceID, ok9 := fixed32(fields[9])
	deviceGeneration, ok10 := fields[10].(uint64)
	tsGeneration, ok13 := fields[13].(uint64)
	proof, ok14 := fixed32(fields[14])
	policy, ok15 := fixed32(fields[15])
	policyGeneration, ok16 := fields[16].(uint64)
	authorityGeneration, ok17 := fields[17].(uint64)
	if !(ok0 && ok1 && ok2 && ok3 && ok4 && ok5 && ok6 && ok7 && ok8 && ok9 && ok10 && ok13 && ok14 && ok15 && ok16 && ok17) || port == 0 || port > 65535 {
		return AuthorityKey{}, ErrInvalidAuthority
	}
	key := AuthorityKey{
		IntentDigest: RouteIntentDigest(intentDigest), ServiceDigest: ServiceDigest(serviceDigest), SourceOperator: source,
		SourceEdge: sourceEdge, TargetOperator: target, TargetEdgeSetDigest: targetEdges, Profile: profile,
		Transport: transport, Port: uint16(port), DeviceID: deviceID, DeviceGeneration: deviceGeneration,
		TSGeneration: TSGeneration(tsGeneration), ProofThumbprint: ProofKeyThumbprint(proof), PolicyHash: PolicyDigest(policy),
		PolicyGeneration: policyGeneration, AuthorityGeneration: AuthorityGeneration(authorityGeneration),
	}
	if hasWorkload {
		workloadDigest, digestOK := fixed32(fields[11])
		workloadGeneration, generationOK := fields[12].(uint64)
		if !digestOK || !generationOK {
			return AuthorityKey{}, ErrInvalidAuthority
		}
		key.WorkloadDigest = workloadDigest
		key.WorkloadGeneration = workloadGeneration
	}
	return key, nil
}

func decodeACPRouteIntent(fields map[uint64]any) (RouteIntent, error) {
	if !keysZeroThrough(fields, 13) {
		return RouteIntent{}, ErrInvalidAuthority
	}
	canonical, ok0 := fields[0].([]byte)
	digest, ok1 := fixed32(fields[1])
	service, ok2 := fields[2].(string)
	source, ok3 := fields[3].(string)
	sourceEdge, ok4 := fields[4].(string)
	target, ok5 := fields[5].(string)
	edgeValues, ok6 := fields[6].([]any)
	transport, ok7 := fields[7].(string)
	port, ok8 := fields[8].(uint64)
	recordSequence, ok9 := fields[9].(uint64)
	policy, ok10 := fixed32(fields[10])
	routeID, ok11 := fixed16(fields[11])
	leaseID, ok12 := fixed16(fields[12])
	expiresAt, ok13 := fields[13].(uint64)
	if !(ok0 && ok1 && ok2 && ok3 && ok4 && ok5 && ok6 && ok7 && ok8 && ok9 && ok10 && ok11 && ok12 && ok13) || port == 0 || port > 65535 {
		return RouteIntent{}, ErrInvalidAuthority
	}
	edges := make([]string, len(edgeValues))
	for index, value := range edgeValues {
		edge, ok := value.(string)
		if !ok || !validTextID(edge) || (index > 0 && edges[index-1] >= edge) {
			return RouteIntent{}, ErrInvalidAuthority
		}
		edges[index] = edge
	}
	return RouteIntent{
		Canonical: append([]byte(nil), canonical...), Digest: RouteIntentDigest(digest), ServiceIdentity: service,
		SourceOperator: source, SourceEdge: sourceEdge, TargetOperator: target, TargetEdges: edges,
		Transport: transport, Port: uint16(port), RecordSequence: recordSequence, PolicyHash: PolicyDigest(policy),
		RouteID: routeID, LeaseID: leaseID, ExpiresAt: expiresAt,
	}, nil
}

func decodeACPDeviceIdentity(fields map[uint64]any) (identity.DeviceIdentity, error) {
	if !keysZeroThrough(fields, 5) {
		return identity.DeviceIdentity{}, ErrInvalidAuthority
	}
	id, ok0 := fixed32(fields[0])
	source, ok1 := fields[1].(string)
	generation, ok2 := fields[2].(uint64)
	notBefore, ok3 := fields[3].(uint64)
	expiresAt, ok4 := fields[4].(uint64)
	keyFields, ok5 := fields[5].(map[uint64]any)
	if !(ok0 && ok1 && ok2 && ok3 && ok4 && ok5) || !keysZeroThrough(keyFields, 3) {
		return identity.DeviceIdentity{}, ErrInvalidAuthority
	}
	keyID, keyOK0 := fixed32(keyFields[0])
	purposeValue, keyOK1 := keyFields[1].(uint64)
	keyGeneration, keyOK2 := keyFields[2].(uint64)
	thumbprint, keyOK3 := fixed32(keyFields[3])
	if !(keyOK0 && keyOK1 && keyOK2 && keyOK3) || purposeValue > 255 {
		return identity.DeviceIdentity{}, ErrInvalidAuthority
	}
	return identity.DeviceIdentity{
		ID: id, SourceOperatorID: source, CredentialGeneration: generation,
		CredentialNotBefore: notBefore, CredentialExpiresAt: expiresAt,
		SigningKey: identity.KeyRef{ID: keyID, Purpose: identity.Purpose(purposeValue), Generation: keyGeneration, Thumbprint: thumbprint},
	}, nil
}

func decodeACPWorkload(fields map[uint64]any) (identity.WorkloadPolicyContext, error) {
	allowed := map[uint64]struct{}{0: {}, 1: {}, 2: {}, 3: {}}
	if len(fields) < 2 || len(fields) > 4 || !onlyAllowedUintKeys(fields, allowed) {
		return identity.WorkloadPolicyContext{}, ErrInvalidAuthority
	}
	subject, subjectOK := fixed32(fields[0])
	generation, generationOK := fields[1].(uint64)
	if !subjectOK || !generationOK {
		return identity.WorkloadPolicyContext{}, ErrInvalidAuthority
	}
	workload := identity.WorkloadPolicyContext{SubjectDigest: subject, PolicyGeneration: generation}
	if value, present := fields[2]; present {
		timestamp, ok := value.(uint64)
		if !ok {
			return identity.WorkloadPolicyContext{}, ErrInvalidAuthority
		}
		workload.CredentialExpiresAt = timestamp
	}
	if value, present := fields[3]; present {
		timestamp, ok := value.(uint64)
		if !ok {
			return identity.WorkloadPolicyContext{}, ErrInvalidAuthority
		}
		workload.PolicyExpiresAt = timestamp
	}
	return workload, nil
}

func validateACPServerGrantRequest(request AcquireRequest, envelope authenticatedACPEnvelope, now uint64) error {
	validated, err := validateAcquireRequest(request, Limits{MaxRequestBytes: maxACPAcquireRequestBodySize, MaxServiceIdentityBytes: 64})
	if err != nil {
		return err
	}
	if !validTextID(validated.Intent.ServiceIdentity) || !validTextID(validated.Intent.SourceOperator) ||
		!validTextID(validated.Intent.SourceEdge) || !validTextID(validated.Intent.TargetOperator) ||
		!validTextID(validated.Intent.Transport) || !validTextID(validated.Key.Profile) {
		return ErrInvalidAuthority
	}
	if validated.Key.SourceOperator != envelope.sourceOperator || validated.Key.Profile != envelope.profile {
		return ErrBindingMismatch
	}
	if validated.Device.SigningKey.ID != envelope.key.KID || validated.Device.SigningKey.Purpose != identity.PurposeDeviceACPRequest ||
		validated.Device.SigningKey.Generation != envelope.key.KeyGeneration || validated.Device.SigningKey.Thumbprint != envelope.key.Thumbprint ||
		validated.Device.ID != envelope.key.DeviceID || validated.Device.CredentialGeneration != envelope.key.CredentialGeneration ||
		validated.Device.SourceOperatorID != envelope.key.SourceOperator || validated.Device.CredentialNotBefore != envelope.key.CredentialNotBefore ||
		validated.Device.CredentialExpiresAt != envelope.key.CredentialExpiresAt {
		return ErrBindingMismatch
	}
	if !validUnixTime(validated.Intent.ExpiresAt) || validated.Intent.ExpiresAt <= now ||
		!validUnixTime(validated.Device.CredentialNotBefore) || !validUnixTime(validated.Device.CredentialExpiresAt) ||
		validated.Device.CredentialNotBefore >= validated.Device.CredentialExpiresAt || now < validated.Device.CredentialNotBefore || now >= validated.Device.CredentialExpiresAt {
		return ErrInvalidAuthority
	}
	if validated.Workload != nil {
		if (validated.Workload.CredentialExpiresAt != 0 && (!validUnixTime(validated.Workload.CredentialExpiresAt) || validated.Workload.CredentialExpiresAt <= now)) ||
			(validated.Workload.PolicyExpiresAt != 0 && (!validUnixTime(validated.Workload.PolicyExpiresAt) || validated.Workload.PolicyExpiresAt <= now)) {
			return ErrInvalidAuthority
		}
	}
	return nil
}

func decodeACPFreshnessRequest(envelope authenticatedACPEnvelope) (FreshnessRequest, error) {
	fields := envelope.operationFields
	if !keysZeroThrough(fields, 3) {
		return FreshnessRequest{}, ErrInvalidAuthority
	}
	deviceID, ok0 := fixed32(fields[0])
	deviceGeneration, ok1 := fields[1].(uint64)
	afterGeneration, ok2 := fields[2].(uint64)
	afterCheckpoint, ok3 := fixed32(fields[3])
	request := FreshnessRequest{
		SourceOperator: envelope.sourceOperator, Profile: envelope.profile, DeviceID: deviceID,
		DeviceGeneration: deviceGeneration, AfterGeneration: AuthorityGeneration(afterGeneration),
		AfterCheckpoint: CheckpointDigest(afterCheckpoint), DeadlineUnix: envelope.deadlineUnix,
	}
	if !(ok0 && ok1 && ok2 && ok3) || validateFreshnessRequest(request) != nil {
		return FreshnessRequest{}, ErrInvalidAuthority
	}
	if request.DeviceID != envelope.key.DeviceID || request.DeviceGeneration != envelope.key.CredentialGeneration {
		return FreshnessRequest{}, ErrBindingMismatch
	}
	return request, nil
}

func onlyAllowedUintKeys(fields map[uint64]any, allowed map[uint64]struct{}) bool {
	for key := range fields {
		if _, ok := allowed[key]; !ok {
			return false
		}
	}
	return true
}

func cloneACPServerAcquire(request AcquireRequest) AcquireRequest {
	request.Intent.Canonical = append([]byte(nil), request.Intent.Canonical...)
	request.Intent.TargetEdges = append([]string(nil), request.Intent.TargetEdges...)
	if request.Workload != nil {
		workload := *request.Workload
		request.Workload = &workload
	}
	return request
}
