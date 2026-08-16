package authority

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"testing"

	"nbsr.local/client/nbsr-go-client/internal/identity"
)

func TestTask2EnrollmentRequestSignAndVerify(t *testing.T) {
	request := validEnrollmentRequestPayload()
	signer, public, keyID := mustEnrollmentSigner(t, identity.PurposeDeviceACPRequest, 0x11, 1)
	request.DeviceSigningKey = EnrollmentDeviceSigningKey{
		PublicKey:  public,
		KeyID:      keyID,
		Purpose:    identity.PurposeDeviceACPRequest,
		Generation: 1,
		Thumbprint: sha256.Sum256(public[:]),
	}

	requestPayload, err := EncodeEnrollmentRequestPayload(request)
	if err != nil {
		t.Fatal(err)
	}

	wire, err := SignEnrollmentRequest(context.Background(), request, signer)
	if err != nil {
		t.Fatal(err)
	}
	parsed, canonical, err := ParseVerifiedEnrollmentRequest(wire, request.DeadlineUnix)
	if err != nil {
		t.Fatal(err)
	}
	if parsed != request {
		t.Fatal("verified request mismatch")
	}
	if !bytes.Equal(canonical, requestPayload) {
		t.Fatal("canonical request payload changed")
	}

	sign1, err := parseRouteGrantSign1(wire)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(sign1.kid, keyID[:]) {
		t.Fatal("request KID mismatch")
	}
	sigStructure, err := encodeEnrollmentRequestSigStructure(sign1.protected, sign1.payload)
	if err != nil {
		t.Fatal(err)
	}
	if !ed25519.Verify(ed25519.PublicKey(public[:]), appendEnrollmentRequestSignaturePayload(sigStructure), sign1.signature) {
		t.Fatal("request signature does not verify")
	}

	reencoded, err := EncodeEnrollmentRequestPayload(parsed)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(canonical, reencoded) {
		t.Fatal("request payload is not byte-stable")
	}
}

func TestTask2EnrollmentRequestVerificationRejectsBadRequest(t *testing.T) {
	request := validEnrollmentRequestPayload()
	signer, public, keyID := mustEnrollmentSigner(t, identity.PurposeDeviceACPRequest, 0x12, 1)
	request.DeviceSigningKey = EnrollmentDeviceSigningKey{
		PublicKey:  public,
		KeyID:      keyID,
		Purpose:    identity.PurposeDeviceACPRequest,
		Generation: 1,
		Thumbprint: sha256.Sum256(public[:]),
	}

	wire, err := SignEnrollmentRequest(context.Background(), request, signer)
	if err != nil {
		t.Fatal(err)
	}

	if _, _, err := ParseVerifiedEnrollmentRequest(wire, request.DeadlineUnix+1); !errors.Is(err, ErrExpired) {
		t.Fatalf("expired request accepted: %v", err)
	}
	if _, _, err := ParseVerifiedEnrollmentRequest(wire, request.DeadlineUnix-31); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("deadline underflow accepted: %v", err)
	}
	if _, _, err := ParseVerifiedEnrollmentRequest(wire[:len(wire)-1], request.DeadlineUnix); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatal("truncated request accepted")
	}

	sign1, err := parseRouteGrantSign1(wire)
	if err != nil {
		t.Fatal(err)
	}
	tamperedPayload := append([]byte(nil), sign1.payload...)
	tamperedPayload[0] ^= 0x01
	tamperedEnvelope := mustBuildSign1Envelope(t, sign1.protected, tamperedPayload, sign1.signature)
	if _, _, err := ParseVerifiedEnrollmentRequest(tamperedEnvelope, request.DeadlineUnix); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatal("tampered request payload accepted")
	}

	header, err := decodeCBORExact(sign1.protected, defaultCBORLimits())
	if err != nil {
		t.Fatal(err)
	}
	protected := header.(map[uint64]any)
	protected[1] = int64(-7)
	malformedHeader, err := encodeCBOR(protected)
	if err != nil {
		t.Fatal(err)
	}
	malformedAlg := mustBuildSign1Envelope(t, malformedHeader, sign1.payload, sign1.signature)
	if _, _, err := ParseVerifiedEnrollmentRequest(malformedAlg, request.DeadlineUnix); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatal("wrong algorithm accepted")
	}

	invalidPurposeSigner, _, _ := mustEnrollmentSigner(t, identity.PurposeTSProof, 0x13, 1)
	if _, err := SignEnrollmentRequest(context.Background(), request, invalidPurposeSigner); !errors.Is(err, ErrInvalidKeyPurpose) {
		t.Fatalf("wrong request purpose accepted: %v", err)
	}

	_, otherPublic, otherKeyID := mustEnrollmentSigner(t, identity.PurposeDeviceACPRequest, 0x14, 1)
	request.DeviceSigningKey = EnrollmentDeviceSigningKey{
		PublicKey:  otherPublic,
		KeyID:      otherKeyID,
		Purpose:    identity.PurposeDeviceACPRequest,
		Generation: 1,
		Thumbprint: sha256.Sum256(otherPublic[:]),
	}
	if _, err := SignEnrollmentRequest(context.Background(), request, signer); !errors.Is(err, ErrBindingMismatch) {
		t.Fatal("request signer/public-key mismatch accepted")
	}
}

func TestTask2EnrollmentResultVerificationAndBinding(t *testing.T) {
	request := validEnrollmentRequestPayload()
	reqSigner, reqPublic, reqKeyID := mustEnrollmentSigner(t, identity.PurposeDeviceACPRequest, 0x21, 1)
	request.DeviceSigningKey = EnrollmentDeviceSigningKey{
		PublicKey:  reqPublic,
		KeyID:      reqKeyID,
		Purpose:    identity.PurposeDeviceACPRequest,
		Generation: 1,
		Thumbprint: sha256.Sum256(reqPublic[:]),
	}

	requestPayload, err := EncodeEnrollmentRequestPayload(request)
	if err != nil {
		t.Fatal(err)
	}
	requestWire, err := SignEnrollmentRequest(context.Background(), request, reqSigner)
	if err != nil {
		t.Fatal(err)
	}
	parsedRequest, canonicalRequest, err := ParseVerifiedEnrollmentRequest(requestWire, request.DeadlineUnix)
	if err != nil {
		t.Fatal(err)
	}

	resultPurpose, err := EnrollmentResultSigningPurpose()
	if err != nil {
		t.Fatal(err)
	}
	resultPrivate, resultPublic, resultKid := mustRawResultSigner(t, 0x30)
	resolver := mustEnrollmentResultResolver(t, request, resultPurpose, resultPublic, resultKid)

	resultPayload := validEnrollmentResultPayload(EnrollmentStatusAccepted, requestPayload)
	resultWire, err := signEnrollmentResultPayload(resultPayload, resultPrivate, resultKid)
	if err != nil {
		t.Fatal(err)
	}
	verified, canonicalResult, err := ParseVerifiedEnrollmentResult(context.Background(), resultWire, parsedRequest, canonicalRequest, resolver, request.DeadlineUnix)
	if err != nil {
		t.Fatal(err)
	}
	reencodedResult, err := EncodeEnrollmentResultPayload(verified)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(canonicalResult, reencodedResult) {
		t.Fatal("result payload is not byte-stable")
	}
	if verified.RequestDigest != EnrollmentRequestDigest(requestPayload) {
		t.Fatal("result request digest mismatch")
	}
	if verified.DeviceIdentity == nil {
		t.Fatal("accepted result missing device identity")
	}

	coSEDigest := sha256.Sum256(resultWire)
	wrongDigestPayload := validEnrollmentResultPayload(EnrollmentStatusAccepted, requestPayload)
	wrongDigestPayload.RequestDigest = coSEDigest
	wrongDigestWire, err := signEnrollmentResultPayload(wrongDigestPayload, resultPrivate, resultKid)
	if err != nil {
		t.Fatal(err)
	}
	if _, _, err := ParseVerifiedEnrollmentResult(context.Background(), wrongDigestWire, parsedRequest, canonicalRequest, resolver, request.DeadlineUnix); !errors.Is(err, ErrBindingMismatch) {
		t.Fatalf("result digest over COSE envelope accepted: %v", err)
	}

	mismatchRequest := parsedRequest
	mismatchRequest.RequestID[0] ^= 0x10
	if _, _, err := ParseVerifiedEnrollmentResult(context.Background(), resultWire, mismatchRequest, canonicalRequest, resolver, request.DeadlineUnix); !errors.Is(err, ErrBindingMismatch) {
		t.Fatalf("request-id mismatch accepted: %v", err)
	}
}

func TestTask2EnrollmentResultRejectsTrustFailuresAndMalformed(t *testing.T) {
	request := validEnrollmentRequestPayload()
	reqSigner, reqPublic, reqKeyID := mustEnrollmentSigner(t, identity.PurposeDeviceACPRequest, 0x22, 1)
	request.DeviceSigningKey = EnrollmentDeviceSigningKey{
		PublicKey:  reqPublic,
		KeyID:      reqKeyID,
		Purpose:    identity.PurposeDeviceACPRequest,
		Generation: 1,
		Thumbprint: sha256.Sum256(reqPublic[:]),
	}

	requestPayload, err := EncodeEnrollmentRequestPayload(request)
	if err != nil {
		t.Fatal(err)
	}
	requestWire, err := SignEnrollmentRequest(context.Background(), request, reqSigner)
	if err != nil {
		t.Fatal(err)
	}
	parsedRequest, canonicalRequest, err := ParseVerifiedEnrollmentRequest(requestWire, request.DeadlineUnix)
	if err != nil {
		t.Fatal(err)
	}

	resultPurpose, err := EnrollmentResultSigningPurpose()
	if err != nil {
		t.Fatal(err)
	}
	resultPrivate, resultPublic, resultKid := mustRawResultSigner(t, 0x31)
	validResolver := mustEnrollmentResultResolver(t, request, resultPurpose, resultPublic, resultKid)

	resultPayload := validEnrollmentResultPayload(EnrollmentStatusAccepted, requestPayload)
	resultWire, err := signEnrollmentResultPayload(resultPayload, resultPrivate, resultKid)
	if err != nil {
		t.Fatal(err)
	}

	wrongPurposeResolver := mustEnrollmentResultResolver(t, request, 15, resultPublic, resultKid)
	if _, _, err := ParseVerifiedEnrollmentResult(context.Background(), resultWire, parsedRequest, canonicalRequest, wrongPurposeResolver, request.DeadlineUnix); !errors.Is(err, ErrInvalidKeyPurpose) {
		t.Fatalf("ACP_RESULT_SIGNING purpose unexpectedly accepted: %v", err)
	}

	otherKid := []byte("other-kid-16bytes----")
	unknownKidResolver := mustEnrollmentResultResolver(t, request, resultPurpose, resultPublic, otherKid)
	if _, _, err := ParseVerifiedEnrollmentResult(context.Background(), resultWire, parsedRequest, canonicalRequest, unknownKidResolver, request.DeadlineUnix); !errors.Is(err, ErrUnknownIdentity) {
		t.Fatalf("unknown KID unexpectedly accepted: %v", err)
	}

	otherOperator := request
	otherOperator.SourceOperator = "other.operator"
	wrongOperatorResolver := mustEnrollmentResultResolver(t, otherOperator, resultPurpose, resultPublic, resultKid)
	if _, _, err := ParseVerifiedEnrollmentResult(context.Background(), resultWire, parsedRequest, canonicalRequest, wrongOperatorResolver, request.DeadlineUnix); !errors.Is(err, ErrUnknownIdentity) {
		t.Fatalf("wrong source-operator accepted: %v", err)
	}

	wrongResultSigner, _, _ := mustRawResultSigner(t, 0x32)
	wrongSignedWire, err := signEnrollmentResultPayload(resultPayload, wrongResultSigner, resultKid)
	if err != nil {
		t.Fatal(err)
	}
	if _, _, err := ParseVerifiedEnrollmentResult(context.Background(), wrongSignedWire, parsedRequest, canonicalRequest, validResolver, request.DeadlineUnix); !errors.Is(err, ErrSignatureFailure) {
		t.Fatalf("wrong signing key expected signature failure: %v", err)
	}

	invalid := append([]byte{0xd2}, readRepo(t, "vectors", "core-v0.2", "artifacts", "invalid", "structural", "cbor-duplicate-map-key.bin")...)
	if _, _, err := ParseEnrollmentResult(invalid, resultPurpose); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatal("malformed result map accepted")
	}
	oversized := append([]byte{0xd2}, bytes.Repeat([]byte{0x00}, maxEnrollmentResultBodySize+1)...)
	if _, _, err := ParseEnrollmentResult(oversized, resultPurpose); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatal("oversized result accepted")
	}
	if _, _, err := ParseVerifiedEnrollmentResult(context.Background(), testSign1Wire([]byte{0xa2, 0x01, 0x26, 0x04, 0x45, 'x'}, []byte{0xa0}, testByteString([]byte{1})), parsedRequest, canonicalRequest, validResolver, request.DeadlineUnix); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("wrong result algorithm unexpectedly accepted: %v", err)
	}
	if _, _, err := ParseVerifiedEnrollmentResult(context.Background(), testSign1Wire([]byte{0xa2, 0x01, 0x27, 0x04, 0x45, 'r', 'e', 'q', 'u', 'l'}, []byte{}, testByteString([]byte{1})), parsedRequest, canonicalRequest, validResolver, request.DeadlineUnix); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("detached payload unexpectedly accepted: %v", err)
	}
}

func mustBuildSign1Envelope(t *testing.T, protected, payload, signature []byte) []byte {
	t.Helper()
	wire, err := buildSign1Envelope(protected, payload, signature)
	if err != nil {
		t.Fatal(err)
	}
	return wire
}

func signEnrollmentResultPayload(result EnrollmentResultPayload, signer ed25519.PrivateKey, kid []byte) ([]byte, error) {
	payload, err := EncodeEnrollmentResultPayload(result)
	if err != nil {
		return nil, err
	}
	protected := mustEncodeCBOR(map[uint64]any{1: int64(-8), 4: kid})
	structure, err := encodeCBOR([]any{"Signature1", protected, []byte{}, payload})
	if err != nil {
		return nil, err
	}
	signature := ed25519.Sign(signer, structure)
	return buildSign1Envelope(protected, payload, signature)
}

func mustEnrollmentSigner(t *testing.T, purpose identity.Purpose, seedByte byte, generation uint64) (identity.Signer, [32]byte, [32]byte) {
	t.Helper()
	seed := bytes32ForSeed(seedByte)
	private := ed25519.NewKeyFromSeed(seed[:])
	public := private.Public().(ed25519.PublicKey)
	var public32 [32]byte
	copy(public32[:], public)
	keyID := bytes32ForSeed(seedByte + 1)
	signer, err := identity.NewMemorySigner(identity.KeyRef{
		ID:         keyID,
		Purpose:    purpose,
		Generation: generation,
		Thumbprint: sha256.Sum256(public),
	}, private)
	if err != nil {
		t.Fatal(err)
	}
	return signer, public32, keyID
}

func mustRawResultSigner(t *testing.T, seedByte byte) (ed25519.PrivateKey, [32]byte, []byte) {
	t.Helper()
	seed := bytes32ForSeed(seedByte)
	private := ed25519.NewKeyFromSeed(seed[:])
	public := private.Public().(ed25519.PublicKey)
	var public32 [32]byte
	copy(public32[:], public)
	return private, public32, []byte{seedByte, seedByte, seedByte, seedByte}
}

func mustEnrollmentResultResolver(t *testing.T, request EnrollmentRequestPayload, purpose uint16, public [32]byte, kid []byte) EnrollmentResultIssuerResolver {
	t.Helper()
	record := IssuerRecord{
		KID:            append([]byte(nil), kid...),
		PublicKey:      public,
		Purpose:        purpose,
		Profile:        request.Profile,
		SourceOperator: request.SourceOperator,
		Generation:     3,
		NotBefore:      request.DeadlineUnix - 1,
		ExpiresAt:      request.DeadlineUnix + 10,
	}
	resolver, err := NewStaticIssuerResolver([]IssuerRecord{record})
	if err != nil {
		t.Fatal(err)
	}
	return resolver
}

func bytes32ForSeed(seedByte byte) [32]byte {
	var seed [32]byte
	for i := range seed {
		seed[i] = seedByte
	}
	return seed
}

func mustEncodeCBOR(value any) []byte {
	raw, err := encodeCBOR(value)
	if err != nil {
		panic(err)
	}
	return raw
}

func mustHex32Literal(value string) [32]byte {
	raw, err := hex.DecodeString(value)
	if err != nil || len(raw) != 32 {
		panic("invalid hex literal")
	}
	var out [32]byte
	copy(out[:], raw)
	return out
}

func validEnrollmentRequestPayload() EnrollmentRequestPayload {
	return EnrollmentRequestPayload{
		ProtocolVersion: 1,
		RequestID:       RequestID{1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16},
		DeadlineUnix:    1_893_456_000,
		SourceOperator:  "source.operator",
		Profile:         "nbsr-federation-dev-v1",
		DeviceSigningKey: EnrollmentDeviceSigningKey{
			PublicKey:  mustHex32Literal("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"),
			KeyID:      mustHex32Literal("1111111111111111111111111111111111111111111111111111111111111111"),
			Purpose:    identity.PurposeDeviceACPRequest,
			Generation: 1,
			Thumbprint: mustHex32Literal("2222222222222222222222222222222222222222222222222222222222222222"),
		},
	}
}

func validEnrollmentResultPayload(status EnrollmentStatus, requestPayload []byte) EnrollmentResultPayload {
	payload := EnrollmentResultPayload{
		ProtocolVersion: 1,
		RequestID:       validEnrollmentRequestPayload().RequestID,
		RequestDigest:   EnrollmentRequestDigest(requestPayload),
		Status:          status,
	}
	if status == EnrollmentStatusAccepted {
		payload.DeviceIdentity = &identity.DeviceIdentity{
			ID:                   mustHex32Literal("3333333333333333333333333333333333333333333333333333333333333333"),
			SourceOperatorID:     "source.operator",
			CredentialGeneration: 1,
			CredentialNotBefore:  1_893_456_001,
			CredentialExpiresAt:  1_893_457_001,
			SigningKey: identity.KeyRef{
				ID:         mustHex32Literal("4444444444444444444444444444444444444444444444444444444444444444"),
				Purpose:    identity.PurposeDeviceACPRequest,
				Generation: 1,
				Thumbprint: mustHex32Literal("5555555555555555555555555555555555555555555555555555555555555555"),
			},
		}
	}
	return payload
}
