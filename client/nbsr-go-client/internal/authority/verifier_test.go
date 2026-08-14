package authority

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"os"
	"path/filepath"
	"testing"
)

const frozenRouteGrantKID = "nbsr-test-route-grant-key"

func TestVerifyRouteGrantSealsFrozenFixture(t *testing.T) {
	candidate, verification, resolver := validFrozenGrantCase(t)
	got, err := mustVerifier(t, resolver).VerifyRouteGrant(context.Background(), candidate, verification)
	if err != nil {
		t.Fatal(err)
	}
	if got.GrantDigest() != RouteGrantDigest(sha256.Sum256(candidate.ExactRouteGrant)) {
		t.Fatal("digest")
	}
	if got.Key() != verification.Key {
		t.Fatal("key")
	}
}

func TestVerifiedAuthorityZeroValueRejected(t *testing.T) {
	if (VerifiedAuthority{}).valid() {
		t.Fatal("zero verified authority is valid")
	}
}

func TestVerifyRouteGrantRejectsSignatureAndIssuerTrustMutations(t *testing.T) {
	candidate, verification, resolver := validFrozenGrantCase(t)
	verifier := mustVerifier(t, resolver)

	mutated := candidate
	mutated.ExactRouteGrant = append([]byte(nil), candidate.ExactRouteGrant...)
	mutated.ExactRouteGrant[len(mutated.ExactRouteGrant)-1] ^= 1
	if _, err := verifier.VerifyRouteGrant(context.Background(), mutated, verification); !errors.Is(err, ErrSignatureFailure) {
		t.Fatalf("bad signature error = %v, want ErrSignatureFailure", err)
	}

	for _, mutation := range []struct {
		name   string
		mutate func(*IssuerRecord)
		want   error
	}{
		{"wrong purpose", func(record *IssuerRecord) { record.Purpose++ }, ErrInvalidKeyPurpose},
		{"wrong profile", func(record *IssuerRecord) { record.Profile = "other-profile" }, ErrUnknownIdentity},
		{"wrong source operator", func(record *IssuerRecord) { record.SourceOperator = "other.operator" }, ErrUnknownIdentity},
		{"revoked", func(record *IssuerRecord) { record.Revoked = true }, ErrRevoked},
		{"expired", func(record *IssuerRecord) { record.ExpiresAt = verification.NowUnix }, ErrExpired},
	} {
		t.Run(mutation.name, func(t *testing.T) {
			record := frozenIssuer(t)
			mutation.mutate(&record)
			issuerResolver, err := NewStaticIssuerResolver([]IssuerRecord{record})
			if err != nil {
				t.Fatal(err)
			}
			if _, err := mustVerifier(t, issuerResolver).VerifyRouteGrant(context.Background(), candidate, verification); !errors.Is(err, mutation.want) {
				t.Fatalf("error = %v, want %v", err, mutation.want)
			}
		})
	}
}

func TestVerifyRouteGrantRejectsEveryBoundField(t *testing.T) {
	candidate, verification, resolver := validFrozenGrantCase(t)
	verifier := mustVerifier(t, resolver)
	for _, mutation := range []struct {
		name   string
		mutate func(*VerificationContext)
	}{
		{"service digest", func(value *VerificationContext) { value.Key.ServiceDigest[0] ^= 1 }},
		{"source operator", func(value *VerificationContext) { value.Key.SourceOperator = "other.operator" }},
		{"source edge", func(value *VerificationContext) { value.Key.SourceEdge = "other.edge" }},
		{"target operator", func(value *VerificationContext) { value.Key.TargetOperator = "other.operator" }},
		{"target edges", func(value *VerificationContext) { value.Intent.TargetEdges = []string{"other.edge"} }},
		{"transport", func(value *VerificationContext) { value.Intent.Transport = "udp"; value.Key.Transport = "udp" }},
		{"port", func(value *VerificationContext) { value.Intent.Port = 443; value.Key.Port = 443 }},
		{"route id", func(value *VerificationContext) { value.Intent.RouteID[0] ^= 1 }},
		{"lease id", func(value *VerificationContext) { value.Intent.LeaseID[0] ^= 1 }},
		{"record sequence", func(value *VerificationContext) { value.Intent.RecordSequence++ }},
		{"policy", func(value *VerificationContext) { value.Intent.PolicyHash[0] ^= 1; value.Key.PolicyHash[0] ^= 1 }},
		{"proof thumbprint", func(value *VerificationContext) { value.Key.ProofThumbprint[0] ^= 1 }},
		{"zero TS generation", func(value *VerificationContext) { value.Key.TSGeneration = 0 }},
		{"stale authority generation", func(value *VerificationContext) { value.Key.AuthorityGeneration++ }},
		{"wrong checkpoint relation", func(value *VerificationContext) { value.Checkpoint.Digest[0] ^= 1 }},
		{"grant expiry end exclusive", func(value *VerificationContext) { value.NowUnix = value.Intent.ExpiresAt }},
	} {
		t.Run(mutation.name, func(t *testing.T) {
			changed := verification
			changed.Intent.TargetEdges = append([]string(nil), verification.Intent.TargetEdges...)
			mutation.mutate(&changed)
			if _, err := verifier.VerifyRouteGrant(context.Background(), candidate, changed); err == nil {
				t.Fatal("accepted mismatched RouteGrant binding")
			}
		})
	}
}

func TestStaticIssuerResolverCopiesBoundedTrustRecords(t *testing.T) {
	record := frozenIssuer(t)
	resolver, err := NewStaticIssuerResolver([]IssuerRecord{record})
	if err != nil {
		t.Fatal(err)
	}
	record.KID[0] ^= 1
	candidate, verification, _ := validFrozenGrantCase(t)
	if _, err := mustVerifier(t, resolver).VerifyRouteGrant(context.Background(), candidate, verification); err != nil {
		t.Fatalf("copied trust record no longer resolves: %v", err)
	}
	if _, err := NewStaticIssuerResolver([]IssuerRecord{{KID: []byte("x"), Purpose: 1, Profile: "profile", SourceOperator: "source", Generation: 1, NotBefore: 1, ExpiresAt: 2}}); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("zero public key error = %v, want ErrInvalidAuthority", err)
	}
}

func TestCBORRejectsFrozenStructuralInvalidVectors(t *testing.T) {
	for _, name := range []string{
		"cbor-duplicate-map-key.bin", "cbor-float.bin", "cbor-indefinite-map.bin", "cbor-nonpreferred-integer.bin",
		"cbor-over-total-bytes.bin", "cbor-trailing-bytes.bin", "cbor-truncated.bin", "cbor-unsupported-tag.bin", "cbor-wrong-map-order.bin",
	} {
		t.Run(name, func(t *testing.T) {
			if _, err := decodeCBORExact(readRepo(t, "vectors", "core-v0.2", "artifacts", "invalid", "structural", name), defaultCBORLimits()); err == nil {
				t.Fatal("accepted frozen invalid CBOR")
			}
		})
	}
}

func TestRouteGrantTargetEdgeComparisonCannotAliasEmbeddedNUL(t *testing.T) {
	if sameStrings([]string{"destination\x00edge", "z"}, []string{"destination", "edge\x00z"}) {
		t.Fatal("embedded NUL aliases distinct target-edge sets")
	}
}

func validFrozenGrantCase(t *testing.T) (ProviderGrant, VerificationContext, IssuerResolver) {
	t.Helper()
	issuer := frozenIssuer(t)
	resolver, err := NewStaticIssuerResolver([]IssuerRecord{issuer})
	if err != nil {
		t.Fatal(err)
	}
	canonical := []byte("frozen route intent")
	intent := RouteIntent{
		Canonical: canonical, Digest: RouteIntentDigest(sha256.Sum256(canonical)), ServiceIdentity: "service.example",
		SourceOperator: "source.operator", SourceEdge: "source.edge", TargetOperator: "destination.operator", TargetEdges: []string{"destination.edge"},
		Transport: "tcp", Port: 8443, RecordSequence: 42, PolicyHash: mustHex32(t, "09fe3b1c85499949da222dd4e2a460f594aee825f444a72258d2f1797bf1143f"),
		RouteID: mustHex16(t, "202122232425262728292a2b2c2d2e2f"), LeaseID: mustHex16(t, "303132333435363738393a3b3c3d3e3f"), ExpiresAt: 1_893_456_300,
	}
	key := AuthorityKey{
		IntentDigest: intent.Digest, ServiceDigest: mustHex32(t, "2a3839a8073dbaa80b49c970615a1e2585e1c86e86f03b3fc674db92314bae92"),
		SourceOperator: intent.SourceOperator, SourceEdge: intent.SourceEdge, TargetOperator: intent.TargetOperator, TargetEdgeSetDigest: targetEdgeSetDigest(intent.TargetEdges),
		Profile: "nbsr-federation-dev-v1", Transport: intent.Transport, Port: intent.Port, DeviceID: [32]byte{1}, DeviceGeneration: 1,
		TSGeneration: 2, ProofThumbprint: ProofKeyThumbprint(mustHex32(t, "39f713d0a644253f04529421b9f51b9b08979d08295959c4f3990ee617f5139f")),
		PolicyHash: intent.PolicyHash, PolicyGeneration: 3, AuthorityGeneration: 7,
	}
	checkpoint := CheckpointClaims{SourceOperator: key.SourceOperator, Profile: key.Profile, Generation: key.AuthorityGeneration, IssuedAt: 1_893_456_000, FreshUntil: intent.ExpiresAt, Digest: CheckpointDigest{0xa5}}
	return ProviderGrant{ExactRouteGrant: readRepo(t, "vectors", "core-v0.2", "artifacts", "valid", "objects", "route-grant-sign1.cose"), Profile: key.Profile, AuthorityGeneration: key.AuthorityGeneration, Checkpoint: checkpoint.Digest}, VerificationContext{Key: key, Intent: intent, Checkpoint: checkpoint, NowUnix: 1_893_456_000}, resolver
}

func frozenIssuer(t *testing.T) IssuerRecord {
	t.Helper()
	var publicKey [32]byte
	decoded, err := hex.DecodeString(string(bytes.TrimSpace(readRepo(t, "vectors", "core-v0.2", "keys", "test-only-route-grant-ed25519-public.hex"))))
	if err != nil || len(decoded) != len(publicKey) {
		t.Fatal("invalid frozen issuer key")
	}
	copy(publicKey[:], decoded)
	return IssuerRecord{KID: []byte(frozenRouteGrantKID), PublicKey: publicKey, Purpose: 1, Profile: "nbsr-federation-dev-v1", SourceOperator: "source.operator", Generation: 7, NotBefore: 1_893_455_000, ExpiresAt: 1_893_457_000}
}

func mustVerifier(t *testing.T, resolver IssuerResolver) *Verifier {
	t.Helper()
	verifier, err := NewVerifier(resolver)
	if err != nil {
		t.Fatal(err)
	}
	return verifier
}

func readRepo(t *testing.T, parts ...string) []byte {
	t.Helper()
	value, err := os.ReadFile(filepath.Join(append([]string{"..", "..", "..", ".."}, parts...)...))
	if err != nil {
		t.Fatal(err)
	}
	return value
}

func mustHex16(t *testing.T, value string) (result [16]byte) {
	t.Helper()
	raw, err := hex.DecodeString(value)
	if err != nil || len(raw) != len(result) {
		t.Fatal("invalid test literal")
	}
	copy(result[:], raw)
	return result
}

func mustHex32(t *testing.T, value string) (result [32]byte) {
	t.Helper()
	raw, err := hex.DecodeString(value)
	if err != nil || len(raw) != len(result) {
		t.Fatal("invalid test literal")
	}
	copy(result[:], raw)
	return result
}
