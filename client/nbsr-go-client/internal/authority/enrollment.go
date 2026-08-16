package authority

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"runtime"
	"sync"

	"nbsr.local/client/nbsr-go-client/internal/identity"
)

const (
	enrollmentProtocolVersion          uint64 = 1
	maxEnrollmentRequestBodySize              = 16 * 1024
	maxEnrollmentResultBodySize               = 64 * 1024
	maxEnrollmentRequestDeadlineWindow        = uint64(30)
)

type EnrollmentStatus string

const (
	EnrollmentStatusAccepted        EnrollmentStatus = "ENROLLMENT_ACCEPTED"
	EnrollmentStatusRejected        EnrollmentStatus = "ENROLLMENT_REJECTED"
	EnrollmentStatusInvalid         EnrollmentStatus = "ENROLLMENT_INVALID"
	EnrollmentStatusRequestConflict EnrollmentStatus = "ENROLLMENT_REQUEST_CONFLICT"
	EnrollmentStatusExpired         EnrollmentStatus = "ENROLLMENT_EXPIRED"
)

var validEnrollmentStatuses = map[EnrollmentStatus]struct{}{
	EnrollmentStatusAccepted:        {},
	EnrollmentStatusRejected:        {},
	EnrollmentStatusInvalid:         {},
	EnrollmentStatusRequestConflict: {},
	EnrollmentStatusExpired:         {},
}

type EnrollmentRequestPayload struct {
	ProtocolVersion  uint64
	RequestID        RequestID
	DeadlineUnix     uint64
	SourceOperator   string
	Profile          string
	DeviceSigningKey EnrollmentDeviceSigningKey
}

type EnrollmentDeviceSigningKey struct {
	PublicKey  [32]byte
	KeyID      [32]byte
	Purpose    identity.Purpose
	Generation uint64
	Thumbprint [32]byte
}

type EnrollmentResultPayload struct {
	ProtocolVersion uint64
	RequestID       RequestID
	RequestDigest   [32]byte
	Status          EnrollmentStatus
	DeviceIdentity  *identity.DeviceIdentity
}

const enrollmentRequestSigningDomain = "NBSR-GO-CLIENT-KEY-PURPOSE-v1\x00"

func EnrollmentRequestDigest(payload []byte) [32]byte {
	return sha256.Sum256(payload)
}

func EnrollmentResultSigningPurpose() (uint16, error) {
	return resolveEnrollmentResultSigningPurpose()
}

func EncodeEnrollmentRequestPayload(request EnrollmentRequestPayload) ([]byte, error) {
	if err := validateEnrollmentRequestPayload(request); err != nil {
		return nil, err
	}
	fields := map[uint64]any{
		0: request.ProtocolVersion,
		1: request.RequestID[:],
		2: request.DeadlineUnix,
		3: request.SourceOperator,
		4: request.Profile,
		5: map[uint64]any{
			0: request.DeviceSigningKey.PublicKey[:],
			1: request.DeviceSigningKey.KeyID[:],
			2: uint64(request.DeviceSigningKey.Purpose),
			3: request.DeviceSigningKey.Generation,
			4: request.DeviceSigningKey.Thumbprint[:],
		},
	}
	return encodeCBOR(fields)
}

func ParseEnrollmentRequest(wire []byte) (EnrollmentRequestPayload, []byte, error) {
	request, canonical, _, err := parseEnrollmentRequestEnvelope(wire)
	if err != nil {
		return EnrollmentRequestPayload{}, nil, err
	}
	return request, canonical, nil
}

func ParseVerifiedEnrollmentRequest(wire []byte, now uint64) (EnrollmentRequestPayload, []byte, error) {
	request, canonical, sign1, err := parseEnrollmentRequestEnvelope(wire)
	if err != nil {
		return EnrollmentRequestPayload{}, nil, err
	}
	if !bytes.Equal(sign1.payload, canonical) {
		return EnrollmentRequestPayload{}, nil, ErrInvalidAuthority
	}
	if !sameKID(sign1.kid, request.DeviceSigningKey.KeyID[:]) {
		return EnrollmentRequestPayload{}, nil, ErrBindingMismatch
	}
	if err := validateEnrollmentRequestDeadline(request.DeadlineUnix, now); err != nil {
		return EnrollmentRequestPayload{}, nil, err
	}
	sigStructure, err := encodeEnrollmentRequestSigStructure(sign1.protected, sign1.payload)
	if err != nil {
		return EnrollmentRequestPayload{}, nil, ErrInvalidAuthority
	}
	if !ed25519.Verify(ed25519.PublicKey(request.DeviceSigningKey.PublicKey[:]), appendEnrollmentRequestSignaturePayload(sigStructure), sign1.signature) {
		return EnrollmentRequestPayload{}, nil, ErrSignatureFailure
	}
	return request, canonical, nil
}

func SignEnrollmentRequest(ctx context.Context, request EnrollmentRequestPayload, signer identity.Signer) ([]byte, error) {
	if signer == nil {
		return nil, ErrUnknownIdentity
	}
	requestPayload, err := EncodeEnrollmentRequestPayload(request)
	if err != nil {
		return nil, err
	}
	ref := signer.KeyRef()
	if ref.Purpose != identity.PurposeDeviceACPRequest {
		return nil, ErrInvalidKeyPurpose
	}
	if !bytes.Equal(ref.ID[:], request.DeviceSigningKey.KeyID[:]) ||
		ref.Generation != request.DeviceSigningKey.Generation ||
		ref.Thumbprint != request.DeviceSigningKey.Thumbprint ||
		ref.Purpose != request.DeviceSigningKey.Purpose ||
		len(ref.ID) == 0 {
		return nil, ErrBindingMismatch
	}
	protected := mustEncodeCBOR(map[uint64]any{1: int64(-8), 4: ref.ID[:]})
	sigStructure, err := encodeEnrollmentRequestSigStructure(protected, requestPayload)
	if err != nil {
		return nil, err
	}
	signature, err := signer.SignPurposeBound(ctx, identity.PurposeDeviceACPRequest, sigStructure)
	if err != nil {
		return nil, err
	}
	return buildSign1Envelope(protected, requestPayload, signature)
}

func parseEnrollmentRequestEnvelope(wire []byte) (EnrollmentRequestPayload, []byte, coseSign1, error) {
	if len(wire) == 0 || len(wire) > maxEnrollmentRequestBodySize {
		return EnrollmentRequestPayload{}, nil, coseSign1{}, ErrInvalidAuthority
	}
	sign1, err := parseRouteGrantSign1(wire)
	if err != nil {
		return EnrollmentRequestPayload{}, nil, coseSign1{}, ErrInvalidAuthority
	}
	requestValue, err := decodeCBORExact(sign1.payload, defaultCBORLimits())
	if err != nil {
		return EnrollmentRequestPayload{}, nil, coseSign1{}, ErrInvalidAuthority
	}
	request, err := decodeEnrollmentRequestPayload(requestValue)
	if err != nil {
		return EnrollmentRequestPayload{}, nil, coseSign1{}, err
	}
	canonical, err := EncodeEnrollmentRequestPayload(request)
	if err != nil {
		return EnrollmentRequestPayload{}, nil, coseSign1{}, err
	}
	return request, canonical, sign1, nil
}

func EncodeEnrollmentResultPayload(result EnrollmentResultPayload) ([]byte, error) {
	if err := validateEnrollmentResultPayload(result); err != nil {
		return nil, err
	}
	fields := map[uint64]any{
		0: result.ProtocolVersion,
		1: result.RequestID[:],
		2: result.RequestDigest[:],
		3: string(result.Status),
	}
	if result.Status == EnrollmentStatusAccepted {
		fields[4] = map[uint64]any{
			0: result.DeviceIdentity.ID[:],
			1: result.DeviceIdentity.SourceOperatorID,
			2: result.DeviceIdentity.CredentialGeneration,
			3: result.DeviceIdentity.CredentialNotBefore,
			4: result.DeviceIdentity.CredentialExpiresAt,
			5: map[uint64]any{
				0: result.DeviceIdentity.SigningKey.ID[:],
				1: uint64(result.DeviceIdentity.SigningKey.Purpose),
				2: result.DeviceIdentity.SigningKey.Generation,
				3: result.DeviceIdentity.SigningKey.Thumbprint[:],
			},
		}
	}
	return encodeCBOR(fields)
}

func ParseEnrollmentResult(wire []byte, resolvedPurpose uint16) (EnrollmentResultPayload, []byte, error) {
	result, canonical, _, err := parseEnrollmentResultEnvelope(wire, resolvedPurpose)
	if err != nil {
		return EnrollmentResultPayload{}, nil, err
	}
	return result, canonical, nil
}

func ParseVerifiedEnrollmentResult(ctx context.Context, wire []byte, request EnrollmentRequestPayload, requestPayload []byte, issuers EnrollmentResultIssuerResolver, now uint64) (EnrollmentResultPayload, []byte, error) {
	if isNilDependency(issuers) || now == 0 {
		return EnrollmentResultPayload{}, nil, ErrInvalidAuthority
	}
	if err := validateEnrollmentRequestPayload(request); err != nil {
		return EnrollmentResultPayload{}, nil, err
	}
	if len(requestPayload) == 0 {
		return EnrollmentResultPayload{}, nil, ErrInvalidAuthority
	}
	if err := validateEnrollmentRequestDeadline(request.DeadlineUnix, now); err != nil {
		return EnrollmentResultPayload{}, nil, err
	}
	purpose, err := EnrollmentResultSigningPurpose()
	if err != nil {
		return EnrollmentResultPayload{}, nil, err
	}
	result, canonical, sign1, err := parseEnrollmentResultEnvelope(wire, purpose)
	if err != nil {
		return EnrollmentResultPayload{}, nil, err
	}
	if !bytes.Equal(sign1.payload, canonical) {
		return EnrollmentResultPayload{}, nil, ErrInvalidAuthority
	}
	issuer, err := issuers.ResolveEnrollmentResultIssuer(ctx, sign1.kid, request.Profile, request.SourceOperator, now)
	if err != nil {
		return EnrollmentResultPayload{}, nil, normalizeIssuerError(err)
	}
	if err := sign1.verify(issuer.PublicKey); err != nil {
		return EnrollmentResultPayload{}, nil, err
	}
	if err := ValidateEnrollmentResultBinding(result, request, requestPayload); err != nil {
		return EnrollmentResultPayload{}, nil, err
	}
	return result, canonical, nil
}

func validateEnrollmentRequestDeadline(deadlineUnix, now uint64) error {
	if deadlineUnix == 0 || !validUnixTime(deadlineUnix) || now == 0 || !validUnixTime(now) {
		return ErrInvalidAuthority
	}
	if deadlineUnix < now {
		return ErrExpired
	}
	if deadlineUnix-now > maxEnrollmentRequestDeadlineWindow {
		return ErrInvalidAuthority
	}
	return nil
}

func encodeEnrollmentRequestSigStructure(protected, payload []byte) ([]byte, error) {
	return encodeCBOR([]any{"Signature1", protected, []byte{}, payload})
}

func appendEnrollmentRequestSignaturePayload(message []byte) []byte {
	payload := make([]byte, 0, len(enrollmentRequestSigningDomain)+1+len(message))
	payload = append(payload, enrollmentRequestSigningDomain...)
	payload = append(payload, byte(identity.PurposeDeviceACPRequest))
	payload = append(payload, message...)
	return payload
}

func buildSign1Envelope(protected, payload, signature []byte) ([]byte, error) {
	signed, err := encodeCBOR([]any{protected, map[uint64]any{}, payload, signature})
	if err != nil {
		return nil, err
	}
	enveloped := make([]byte, 0, len(signed)+1)
	enveloped = append(enveloped, 0xd2)
	return append(enveloped, signed...), nil
}

func parseEnrollmentResultEnvelope(wire []byte, resolvedPurpose uint16) (EnrollmentResultPayload, []byte, coseSign1, error) {
	if len(wire) == 0 || len(wire) > maxEnrollmentResultBodySize {
		return EnrollmentResultPayload{}, nil, coseSign1{}, ErrInvalidAuthority
	}
	sign1, err := parseRouteGrantSign1(wire)
	if err != nil {
		return EnrollmentResultPayload{}, nil, coseSign1{}, ErrInvalidAuthority
	}
	if err := validateEnrollmentResultSigningPurpose(resolvedPurpose); err != nil {
		return EnrollmentResultPayload{}, nil, coseSign1{}, err
	}
	resultValue, err := decodeCBORExact(sign1.payload, defaultCBORLimits())
	if err != nil {
		return EnrollmentResultPayload{}, nil, coseSign1{}, ErrInvalidAuthority
	}
	result, err := decodeEnrollmentResultPayload(resultValue)
	if err != nil {
		return EnrollmentResultPayload{}, nil, coseSign1{}, err
	}
	canonical, err := EncodeEnrollmentResultPayload(result)
	if err != nil {
		return EnrollmentResultPayload{}, nil, coseSign1{}, err
	}
	return result, canonical, sign1, nil
}

func ValidateEnrollmentResultBinding(result EnrollmentResultPayload, request EnrollmentRequestPayload, requestPayload []byte) error {
	if result.RequestID != request.RequestID {
		return ErrBindingMismatch
	}
	if EnrollmentRequestDigest(requestPayload) != result.RequestDigest {
		return ErrBindingMismatch
	}
	return nil
}

func decodeEnrollmentRequestPayload(value any) (EnrollmentRequestPayload, error) {
	fields, ok := value.(map[uint64]any)
	if !ok || !keysZeroThrough(fields, 5) {
		return EnrollmentRequestPayload{}, ErrInvalidAuthority
	}
	return parseEnrollmentRequestPayloadFields(fields)
}

func parseEnrollmentRequestPayloadFields(fields map[uint64]any) (EnrollmentRequestPayload, error) {
	protocolVersion, protocolVersionOK := fields[0].(uint64)
	requestID, requestIDOK := fixed16(fields[1])
	deadlineUnix, deadlineUnixOK := fields[2].(uint64)
	sourceOperator, sourceOperatorOK := fields[3].(string)
	profile, profileOK := fields[4].(string)
	deviceKeyValue, deviceKeyOK := fields[5].(map[uint64]any)
	deviceSigningKey, err := parseEnrollmentDeviceSigningKey(deviceKeyValue)
	if protocolVersion != enrollmentProtocolVersion || !protocolVersionOK || !requestIDOK || requestID == (RequestID{}) ||
		!deadlineUnixOK || deadlineUnix == 0 || deadlineUnix > maxUnixTime || !sourceOperatorOK || !validTextID(sourceOperator) ||
		!profileOK || !validTextID(profile) || !deviceKeyOK || err != nil {
		return EnrollmentRequestPayload{}, ErrInvalidAuthority
	}
	return EnrollmentRequestPayload{
		ProtocolVersion:  protocolVersion,
		RequestID:        requestID,
		DeadlineUnix:     deadlineUnix,
		SourceOperator:   sourceOperator,
		Profile:          profile,
		DeviceSigningKey: deviceSigningKey,
	}, nil
}

func parseEnrollmentDeviceSigningKey(raw map[uint64]any) (EnrollmentDeviceSigningKey, error) {
	if len(raw) != 5 {
		return EnrollmentDeviceSigningKey{}, ErrInvalidAuthority
	}
	publicKey, publicKeyOK := fixed32(raw[0])
	keyID, keyIDOK := fixed32(raw[1])
	purposeValue, purposeOK := raw[2].(uint64)
	generation, generationOK := raw[3].(uint64)
	thumbprint, thumbprintOK := fixed32(raw[4])
	if !keysZeroThrough(raw, 4) ||
		!publicKeyOK || publicKey == ([32]byte{}) ||
		!validPublicKey(publicKey) ||
		!keyIDOK || keyID == ([32]byte{}) ||
		!purposeOK ||
		!generationOK || generation == 0 ||
		!thumbprintOK || thumbprint == ([32]byte{}) {
		return EnrollmentDeviceSigningKey{}, ErrInvalidAuthority
	}
	purpose := identity.Purpose(purposeValue)
	if purpose != identity.PurposeDeviceACPRequest {
		return EnrollmentDeviceSigningKey{}, ErrInvalidAuthority
	}
	return EnrollmentDeviceSigningKey{
		PublicKey:  publicKey,
		KeyID:      keyID,
		Purpose:    purpose,
		Generation: generation,
		Thumbprint: thumbprint,
	}, nil
}

func decodeEnrollmentResultPayload(value any) (EnrollmentResultPayload, error) {
	fields, ok := value.(map[uint64]any)
	if !ok {
		return EnrollmentResultPayload{}, ErrInvalidAuthority
	}
	if !keysZeroThrough(fields, 3) && !keysZeroThrough(fields, 4) {
		return EnrollmentResultPayload{}, ErrInvalidAuthority
	}
	return parseEnrollmentResultPayloadFields(fields)
}

func parseEnrollmentResultPayloadFields(fields map[uint64]any) (EnrollmentResultPayload, error) {
	protocolVersion, protocolVersionOK := fields[0].(uint64)
	requestID, requestIDOK := fixed16(fields[1])
	requestDigest, requestDigestOK := fixed32(fields[2])
	rawStatus, statusOK := fields[3].(string)
	status := EnrollmentStatus(rawStatus)
	if protocolVersion != enrollmentProtocolVersion || !protocolVersionOK ||
		!requestIDOK || requestID == (RequestID{}) ||
		!requestDigestOK || requestDigest == ([32]byte{}) ||
		!statusOK || !isEnrollmentStatus(status) {
		return EnrollmentResultPayload{}, ErrInvalidAuthority
	}
	payload := EnrollmentResultPayload{
		ProtocolVersion: protocolVersion,
		RequestID:       requestID,
		RequestDigest:   requestDigest,
		Status:          status,
	}
	switch status {
	case EnrollmentStatusAccepted:
		if _, ok := fields[4]; !ok {
			return EnrollmentResultPayload{}, ErrInvalidAuthority
		}
		identityValue, ok := fields[4].(map[uint64]any)
		if !ok || !keysZeroThrough(identityValue, 5) {
			return EnrollmentResultPayload{}, ErrInvalidAuthority
		}
		deviceIdentity, err := parseEnrollmentDeviceIdentity(identityValue)
		if err != nil {
			return EnrollmentResultPayload{}, err
		}
		payload.DeviceIdentity = &deviceIdentity
	case EnrollmentStatusRejected, EnrollmentStatusInvalid, EnrollmentStatusRequestConflict, EnrollmentStatusExpired:
		if _, ok := fields[4]; ok {
			return EnrollmentResultPayload{}, ErrInvalidAuthority
		}
	default:
		return EnrollmentResultPayload{}, ErrInvalidAuthority
	}
	return payload, nil
}

func parseEnrollmentDeviceIdentity(raw map[uint64]any) (identity.DeviceIdentity, error) {
	if len(raw) != 6 {
		return identity.DeviceIdentity{}, ErrInvalidAuthority
	}
	id, idOK := fixed32(raw[0])
	sourceOperatorID, sourceOperatorIDOK := raw[1].(string)
	credentialGeneration, credentialGenerationOK := raw[2].(uint64)
	credentialNotBefore, credentialNotBeforeOK := raw[3].(uint64)
	credentialExpiresAt, credentialExpiresAtOK := raw[4].(uint64)
	signingKeyValue, signingKeyOK := raw[5].(map[uint64]any)
	if !keysZeroThrough(raw, 5) ||
		!idOK || id == ([32]byte{}) ||
		!sourceOperatorIDOK || !validTextID(sourceOperatorID) ||
		!credentialGenerationOK || credentialGeneration == 0 ||
		!credentialNotBeforeOK || credentialNotBefore == 0 || !validUnixTime(credentialNotBefore) ||
		!credentialExpiresAtOK || credentialExpiresAt == 0 || !validUnixTime(credentialExpiresAt) ||
		credentialExpiresAt <= credentialNotBefore || !signingKeyOK {
		return identity.DeviceIdentity{}, ErrInvalidAuthority
	}
	signingKey, err := parseEnrollmentDeviceIdentitySigningKey(signingKeyValue)
	if err != nil {
		return identity.DeviceIdentity{}, err
	}
	return identity.DeviceIdentity{
		ID:                   id,
		SourceOperatorID:     sourceOperatorID,
		CredentialGeneration: credentialGeneration,
		CredentialNotBefore:  credentialNotBefore,
		CredentialExpiresAt:  credentialExpiresAt,
		SigningKey:           signingKey,
	}, nil
}

func parseEnrollmentDeviceIdentitySigningKey(raw map[uint64]any) (identity.KeyRef, error) {
	if len(raw) != 4 {
		return identity.KeyRef{}, ErrInvalidAuthority
	}
	keyID, keyIDOK := fixed32(raw[0])
	purposeValue, purposeOK := raw[1].(uint64)
	generation, generationOK := raw[2].(uint64)
	thumbprint, thumbprintOK := fixed32(raw[3])
	purpose := identity.Purpose(purposeValue)
	if !keysZeroThrough(raw, 3) ||
		!keyIDOK || keyID == ([32]byte{}) ||
		!purposeOK ||
		!generationOK || generation == 0 ||
		!thumbprintOK || thumbprint == ([32]byte{}) ||
		purpose != identity.PurposeDeviceACPRequest {
		return identity.KeyRef{}, ErrInvalidAuthority
	}
	return identity.KeyRef{
		ID:         keyID,
		Purpose:    purpose,
		Generation: generation,
		Thumbprint: thumbprint,
	}, nil
}

func validateEnrollmentRequestPayload(request EnrollmentRequestPayload) error {
	if request.ProtocolVersion != enrollmentProtocolVersion ||
		request.RequestID == (RequestID{}) ||
		request.DeadlineUnix == 0 ||
		request.DeadlineUnix > maxUnixTime ||
		request.SourceOperator == "" ||
		request.Profile == "" ||
		!validTextID(request.SourceOperator) ||
		!validTextID(request.Profile) {
		return ErrInvalidAuthority
	}
	return validateEnrollmentDeviceSigningKey(request.DeviceSigningKey)
}

func validateEnrollmentDeviceSigningKey(key EnrollmentDeviceSigningKey) error {
	if key.PublicKey == ([32]byte{}) || !validPublicKey(key.PublicKey) ||
		key.KeyID == ([32]byte{}) ||
		key.Purpose != identity.PurposeDeviceACPRequest ||
		key.Generation == 0 ||
		key.Thumbprint == ([32]byte{}) {
		return ErrInvalidAuthority
	}
	return nil
}

func validateEnrollmentResultPayload(result EnrollmentResultPayload) error {
	if result.ProtocolVersion != enrollmentProtocolVersion ||
		result.RequestID == (RequestID{}) ||
		result.RequestDigest == ([32]byte{}) ||
		!isEnrollmentStatus(result.Status) {
		return ErrInvalidAuthority
	}
	if result.Status == EnrollmentStatusAccepted {
		if result.DeviceIdentity == nil {
			return ErrInvalidAuthority
		}
		return validateEnrollmentDeviceIdentity(*result.DeviceIdentity)
	}
	if result.DeviceIdentity != nil {
		return ErrInvalidAuthority
	}
	return nil
}

func validateEnrollmentDeviceIdentity(identityValue identity.DeviceIdentity) error {
	if identityValue.ID == ([32]byte{}) ||
		identityValue.CredentialGeneration == 0 ||
		identityValue.CredentialNotBefore == 0 ||
		identityValue.CredentialExpiresAt == 0 ||
		identityValue.CredentialExpiresAt <= identityValue.CredentialNotBefore ||
		identityValue.SourceOperatorID == "" ||
		!validTextID(identityValue.SourceOperatorID) ||
		!validUnixTime(identityValue.CredentialNotBefore) ||
		!validUnixTime(identityValue.CredentialExpiresAt) {
		return ErrInvalidAuthority
	}
	if identityValue.SigningKey.ID == ([32]byte{}) ||
		identityValue.SigningKey.Thumbprint == ([32]byte{}) ||
		identityValue.SigningKey.Generation == 0 ||
		identityValue.SigningKey.Purpose != identity.PurposeDeviceACPRequest {
		return ErrInvalidAuthority
	}
	return nil
}

func isEnrollmentStatus(value EnrollmentStatus) bool {
	_, ok := validEnrollmentStatuses[value]
	return ok
}

func validateEnrollmentResultSigningPurpose(resolvedPurpose uint16) error {
	expectedPurpose, err := EnrollmentResultSigningPurpose()
	if err != nil || expectedPurpose != resolvedPurpose {
		return ErrInvalidKeyPurpose
	}
	return nil
}

func resolveEnrollmentResultSigningPurpose() (uint16, error) {
	enrollmentResultPurposeReadOnce.Do(func() {
		cachedEnrollmentResultPurpose, cachedEnrollmentResultPurposeErr = resolveFederationKeyPurpose("ENROLLMENT_RESULT_SIGNING")
	})
	if cachedEnrollmentResultPurposeErr != nil {
		return 0, cachedEnrollmentResultPurposeErr
	}
	return cachedEnrollmentResultPurpose, nil
}

func resolveFederationKeyPurpose(name string) (uint16, error) {
	raw, err := os.ReadFile(federationDevelopmentRegistryPath())
	if err != nil {
		return 0, err
	}
	type purposeEntry struct {
		Name  string `json:"name"`
		Value uint16 `json:"value"`
	}
	type registry struct {
		Registries struct {
			KeyPurposes []purposeEntry `json:"key_purposes"`
		} `json:"registries"`
	}
	var parsed registry
	if err := json.Unmarshal(raw, &parsed); err != nil {
		return 0, err
	}
	for _, purpose := range parsed.Registries.KeyPurposes {
		if purpose.Name == name {
			return purpose.Value, nil
		}
	}
	return 0, errors.New("federation key purpose not found")
}

func federationDevelopmentRegistryPath() string {
	_, filename, _, ok := runtime.Caller(0)
	if ok {
		return filepath.Join(filepath.Dir(filename), "..", "..", "..", "..", "docs", "protocol", "registries", "federation-v0.1-development.json")
	}
	return filepath.Join("docs", "protocol", "registries", "federation-v0.1-development.json")
}

var (
	cachedEnrollmentResultPurpose    uint16
	cachedEnrollmentResultPurposeErr error
	enrollmentResultPurposeReadOnce  sync.Once
)
