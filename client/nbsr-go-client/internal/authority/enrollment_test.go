package authority

import (
	"bytes"
	"encoding/hex"
	"errors"
	"testing"

	"nbsr.local/client/nbsr-go-client/internal/identity"
)

func TestEnrollmentRequestRoundTripIsDeterministic(t *testing.T) {
	request := validEnrollmentRequestPayload()
	requestPayload, err := EncodeEnrollmentRequestPayload(request)
	if err != nil {
		t.Fatal(err)
	}
	parsed, canonical, err := ParseEnrollmentRequest(enrollmentSign1(requestPayload))
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(requestPayload, canonical) {
		t.Fatalf("nondeterministic encoding: %x != %x", requestPayload, canonical)
	}
	if parsed != request {
		t.Fatalf("parsed request mismatch")
	}
}

func TestEnrollmentResultRoundTripIsDeterministicAndStatusAware(t *testing.T) {
	requestPayload, err := EncodeEnrollmentRequestPayload(validEnrollmentRequestPayload())
	if err != nil {
		t.Fatal(err)
	}
	for _, status := range []EnrollmentStatus{
		EnrollmentStatusAccepted,
		EnrollmentStatusRejected,
		EnrollmentStatusInvalid,
		EnrollmentStatusRequestConflict,
		EnrollmentStatusExpired,
	} {
		t.Run(string(status), func(t *testing.T) {
			resultPayload := validEnrollmentResultPayload(status, requestPayload)
			resultWirePayload, err := EncodeEnrollmentResultPayload(resultPayload)
			if err != nil {
				t.Fatal(err)
			}
			purpose, err := EnrollmentResultSigningPurpose()
			if err != nil {
				t.Fatal(err)
			}
			parsed, canonical, err := ParseEnrollmentResult(enrollmentResultSign1(resultWirePayload), purpose)
			if err != nil {
				t.Fatal(err)
			}
			if !bytes.Equal(resultWirePayload, canonical) {
				t.Fatalf("nondeterministic encoding: %x != %x", resultWirePayload, canonical)
			}
			if parsed.Status != status {
				t.Fatalf("status mismatch: got %q", parsed.Status)
			}
			if status == EnrollmentStatusAccepted {
				if parsed.DeviceIdentity == nil {
					t.Fatal("accepted result missing device identity")
				}
			} else if parsed.DeviceIdentity != nil {
				t.Fatal("non-success result includes device identity")
			}
		})
	}
}

func TestEnrollmentResultPurposeBindingRejectsWrongPurpose(t *testing.T) {
	requestPayload, err := EncodeEnrollmentRequestPayload(validEnrollmentRequestPayload())
	if err != nil {
		t.Fatal(err)
	}
	resultPayload := validEnrollmentResultPayload(EnrollmentStatusAccepted, requestPayload)
	resultWirePayload, err := EncodeEnrollmentResultPayload(resultPayload)
	if err != nil {
		t.Fatal(err)
	}
	resultWire := enrollmentResultSign1(resultWirePayload)
	purpose, err := EnrollmentResultSigningPurpose()
	if err != nil {
		t.Fatal(err)
	}
	if _, _, err := ParseEnrollmentResult(resultWire, purpose); err != nil {
		t.Fatalf("resolved purpose 16 should parse: %v", err)
	}
	if _, _, err := ParseEnrollmentResult(resultWire, 15); !errors.Is(err, ErrInvalidKeyPurpose) {
		t.Fatalf("ACP result purpose accepted unexpectedly: %v", err)
	}
	if _, _, err := ParseEnrollmentResult(resultWire, 77); !errors.Is(err, ErrInvalidKeyPurpose) {
		t.Fatalf("unrelated purpose accepted unexpectedly: %v", err)
	}
}

func TestEnrollmentResultSigningPurposeIs16FromRegistry(t *testing.T) {
	purpose, err := EnrollmentResultSigningPurpose()
	if err != nil {
		t.Fatal(err)
	}
	if purpose != 16 {
		t.Fatalf("unexpected purpose value: got %d want 16", purpose)
	}
	if acp, err := resolveFederationKeyPurpose("ACP_RESULT_SIGNING"); err != nil || acp != 15 {
		t.Fatalf("unexpected ACP_RESULT_SIGNING purpose resolution: got %d err %v", acp, err)
	}
}

func TestEnrollmentResultBindingRequiresExactRequest(t *testing.T) {
	requestPayload, err := EncodeEnrollmentRequestPayload(validEnrollmentRequestPayload())
	if err != nil {
		t.Fatal(err)
	}
	requestIDWire := validEnrollmentRequestPayload().RequestID

	parsedRequest, canonicalRequest, err := ParseEnrollmentRequest(enrollmentSign1(requestPayload))
	if err != nil {
		t.Fatal(err)
	}
	resultPayload := validEnrollmentResultPayload(EnrollmentStatusAccepted, requestPayload)
	resultWirePayload, err := EncodeEnrollmentResultPayload(resultPayload)
	if err != nil {
		t.Fatal(err)
	}
	purpose, err := EnrollmentResultSigningPurpose()
	if err != nil {
		t.Fatal(err)
	}
	parsedResult, _, err := ParseEnrollmentResult(enrollmentResultSign1(resultWirePayload), purpose)
	if err != nil {
		t.Fatal(err)
	}
	if err := ValidateEnrollmentResultBinding(parsedResult, parsedRequest, canonicalRequest); err != nil {
		t.Fatal(err)
	}

	mismatchedRequestID := parsedRequest
	mismatchedRequestID.RequestID = requestIDWire
	mismatchedRequestID.RequestID[0] ^= 0xff
	if err := ValidateEnrollmentResultBinding(parsedResult, mismatchedRequestID, canonicalRequest); !errors.Is(err, ErrBindingMismatch) {
		t.Fatalf("expected request-id mismatch failure, got %v", err)
	}

	mutatedPayload := append([]byte(nil), canonicalRequest...)
	mutatedPayload[0] ^= 0xff
	if err := ValidateEnrollmentResultBinding(parsedResult, parsedRequest, mutatedPayload); !errors.Is(err, ErrBindingMismatch) {
		t.Fatalf("expected digest mismatch failure, got %v", err)
	}
}

func TestEnrollmentRequestRejectsMalformedPayloads(t *testing.T) {
	requestPayload, err := EncodeEnrollmentRequestPayload(validEnrollmentRequestPayload())
	if err != nil {
		t.Fatal(err)
	}
	rawMap := decodeEnrollmentMap(t, requestPayload)

	cases := []struct {
		name   string
		mutate func(map[uint64]any) bool
	}{
		{"missing required field", func(fields map[uint64]any) bool {
			delete(fields, 4)
			return true
		}},
		{"extra field", func(fields map[uint64]any) bool {
			fields[6] = uint64(7)
			return true
		}},
		{"wrong protocol version", func(fields map[uint64]any) bool {
			fields[0] = uint64(2)
			return true
		}},
		{"wrong request-id type", func(fields map[uint64]any) bool {
			fields[1] = uint64(1)
			return true
		}},
		{"bad source operator", func(fields map[uint64]any) bool {
			fields[3] = "bad_source//op"
			return true
		}},
		{"deadline overflow", func(fields map[uint64]any) bool {
			fields[2] = maxUnixTime + 1
			return true
		}},
		{"malformed key purpose", func(fields map[uint64]any) bool {
			device := cloneEnrollmentMap(rawMap[5].(map[uint64]any))
			device[2] = uint64(identity.PurposeTSProof)
			fields[5] = device
			return true
		}},
		{"malformed key public key", func(fields map[uint64]any) bool {
			device := cloneEnrollmentMap(rawMap[5].(map[uint64]any))
			device[0] = []byte{1, 2, 3}
			fields[5] = device
			return true
		}},
	}

	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			fields := cloneEnrollmentMap(rawMap)
			if !testCase.mutate(fields) {
				t.Fatal("mutation no-op")
			}
			payload := encodeCBORValueForTest(t, fields)
			if _, _, err := ParseEnrollmentRequest(enrollmentSign1(payload)); !errors.Is(err, ErrInvalidAuthority) {
				t.Fatalf("malformed request accepted: %v", err)
			}
		})
	}

	invalid := append([]byte{0xd2}, readRepo(t, "vectors", "core-v0.2", "artifacts", "invalid", "structural", "cbor-duplicate-map-key.bin")...)
	if _, _, err := ParseEnrollmentRequest(invalid); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatal("duplicate-map-key request accepted")
	}
	invalid = append([]byte{0xd2}, readRepo(t, "vectors", "core-v0.2", "artifacts", "invalid", "structural", "cbor-nonpreferred-integer.bin")...)
	if _, _, err := ParseEnrollmentRequest(invalid); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatal("noncanonical request accepted")
	}

	oversized := make([]byte, maxEnrollmentRequestBodySize+1)
	if _, _, err := ParseEnrollmentRequest(oversized); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatal("oversized request accepted")
	}
	requestWire := enrollmentSign1(requestPayload)
	if _, _, err := ParseEnrollmentRequest(requestWire[:len(requestWire)-1]); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatal("truncated request accepted")
	}
}

func TestEnrollmentResultRejectsMalformedPayloads(t *testing.T) {
	requestPayload, err := EncodeEnrollmentRequestPayload(validEnrollmentRequestPayload())
	if err != nil {
		t.Fatal(err)
	}
	resultPayload := validEnrollmentResultPayload(EnrollmentStatusAccepted, requestPayload)
	encoded, err := EncodeEnrollmentResultPayload(resultPayload)
	if err != nil {
		t.Fatal(err)
	}
	purpose, err := EnrollmentResultSigningPurpose()
	if err != nil {
		t.Fatal(err)
	}
	rawMap := decodeEnrollmentMap(t, encoded)

	for _, testCase := range []struct {
		name   string
		mutate func(map[uint64]any) bool
	}{
		{"missing required status", func(fields map[uint64]any) bool {
			delete(fields, 3)
			return true
		}},
		{"extra trailing field", func(fields map[uint64]any) bool {
			fields[5] = uint64(9)
			return true
		}},
		{"unknown status", func(fields map[uint64]any) bool {
			fields[3] = "ENROLLMENT_UNKNOWN"
			return true
		}},
		{"accepted without identity", func(fields map[uint64]any) bool {
			delete(fields, 4)
			return true
		}},
		{"invalid status identity combination", func(fields map[uint64]any) bool {
			fields[3] = string(EnrollmentStatusRejected)
			return true
		}},
		{"invalid identity expiry ordering", func(fields map[uint64]any) bool {
			id := fields[4].(map[uint64]any)
			id[4] = uint64(1)
			id[3] = uint64(2)
			fields[4] = id
			fields[3] = string(EnrollmentStatusAccepted)
			return true
		}},
		{"invalid request digest length", func(fields map[uint64]any) bool {
			fields[2] = []byte{1, 2, 3}
			return true
		}},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			fields := cloneEnrollmentMap(rawMap)
			if !testCase.mutate(fields) {
				t.Fatal("mutation no-op")
			}
			payload := encodeCBORValueForTest(t, fields)
			if _, _, err := ParseEnrollmentResult(enrollmentResultSign1(payload), purpose); !errors.Is(err, ErrInvalidAuthority) {
				t.Fatalf("malformed result accepted: %v", err)
			}
		})
	}

	invalid := append([]byte{0xd2}, readRepo(t, "vectors", "core-v0.2", "artifacts", "invalid", "structural", "cbor-duplicate-map-key.bin")...)
	if _, _, err := ParseEnrollmentResult(invalid, purpose); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatal("duplicate-map-key result accepted")
	}
	invalid = append([]byte{0xd2}, readRepo(t, "vectors", "core-v0.2", "artifacts", "invalid", "structural", "cbor-nonpreferred-integer.bin")...)
	if _, _, err := ParseEnrollmentResult(invalid, purpose); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatal("noncanonical result accepted")
	}

	oversized := make([]byte, maxEnrollmentResultBodySize+1)
	if _, _, err := ParseEnrollmentResult(oversized, purpose); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatal("oversized result accepted")
	}
	truncated := enrollmentResultSign1(encoded)
	if _, _, err := ParseEnrollmentResult(truncated[:len(truncated)-1], purpose); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatal("truncated result accepted")
	}
}

func decodeEnrollmentMap(t *testing.T, payload []byte) map[uint64]any {
	t.Helper()
	raw, err := decodeCBORExact(payload, defaultCBORLimits())
	if err != nil {
		t.Fatal(err)
	}
	fields, ok := raw.(map[uint64]any)
	if !ok {
		t.Fatalf("expected map got %T", raw)
	}
	return fields
}

func cloneEnrollmentMap(source map[uint64]any) map[uint64]any {
	cloned := make(map[uint64]any, len(source))
	for key, value := range source {
		if nested, ok := value.(map[uint64]any); ok {
			cloned[key] = cloneEnrollmentMap(nested)
		} else {
			cloned[key] = value
		}
	}
	return cloned
}

func encodeCBORValueForTest(t *testing.T, value any) []byte {
	t.Helper()
	encoded, err := encodeCBOR(value)
	if err != nil {
		t.Fatal(err)
	}
	return encoded
}

func validEnrollmentRequestPayload() EnrollmentRequestPayload {
	return EnrollmentRequestPayload{
		ProtocolVersion: 1,
		RequestID:       RequestID{1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16},
		DeadlineUnix:    1_893_456_001,
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
	result := EnrollmentResultPayload{
		ProtocolVersion: 1,
		RequestID:       validEnrollmentRequestPayload().RequestID,
		RequestDigest:   EnrollmentRequestDigest(requestPayload),
		Status:          status,
	}
	if status == EnrollmentStatusAccepted {
		result.DeviceIdentity = &identity.DeviceIdentity{
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
	return result
}

func enrollmentSign1(payload []byte) []byte {
	return testSign1Wire(enrollmentProtectedHeader(), []byte{0xa0}, testByteString(payload))
}

func enrollmentResultSign1(payload []byte) []byte {
	return testSign1Wire(enrollmentProtectedHeader(), []byte{0xa0}, testByteString(payload))
}

func enrollmentProtectedHeader() []byte {
	return mustEncodeCBOR(map[uint64]any{1: int64(-8), 4: []byte("enroll-kid")})
}
func mustHex32Literal(value string) (result [32]byte) {
	raw, err := hex.DecodeString(value)
	if err != nil || len(raw) != len(result) {
		panic("invalid hex literal")
	}
	copy(result[:], raw)
	return result
}

func mustEncodeCBOR(value any) []byte {
	encoded, err := encodeCBOR(value)
	if err != nil {
		panic(err)
	}
	return encoded
}
