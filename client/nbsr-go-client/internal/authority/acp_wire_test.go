package authority

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"errors"
	"reflect"
	"testing"

	"nbsr.local/client/nbsr-go-client/internal/identity"
)

const acpTestNow = uint64(1_893_456_000)

func TestSignACPRequestsUseFrozenSchemasAndPurpose(t *testing.T) {
	signer, public, keyID := mustEnrollmentSigner(t, identity.PurposeDeviceACPRequest, 0x31, 4)
	acquire := validACPRequest(signer.KeyRef())
	renew := RenewRequest{AcquireRequest: acquire, PreviousGrant: RouteGrantDigest(bytes32ForSeed(0x41))}
	freshness := FreshnessRequest{
		SourceOperator:   acquire.Key.SourceOperator,
		Profile:          acquire.Key.Profile,
		DeviceID:         acquire.Device.ID,
		DeviceGeneration: acquire.Device.CredentialGeneration,
		AfterGeneration:  acquire.Key.AuthorityGeneration,
		AfterCheckpoint:  CheckpointDigest(bytes32ForSeed(0x42)),
		DeadlineUnix:     acquire.DeadlineUnix,
	}

	tests := []struct {
		name           string
		operation      ACPOperation
		requestID      RequestID
		wantPayloadKey []uint64
		wantPayloadSHA [32]byte
		wantBodySHA    [32]byte
		sign           func() (SignedACPRequest, error)
	}{
		{"acquire", ACPOperationAcquire, acquire.RequestID, []uint64{0, 1, 2, 3}, mustHex32Literal("369122675ceae29ffed9342149961ecf8cc219061155f114951c11b404980d67"), mustHex32Literal("3fb4e109cb8890a19b9eda925aef316a1e829feabc3870619ce4bb4a2725baff"), func() (SignedACPRequest, error) {
			return SignACPAcquireRequest(context.Background(), acquire, signer, acpTestNow)
		}},
		{"renew", ACPOperationRenew, renew.RequestID, []uint64{0, 1, 2, 3, 4}, mustHex32Literal("5f6cf8b4a5ac0a60c3f662d1e0e2585d5eee3ab1ec979187179f52ed05824717"), mustHex32Literal("fe4300e854f1753ebd92bf55a14fd70d0e9c1008d5f5a7b5db18a9c5c6876f31"), func() (SignedACPRequest, error) {
			return SignACPRenewRequest(context.Background(), renew, signer, acpTestNow)
		}},
		{"freshness", ACPOperationFreshness, RequestID{16, 15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1}, []uint64{0, 1, 2, 3}, mustHex32Literal("1c028277feb3ec077ba415d687c4ae6bdddeae03220573e3702124cd2dd69c42"), mustHex32Literal("2bfc2bc6f0171cd17449f3118fbf793d171e12bac7b059edc43d3a6aad18d359"), func() (SignedACPRequest, error) {
			return SignACPFreshnessRequest(context.Background(), freshness, RequestID{16, 15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1}, signer, acpTestNow)
		}},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			signed, err := test.sign()
			if err != nil {
				t.Fatal(err)
			}
			second, err := test.sign()
			if err != nil {
				t.Fatal(err)
			}
			if !bytes.Equal(signed.Body(), second.Body()) || !bytes.Equal(signed.Payload(), second.Payload()) {
				t.Fatal("deterministic signing changed bytes")
			}
			if signed.Operation() != test.operation || signed.RequestID() != test.requestID {
				t.Fatal("signed request metadata mismatch")
			}
			body := signed.Body()
			body[0] ^= 0xff
			if bytes.Equal(body, signed.Body()) {
				t.Fatal("signed request leaked mutable body backing storage")
			}
			payloadCopy := signed.Payload()
			payloadCopy[0] ^= 0xff
			if bytes.Equal(payloadCopy, signed.Payload()) {
				t.Fatal("signed request leaked mutable payload backing storage")
			}
			if signed.Digest() != sha256.Sum256(signed.Payload()) {
				t.Fatal("request digest is not SHA-256 over exact payload")
			}
			if got := sha256.Sum256(signed.Payload()); got != test.wantPayloadSHA {
				t.Fatalf("payload SHA-256 = %x, want %x", got, test.wantPayloadSHA)
			}
			if got := sha256.Sum256(signed.Body()); got != test.wantBodySHA {
				t.Fatalf("body SHA-256 = %x, want %x", got, test.wantBodySHA)
			}

			sign1, err := parseRouteGrantSign1(signed.Body())
			if err != nil {
				t.Fatal(err)
			}
			if !bytes.Equal(sign1.kid, keyID[:]) || !bytes.Equal(sign1.payload, signed.Payload()) {
				t.Fatal("COSE protected kid or embedded payload mismatch")
			}
			structure, err := encodeCBOR([]any{"Signature1", sign1.protected, []byte{}, sign1.payload})
			if err != nil {
				t.Fatal(err)
			}
			if !ed25519.Verify(ed25519.PublicKey(public[:]), appendEnrollmentRequestSignaturePayload(structure), sign1.signature) {
				t.Fatal("request is not bound to PurposeDeviceACPRequest")
			}

			value, err := decodeCBORExact(signed.Payload(), defaultCBORLimits())
			if err != nil {
				t.Fatal(err)
			}
			fields := requireExactUintKeys(t, value, []uint64{0, 1, 2, 3, 4, 5, 6})
			if fields[0] != uint64(1) || fields[1] != string(test.operation) || fields[3] != acquire.DeadlineUnix || fields[4] != acquire.Key.SourceOperator || fields[5] != acquire.Key.Profile {
				t.Fatal("frozen common request fields mismatch")
			}
			payload := requireExactUintKeys(t, fields[6], test.wantPayloadKey)
			switch test.operation {
			case ACPOperationAcquire, ACPOperationRenew:
				requireExactUintKeys(t, payload[0], uintRange(0, 17))
				requireExactUintKeys(t, payload[1], uintRange(0, 13))
				device := requireExactUintKeys(t, payload[2], uintRange(0, 5))
				requireExactUintKeys(t, device[5], uintRange(0, 3))
				requireExactUintKeys(t, payload[3], uintRange(0, 3))
			}
		})
	}
}

func TestSignACPRequestRejectsSecurityAndBindingFailures(t *testing.T) {
	signer, _, _ := mustEnrollmentSigner(t, identity.PurposeDeviceACPRequest, 0x51, 4)
	base := validACPRequest(signer.KeyRef())

	tests := []struct {
		name string
		edit func(*AcquireRequest)
		want error
	}{
		{"expired deadline", func(request *AcquireRequest) { request.DeadlineUnix = acpTestNow }, ErrExpired},
		{"deadline beyond horizon", func(request *AcquireRequest) { request.DeadlineUnix = acpTestNow + 31 }, ErrInvalidAuthority},
		{"intent digest binding", func(request *AcquireRequest) { request.Intent.Canonical[0] ^= 0xff }, ErrInvalidAuthority},
		{"duplicate target edge", func(request *AcquireRequest) { request.Intent.TargetEdges[1] = request.Intent.TargetEdges[0] }, ErrInvalidAuthority},
		{"device signing key purpose", func(request *AcquireRequest) { request.Device.SigningKey.Purpose = identity.PurposeTSProof }, ErrInvalidKeyPurpose},
		{"device signing key id", func(request *AcquireRequest) { request.Device.SigningKey.ID[0] ^= 0xff }, ErrBindingMismatch},
		{"operator binding", func(request *AcquireRequest) { request.Device.SourceOperatorID = "other.operator" }, ErrBindingMismatch},
		{"transport text constraint", func(request *AcquireRequest) {
			request.Key.Transport = "TCP"
			request.Intent.Transport = "TCP"
		}, ErrInvalidAuthority},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			request := cloneACPRequest(base)
			test.edit(&request)
			_, err := SignACPAcquireRequest(context.Background(), request, signer, acpTestNow)
			if !errors.Is(err, test.want) {
				t.Fatalf("got %v, want %v", err, test.want)
			}
		})
	}

	wrongSigner, _, _ := mustEnrollmentSigner(t, identity.PurposeTSProof, 0x61, 4)
	if _, err := SignACPAcquireRequest(context.Background(), base, wrongSigner, acpTestNow); !errors.Is(err, ErrInvalidKeyPurpose) {
		t.Fatalf("cross-purpose signer got %v", err)
	}
	shortSigner := shortSignatureSigner{Signer: signer}
	if _, err := SignACPAcquireRequest(context.Background(), base, shortSigner, acpTestNow); !errors.Is(err, ErrSignatureFailure) {
		t.Fatalf("short Ed25519 signature got %v", err)
	}

	oversized := cloneACPRequest(base)
	oversized.Intent.Canonical = bytes.Repeat([]byte{0x61}, maxACPAcquireRequestBodySize)
	oversized.Intent.Digest = RouteIntentDigest(sha256.Sum256(oversized.Intent.Canonical))
	oversized.Key.IntentDigest = oversized.Intent.Digest
	if _, err := SignACPAcquireRequest(context.Background(), oversized, signer, acpTestNow); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("oversized complete request got %v", err)
	}

	if _, err := SignACPRenewRequest(context.Background(), RenewRequest{AcquireRequest: base}, signer, acpTestNow); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("renew without predecessor got %v", err)
	}
	freshness := FreshnessRequest{
		SourceOperator: base.Key.SourceOperator, Profile: base.Key.Profile, DeviceID: base.Device.ID,
		DeviceGeneration: base.Device.CredentialGeneration, DeadlineUnix: base.DeadlineUnix,
	}
	if _, err := SignACPFreshnessRequest(context.Background(), freshness, RequestID{}, signer, acpTestNow); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("freshness without request ID got %v", err)
	}
}

func TestSignACPGrantRequestsRejectZeroCredentialNotBefore(t *testing.T) {
	signer, _, _ := mustEnrollmentSigner(t, identity.PurposeDeviceACPRequest, 0x62, 4)
	base := validACPRequest(signer.KeyRef())
	base.Device.CredentialNotBefore = 0

	for _, test := range []struct {
		name string
		sign func() error
	}{
		{"acquire", func() error {
			_, err := SignACPAcquireRequest(context.Background(), base, signer, acpTestNow)
			return err
		}},
		{"renew", func() error {
			_, err := SignACPRenewRequest(context.Background(), RenewRequest{
				AcquireRequest: base,
				PreviousGrant:  RouteGrantDigest(bytes32ForSeed(0x63)),
			}, signer, acpTestNow)
			return err
		}},
	} {
		t.Run(test.name, func(t *testing.T) {
			if err := test.sign(); !errors.Is(err, ErrInvalidAuthority) {
				t.Fatalf("zero credential_not_before got %v, want ErrInvalidAuthority", err)
			}
		})
	}
}

func TestParseVerifiedACPResultBindsOuterEnvelope(t *testing.T) {
	requestSigner, _, _ := mustEnrollmentSigner(t, identity.PurposeDeviceACPRequest, 0x71, 4)
	request, err := SignACPAcquireRequest(context.Background(), validACPRequest(requestSigner.KeyRef()), requestSigner, acpTestNow)
	if err != nil {
		t.Fatal(err)
	}
	private, public, kid := mustRawResultSigner(t, 0x72)
	purpose, err := ACPResultSigningPurpose()
	if err != nil {
		t.Fatal(err)
	}
	if purpose != 15 {
		t.Fatalf("ACP_RESULT_SIGNING = %d, want 15", purpose)
	}
	resolver := mustACPResultResolver(t, request, purpose, public, kid)
	result := validACPResult(request, ACPResultStatusSuccess)
	wire := mustSignACPResult(t, result, private, kid)

	verified, err := ParseVerifiedACPResult(context.Background(), wire, request, resolver, acpTestNow)
	if err != nil {
		t.Fatal(err)
	}
	if verified.Status() != ACPResultStatusSuccess || verified.AuthorityGeneration() != request.AuthorityGeneration() || !bytes.Equal(verified.Artifact(), result.Artifact) {
		t.Fatal("verified ACP result candidate mismatch")
	}
	artifact := verified.Artifact()
	artifact[0] ^= 0xff
	if bytes.Equal(artifact, verified.Artifact()) {
		t.Fatal("verified result leaked mutable artifact backing storage")
	}
}

func TestParseVerifiedACPResultRejectsExpiredRequestBeforeIssuerResolution(t *testing.T) {
	requestSigner, _, _ := mustEnrollmentSigner(t, identity.PurposeDeviceACPRequest, 0x73, 4)
	request, err := SignACPAcquireRequest(context.Background(), validACPRequest(requestSigner.KeyRef()), requestSigner, acpTestNow)
	if err != nil {
		t.Fatal(err)
	}
	private, public, kid := mustRawResultSigner(t, 0x74)
	wire := mustSignACPResult(t, validACPResult(request, ACPResultStatusSuccess), private, kid)
	issuer := IssuerRecord{
		KID: kid, PublicKey: public, Purpose: acpResultSigningPurpose,
		Profile: request.Profile(), SourceOperator: request.SourceOperator(), Generation: 1,
		NotBefore: acpTestNow - 1, ExpiresAt: request.DeadlineUnix() + 100,
	}

	for _, test := range []struct {
		name string
		now  uint64
	}{
		{"at deadline", request.DeadlineUnix()},
		{"after deadline", request.DeadlineUnix() + 1},
	} {
		t.Run(test.name, func(t *testing.T) {
			calls := 0
			resolver := acpResultIssuerResolverFunc(func(context.Context, []byte, string, string, uint64) (IssuerRecord, error) {
				calls++
				return issuer, nil
			})
			if _, err := ParseVerifiedACPResult(context.Background(), wire, request, resolver, test.now); !errors.Is(err, ErrExpired) {
				t.Fatalf("got %v, want ErrExpired", err)
			}
			if calls != 0 {
				t.Fatalf("issuer resolver called %d times after request deadline", calls)
			}
		})
	}
}

func TestACPResultGoldenVectors(t *testing.T) {
	signer, _, _ := mustEnrollmentSigner(t, identity.PurposeDeviceACPRequest, 0xd1, 4)
	acquireValue := validACPRequest(signer.KeyRef())
	acquire, err := SignACPAcquireRequest(context.Background(), acquireValue, signer, acpTestNow)
	if err != nil {
		t.Fatal(err)
	}
	renew, err := SignACPRenewRequest(context.Background(), RenewRequest{AcquireRequest: acquireValue, PreviousGrant: RouteGrantDigest(bytes32ForSeed(0xd2))}, signer, acpTestNow)
	if err != nil {
		t.Fatal(err)
	}
	freshness, err := SignACPFreshnessRequest(context.Background(), FreshnessRequest{
		SourceOperator: acquireValue.Key.SourceOperator, Profile: acquireValue.Key.Profile, DeviceID: acquireValue.Device.ID,
		DeviceGeneration: acquireValue.Device.CredentialGeneration, AfterGeneration: acquireValue.Key.AuthorityGeneration,
		AfterCheckpoint: CheckpointDigest(bytes32ForSeed(0xd3)), DeadlineUnix: acquireValue.DeadlineUnix,
	}, RequestID{2, 4, 6, 8, 10, 12, 14, 16, 1, 3, 5, 7, 9, 11, 13, 15}, signer, acpTestNow)
	if err != nil {
		t.Fatal(err)
	}
	private, _, kid := mustRawResultSigner(t, 0xd4)

	for _, test := range []struct {
		name           string
		request        SignedACPRequest
		wantPayloadSHA [32]byte
		wantBodySHA    [32]byte
	}{
		{"acquire", acquire, mustHex32Literal("981e4d1eda3b12cdaca80056ebea6b1019535b0fbbc183d67dd05b8851f04355"), mustHex32Literal("17a7638c63737f0ef3ca5f1105721d2a648bfdb0b31e0c99db7dd8a51521d7db")},
		{"renew", renew, mustHex32Literal("dcf00328992106c6bdb3d9838050cb150c56d5ece2bab9b797602338bd3c861e"), mustHex32Literal("1ae5e98c3b4839910c83e4a064612019fb4fc818f648c4a0195157e30dd0d97d")},
		{"freshness", freshness, mustHex32Literal("2f3ec1cadc46214b61a627cb401c491c9999371e4c2e4cf6b2f0ab79d8ed9655"), mustHex32Literal("eea547c2f48a2dd37c422c979c754ec54eaf23db0198f80df69f3b7f5b9843ca")},
	} {
		t.Run(test.name, func(t *testing.T) {
			result := validACPResult(test.request, ACPResultStatusSuccess)
			payload, err := EncodeACPResultPayload(result)
			if err != nil {
				t.Fatal(err)
			}
			body := mustSignACPResult(t, result, private, kid)
			if got := sha256.Sum256(payload); got != test.wantPayloadSHA {
				t.Fatalf("payload SHA-256 = %x, want %x", got, test.wantPayloadSHA)
			}
			if got := sha256.Sum256(body); got != test.wantBodySHA {
				t.Fatalf("body SHA-256 = %x, want %x", got, test.wantBodySHA)
			}
		})
	}
}

func TestParseVerifiedACPResultRejectsBindingAndPurposeFailures(t *testing.T) {
	requestSigner, _, _ := mustEnrollmentSigner(t, identity.PurposeDeviceACPRequest, 0x81, 4)
	request, err := SignACPAcquireRequest(context.Background(), validACPRequest(requestSigner.KeyRef()), requestSigner, acpTestNow)
	if err != nil {
		t.Fatal(err)
	}
	private, public, kid := mustRawResultSigner(t, 0x82)
	purpose, err := ACPResultSigningPurpose()
	if err != nil {
		t.Fatal(err)
	}
	resolver := mustACPResultResolver(t, request, purpose, public, kid)

	tests := []struct {
		name string
		edit func(*ACPResultPayload)
		want error
	}{
		{"request id", func(result *ACPResultPayload) { result.RequestID[0] ^= 0xff }, ErrBindingMismatch},
		{"request digest", func(result *ACPResultPayload) { result.RequestDigest[0] ^= 0xff }, ErrBindingMismatch},
		{"source operator", func(result *ACPResultPayload) { result.SourceOperator = "other.operator" }, ErrBindingMismatch},
		{"profile", func(result *ACPResultPayload) { result.Profile = "other-profile" }, ErrBindingMismatch},
		{"operation", func(result *ACPResultPayload) { result.Operation = ACPOperationRenew }, ErrBindingMismatch},
		{"authority generation", func(result *ACPResultPayload) { result.AuthorityGeneration++ }, ErrStaleGeneration},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			result := validACPResult(request, ACPResultStatusSuccess)
			test.edit(&result)
			wire := mustSignACPResult(t, result, private, kid)
			if _, err := ParseVerifiedACPResult(context.Background(), wire, request, resolver, acpTestNow); !errors.Is(err, test.want) {
				t.Fatalf("got %v, want %v", err, test.want)
			}
		})
	}

	wrongPurposeResolver := mustACPResultResolver(t, request, purpose-1, public, kid)
	wire := mustSignACPResult(t, validACPResult(request, ACPResultStatusSuccess), private, kid)
	if _, err := ParseVerifiedACPResult(context.Background(), wire, request, wrongPurposeResolver, acpTestNow); !errors.Is(err, ErrInvalidKeyPurpose) {
		t.Fatalf("cross-purpose result got %v", err)
	}
}

func TestParseVerifiedACPResultRejectsMalformedAndNoncanonicalWire(t *testing.T) {
	requestSigner, _, _ := mustEnrollmentSigner(t, identity.PurposeDeviceACPRequest, 0x91, 4)
	request, err := SignACPAcquireRequest(context.Background(), validACPRequest(requestSigner.KeyRef()), requestSigner, acpTestNow)
	if err != nil {
		t.Fatal(err)
	}
	private, public, kid := mustRawResultSigner(t, 0x92)
	purpose, err := ACPResultSigningPurpose()
	if err != nil {
		t.Fatal(err)
	}
	resolver := mustACPResultResolver(t, request, purpose, public, kid)
	validWire := mustSignACPResult(t, validACPResult(request, ACPResultStatusSuccess), private, kid)

	badAlgProtected := mustEncodeCBOR(map[uint64]any{1: int64(-7), 4: kid})
	badAlgPayload, err := EncodeACPResultPayload(validACPResult(request, ACPResultStatusSuccess))
	if err != nil {
		t.Fatal(err)
	}
	badAlgStructure := mustEncodeCBOR([]any{"Signature1", badAlgProtected, []byte{}, badAlgPayload})
	badAlgWire, err := buildSign1Envelope(badAlgProtected, badAlgPayload, ed25519.Sign(private, badAlgStructure))
	if err != nil {
		t.Fatal(err)
	}

	tests := []struct {
		name string
		wire []byte
	}{
		{"empty", nil},
		{"malformed CBOR", []byte{0xd2, 0xff}},
		{"trailing bytes", append(append([]byte(nil), validWire...), 0)},
		{"wrong algorithm", badAlgWire},
		{"oversized body", make([]byte, maxACPAcquireResultBodySize+1)},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			if _, err := ParseVerifiedACPResult(context.Background(), test.wire, request, resolver, acpTestNow); !errors.Is(err, ErrInvalidAuthority) {
				t.Fatalf("got %v, want invalid authority", err)
			}
		})
	}
}

func TestParseVerifiedACPResultRejectsFrozenStructuralInvalidVectors(t *testing.T) {
	requestSigner, _, _ := mustEnrollmentSigner(t, identity.PurposeDeviceACPRequest, 0xb1, 4)
	request, err := SignACPAcquireRequest(context.Background(), validACPRequest(requestSigner.KeyRef()), requestSigner, acpTestNow)
	if err != nil {
		t.Fatal(err)
	}
	private, public, kid := mustRawResultSigner(t, 0xb2)
	purpose, err := ACPResultSigningPurpose()
	if err != nil {
		t.Fatal(err)
	}
	resolver := mustACPResultResolver(t, request, purpose, public, kid)
	base := rawACPResultFields(validACPResult(request, ACPResultStatusSuccess))

	missing := cloneUintMap(base)
	delete(missing, 6)
	unknown := cloneUintMap(base)
	unknown[9] = uint64(1)
	wrongType := cloneUintMap(base)
	wrongType[2] = "not-bytes"
	shortRequestID := cloneUintMap(base)
	shortRequestID[2] = bytes.Repeat([]byte{1}, 15)
	wrongVersion := cloneUintMap(base)
	wrongVersion[0] = uint64(2)
	wrongOperation := cloneUintMap(base)
	wrongOperation[1] = "acquire"
	missingArtifact := cloneUintMap(base)
	delete(missingArtifact, 8)
	denyWithArtifact := cloneUintMap(base)
	denyWithArtifact[7] = string(ACPResultStatusPolicyDenied)

	canonicalPayload := mustEncodeCBOR(base)
	nonPreferredVersion := append([]byte{canonicalPayload[0], 0x00, 0x18, 0x01}, canonicalPayload[3:]...)
	tests := []struct {
		name    string
		payload []byte
	}{
		{"duplicate keys", []byte{0xa2, 0x00, 0x01, 0x00, 0x01}},
		{"indefinite map", []byte{0xbf, 0xff}},
		{"non-preferred integer", nonPreferredVersion},
		{"trailing payload bytes", append(append([]byte(nil), canonicalPayload...), 0)},
		{"missing required key", mustEncodeCBOR(missing)},
		{"forbidden unknown key", mustEncodeCBOR(unknown)},
		{"wrong primitive type", mustEncodeCBOR(wrongType)},
		{"invalid request ID size", mustEncodeCBOR(shortRequestID)},
		{"wrong version", mustEncodeCBOR(wrongVersion)},
		{"wrong operation", mustEncodeCBOR(wrongOperation)},
		{"success missing artifact", mustEncodeCBOR(missingArtifact)},
		{"failure carrying artifact", mustEncodeCBOR(denyWithArtifact)},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			wire := mustSignRawACPResult(t, test.payload, private, kid, map[uint64]any{})
			if _, err := ParseVerifiedACPResult(context.Background(), wire, request, resolver, acpTestNow); !errors.Is(err, ErrInvalidAuthority) {
				t.Fatalf("got %v, want invalid authority", err)
			}
		})
	}

	protectedWithoutKID := mustEncodeCBOR(map[uint64]any{1: int64(-8)})
	structure := mustEncodeCBOR([]any{"Signature1", protectedWithoutKID, []byte{}, canonicalPayload})
	missingKIDBody := mustRawCOSEEnvelope(t, protectedWithoutKID, map[uint64]any{}, canonicalPayload, ed25519.Sign(private, structure))
	if _, err := ParseVerifiedACPResult(context.Background(), missingKIDBody, request, resolver, acpTestNow); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("missing protected kid got %v", err)
	}

	protected := mustEncodeCBOR(map[uint64]any{1: int64(-8), 4: kid})
	structure = mustEncodeCBOR([]any{"Signature1", protected, []byte{}, canonicalPayload})
	unprotectedKIDBody := mustRawCOSEEnvelope(t, protected, map[uint64]any{4: kid}, canonicalPayload, ed25519.Sign(private, structure))
	if _, err := ParseVerifiedACPResult(context.Background(), unprotectedKIDBody, request, resolver, acpTestNow); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("unprotected kid got %v", err)
	}

	wrongSignature := mustSignRawACPResult(t, canonicalPayload, private, kid, map[uint64]any{})
	wrongSignature[len(wrongSignature)-1] ^= 0xff
	if _, err := ParseVerifiedACPResult(context.Background(), wrongSignature, request, resolver, acpTestNow); !errors.Is(err, ErrSignatureFailure) {
		t.Fatalf("wrong signature got %v", err)
	}

	wrongKID := []byte{0xff, 0xff, 0xff, 0xff}
	wrongKIDBody := mustSignRawACPResult(t, canonicalPayload, private, wrongKID, map[uint64]any{})
	if _, err := ParseVerifiedACPResult(context.Background(), wrongKIDBody, request, resolver, acpTestNow); !errors.Is(err, ErrUnknownIdentity) {
		t.Fatalf("wrong protected kid got %v", err)
	}
}

func TestACPResultBodyLimitsAreOperationSpecific(t *testing.T) {
	signer, _, _ := mustEnrollmentSigner(t, identity.PurposeDeviceACPRequest, 0xc1, 4)
	acquireValue := validACPRequest(signer.KeyRef())
	acquire, err := SignACPAcquireRequest(context.Background(), acquireValue, signer, acpTestNow)
	if err != nil {
		t.Fatal(err)
	}
	renew, err := SignACPRenewRequest(context.Background(), RenewRequest{AcquireRequest: acquireValue, PreviousGrant: RouteGrantDigest(bytes32ForSeed(0xc2))}, signer, acpTestNow)
	if err != nil {
		t.Fatal(err)
	}
	freshness, err := SignACPFreshnessRequest(context.Background(), FreshnessRequest{
		SourceOperator: acquireValue.Key.SourceOperator, Profile: acquireValue.Key.Profile, DeviceID: acquireValue.Device.ID,
		DeviceGeneration: acquireValue.Device.CredentialGeneration, DeadlineUnix: acquireValue.DeadlineUnix,
	}, RequestID{1}, signer, acpTestNow)
	if err != nil {
		t.Fatal(err)
	}
	private, public, kid := mustRawResultSigner(t, 0xc3)
	_ = private
	purpose, err := ACPResultSigningPurpose()
	if err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct {
		name    string
		request SignedACPRequest
		limit   int
	}{
		{"acquire", acquire, maxACPAcquireResultBodySize},
		{"renew", renew, maxACPRenewResultBodySize},
		{"freshness", freshness, maxACPFreshnessResultBodySize},
	} {
		t.Run(test.name, func(t *testing.T) {
			resolver := mustACPResultResolver(t, test.request, purpose, public, kid)
			if _, err := ParseVerifiedACPResult(context.Background(), make([]byte, test.limit+1), test.request, resolver, acpTestNow); !errors.Is(err, ErrInvalidAuthority) {
				t.Fatalf("got %v, want invalid authority", err)
			}
		})
	}
}

func TestACPResultArtifactPresenceIsStatusBound(t *testing.T) {
	requestSigner, _, _ := mustEnrollmentSigner(t, identity.PurposeDeviceACPRequest, 0xa1, 4)
	request, err := SignACPAcquireRequest(context.Background(), validACPRequest(requestSigner.KeyRef()), requestSigner, acpTestNow)
	if err != nil {
		t.Fatal(err)
	}

	missing := validACPResult(request, ACPResultStatusSuccess)
	missing.Artifact = nil
	if _, err := EncodeACPResultPayload(missing); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("success without artifact got %v", err)
	}
	for _, status := range allACPFailureStatuses() {
		result := validACPResult(request, status)
		result.Artifact = []byte{1}
		if _, err := EncodeACPResultPayload(result); !errors.Is(err, ErrInvalidAuthority) {
			t.Fatalf("%s with artifact got %v", status, err)
		}
	}
}

func FuzzParseVerifiedACPResult(f *testing.F) {
	requestSeed := bytes32ForSeed(0xe1)
	requestPrivate := ed25519.NewKeyFromSeed(requestSeed[:])
	requestPublic := requestPrivate.Public().(ed25519.PublicKey)
	requestRef := identity.KeyRef{
		ID: bytes32ForSeed(0xe2), Purpose: identity.PurposeDeviceACPRequest, Generation: 4,
		Thumbprint: sha256.Sum256(requestPublic),
	}
	requestSigner, err := identity.NewMemorySigner(requestRef, requestPrivate)
	if err != nil {
		f.Fatal(err)
	}
	request, err := SignACPAcquireRequest(context.Background(), validACPRequest(requestRef), requestSigner, acpTestNow)
	if err != nil {
		f.Fatal(err)
	}
	resultSeed := bytes32ForSeed(0xe3)
	resultPrivate := ed25519.NewKeyFromSeed(resultSeed[:])
	resultPublicBytes := resultPrivate.Public().(ed25519.PublicKey)
	var resultPublic [32]byte
	copy(resultPublic[:], resultPublicBytes)
	kid := []byte{0xe4, 0xe4, 0xe4, 0xe4}
	resolver, err := NewStaticIssuerResolver([]IssuerRecord{{
		KID: kid, PublicKey: resultPublic, Purpose: acpResultSigningPurpose,
		Profile: request.Profile(), SourceOperator: request.SourceOperator(), Generation: 1,
		NotBefore: acpTestNow - 1, ExpiresAt: acpTestNow + 10,
	}})
	if err != nil {
		f.Fatal(err)
	}
	protected, err := encodeCBOR(map[uint64]any{1: int64(-8), 4: kid})
	if err != nil {
		f.Fatal(err)
	}
	for _, status := range []ACPResultStatus{ACPResultStatusSuccess, ACPResultStatusPolicyDenied} {
		payload, err := EncodeACPResultPayload(validACPResult(request, status))
		if err != nil {
			f.Fatal(err)
		}
		structure, err := encodeCBOR([]any{"Signature1", protected, []byte{}, payload})
		if err != nil {
			f.Fatal(err)
		}
		validWire, err := buildSign1Envelope(protected, payload, ed25519.Sign(resultPrivate, structure))
		if err != nil {
			f.Fatal(err)
		}
		f.Add(validWire)
	}
	f.Add([]byte{0xd2, 0xff})
	f.Add([]byte{})

	f.Fuzz(func(t *testing.T, wire []byte) {
		if len(wire) > maxACPAcquireResultBodySize+1 {
			t.Skip()
		}
		result, err := ParseVerifiedACPResult(context.Background(), wire, request, resolver, acpTestNow)
		if err != nil {
			return
		}
		artifact := result.Artifact()
		if !validACPResultStatus(result.Status()) || result.AuthorityGeneration() == 0 ||
			(result.Status() == ACPResultStatusSuccess && len(artifact) == 0) ||
			(result.Status() != ACPResultStatusSuccess && len(artifact) != 0) {
			t.Fatal("parser accepted an invalid verified result")
		}
	})
}

func validACPRequest(signingKey identity.KeyRef) AcquireRequest {
	canonical := []byte("frozen-acp-intent-v1")
	digest := RouteIntentDigest(sha256.Sum256(canonical))
	edges := []string{"edge-a", "edge-b"}
	policy := PolicyDigest(bytes32ForSeed(0x15))
	deviceID := bytes32ForSeed(0x16)
	return AcquireRequest{
		Key: AuthorityKey{
			IntentDigest: digest, ServiceDigest: ServiceDigest(bytes32ForSeed(0x11)), SourceOperator: "source.operator",
			SourceEdge: "edge-a", TargetOperator: "target.operator", TargetEdgeSetDigest: targetEdgeSetDigest(edges), Profile: "nbsr-federation-dev-v1",
			Transport: "tcp", Port: 443, DeviceID: deviceID, DeviceGeneration: 3,
			WorkloadDigest: bytes32ForSeed(0x17), WorkloadGeneration: 2, TSGeneration: 5,
			ProofThumbprint: ProofKeyThumbprint(bytes32ForSeed(0x18)), PolicyHash: policy, PolicyGeneration: 6, AuthorityGeneration: 7,
		},
		Intent: RouteIntent{
			Canonical: canonical, Digest: digest, ServiceIdentity: "service.internal", SourceOperator: "source.operator", SourceEdge: "edge-a",
			TargetOperator: "target.operator", TargetEdges: edges, Transport: "tcp", Port: 443, RecordSequence: 9, PolicyHash: policy,
			RouteID: [16]byte{1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16},
			LeaseID: [16]byte{16, 15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1}, ExpiresAt: acpTestNow + 600,
		},
		Device: identity.DeviceIdentity{
			ID: deviceID, SourceOperatorID: "source.operator", CredentialGeneration: 3,
			CredentialNotBefore: acpTestNow - 100, CredentialExpiresAt: acpTestNow + 1000,
			SigningKey: signingKey,
		},
		Workload: &identity.WorkloadPolicyContext{
			SubjectDigest: bytes32ForSeed(0x17), PolicyGeneration: 2,
			CredentialExpiresAt: acpTestNow + 500, PolicyExpiresAt: acpTestNow + 400,
		},
		RequestID:    RequestID{1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16},
		DeadlineUnix: acpTestNow + 30,
	}
}

func cloneACPRequest(request AcquireRequest) AcquireRequest {
	request.Intent.Canonical = append([]byte(nil), request.Intent.Canonical...)
	request.Intent.TargetEdges = append([]string(nil), request.Intent.TargetEdges...)
	if request.Workload != nil {
		workload := *request.Workload
		request.Workload = &workload
	}
	return request
}

func requireExactUintKeys(t *testing.T, value any, want []uint64) map[uint64]any {
	t.Helper()
	fields, ok := value.(map[uint64]any)
	if !ok {
		t.Fatalf("got %T, want map[uint64]any", value)
	}
	got := make([]uint64, 0, len(fields))
	for key := range fields {
		got = append(got, key)
	}
	for left := range got {
		for right := left + 1; right < len(got); right++ {
			if got[right] < got[left] {
				got[left], got[right] = got[right], got[left]
			}
		}
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("keys = %v, want %v", got, want)
	}
	return fields
}

func uintRange(first, last uint64) []uint64 {
	values := make([]uint64, 0, last-first+1)
	for value := first; value <= last; value++ {
		values = append(values, value)
	}
	return values
}

func validACPResult(request SignedACPRequest, status ACPResultStatus) ACPResultPayload {
	result := ACPResultPayload{
		ProtocolVersion:     1,
		Operation:           request.Operation(),
		RequestID:           request.RequestID(),
		RequestDigest:       request.Digest(),
		SourceOperator:      request.SourceOperator(),
		Profile:             request.Profile(),
		AuthorityGeneration: request.AuthorityGeneration(),
		Status:              status,
	}
	if status == ACPResultStatusSuccess {
		result.Artifact = []byte("independently-signed-inner-artifact")
	}
	return result
}

func mustSignACPResult(t *testing.T, result ACPResultPayload, private ed25519.PrivateKey, kid []byte) []byte {
	t.Helper()
	payload, err := EncodeACPResultPayload(result)
	if err != nil {
		t.Fatal(err)
	}
	protected := mustEncodeCBOR(map[uint64]any{1: int64(-8), 4: kid})
	structure := mustEncodeCBOR([]any{"Signature1", protected, []byte{}, payload})
	wire, err := buildSign1Envelope(protected, payload, ed25519.Sign(private, structure))
	if err != nil {
		t.Fatal(err)
	}
	return wire
}

func rawACPResultFields(result ACPResultPayload) map[uint64]any {
	fields := map[uint64]any{
		0: result.ProtocolVersion, 1: string(result.Operation), 2: result.RequestID[:], 3: result.RequestDigest[:],
		4: result.SourceOperator, 5: result.Profile, 6: uint64(result.AuthorityGeneration), 7: string(result.Status),
	}
	if result.Artifact != nil {
		fields[8] = result.Artifact
	}
	return fields
}

func cloneUintMap(value map[uint64]any) map[uint64]any {
	cloned := make(map[uint64]any, len(value))
	for key, field := range value {
		cloned[key] = field
	}
	return cloned
}

func mustSignRawACPResult(t *testing.T, payload []byte, private ed25519.PrivateKey, kid []byte, unprotected map[uint64]any) []byte {
	t.Helper()
	protected := mustEncodeCBOR(map[uint64]any{1: int64(-8), 4: kid})
	structure := mustEncodeCBOR([]any{"Signature1", protected, []byte{}, payload})
	return mustRawCOSEEnvelope(t, protected, unprotected, payload, ed25519.Sign(private, structure))
}

func mustRawCOSEEnvelope(t *testing.T, protected []byte, unprotected map[uint64]any, payload, signature []byte) []byte {
	t.Helper()
	signed := mustEncodeCBOR([]any{protected, unprotected, payload, signature})
	return append([]byte{0xd2}, signed...)
}

func mustACPResultResolver(t *testing.T, request SignedACPRequest, purpose uint16, public [32]byte, kid []byte) ACPResultIssuerResolver {
	t.Helper()
	resolver, err := NewStaticIssuerResolver([]IssuerRecord{{
		KID: kid, PublicKey: public, Purpose: purpose, Profile: request.Profile(), SourceOperator: request.SourceOperator(),
		Generation: 1, NotBefore: acpTestNow - 1, ExpiresAt: acpTestNow + 10,
	}})
	if err != nil {
		t.Fatal(err)
	}
	return resolver
}

func allACPFailureStatuses() []ACPResultStatus {
	return []ACPResultStatus{
		ACPResultStatusInvalidRequest,
		ACPResultStatusUnsupportedVersion,
		ACPResultStatusUnsupportedProfile,
		ACPResultStatusRequestIDConflict,
		ACPResultStatusRequestExpired,
		ACPResultStatusResourceExhausted,
		ACPResultStatusStaleGeneration,
		ACPResultStatusStaleFreshness,
		ACPResultStatusPolicyDenied,
		ACPResultStatusRevoked,
		ACPResultStatusBindingError,
		ACPResultStatusSignatureError,
		ACPResultStatusInternalError,
	}
}

type shortSignatureSigner struct{ identity.Signer }

func (shortSignatureSigner) SignPurposeBound(context.Context, identity.Purpose, []byte) ([]byte, error) {
	return []byte{1}, nil
}

type acpResultIssuerResolverFunc func(context.Context, []byte, string, string, uint64) (IssuerRecord, error)

func (function acpResultIssuerResolverFunc) ResolveACPResultIssuer(ctx context.Context, kid []byte, profile, source string, now uint64) (IssuerRecord, error) {
	return function(ctx, kid, profile, source, now)
}
