package verifier

import (
	"crypto/ed25519"
	"encoding/hex"
	"strings"
	"testing"

	"nbsr.example/federation-verifier/internal/cbor"
	"nbsr.example/federation-verifier/internal/identity"
)

func validSigner(t *testing.T) (trustedSigner, signerRequirement, []byte, cbor.Value, authorityState) {
	t.Helper()
	seed := make([]byte, ed25519.SeedSize)
	for i := range seed {
		seed[i] = byte(i + 1)
	}
	genesis := ed25519.NewKeyFromSeed(seed).Public().(ed25519.PublicKey)
	seed[0] ^= 0xff
	pub := ed25519.NewKeyFromSeed(seed).Public().(ed25519.PublicKey)
	oid, e := identity.OperatorID(genesis)
	if e != nil {
		t.Fatal(e)
	}
	kid := []byte("trusted-kid")
	subject := hex.EncodeToString(oid[:])
	authority := cbor.Value{Kind: cbor.Map, Map: []cbor.Pair{{Key: cbor.Value{Kind: cbor.Uint, Uint: 1}, Value: cbor.Value{Kind: cbor.Uint, Uint: 1}}, {Key: cbor.Value{Kind: cbor.Uint, Uint: 2}, Value: cbor.Value{Kind: cbor.Bytes, Bytes: oid[:]}}, {Key: cbor.Value{Kind: cbor.Uint, Uint: 3}, Value: cbor.Value{Kind: cbor.Bytes, Bytes: kid}}, {Key: cbor.Value{Kind: cbor.Uint, Uint: 4}, Value: cbor.Value{Kind: cbor.Bytes, Bytes: oid[:]}}}}
	payload := cbor.Value{Kind: cbor.Map, Map: []cbor.Pair{{Key: cbor.Value{Kind: cbor.Uint, Uint: 32}, Value: cbor.Value{Kind: cbor.Bytes, Bytes: oid[:]}}, {Key: cbor.Value{Kind: cbor.Uint, Uint: 37}, Value: authority}}}
	record := trustedSigner{AuthorityClass: 1, ExpiresAt: 1900000001, Generation: 1, GenesisPublicKey: hex.EncodeToString(genesis), KeyLifecycle: 2, KeyPurpose: 1, Kid: hex.EncodeToString(kid), NotBefore: 1700000000, OperatorID: subject, RecordID: "identity-root", Sequence: 1, SigningPublicKey: hex.EncodeToString(pub), SubjectID: subject}
	requirement := signerRequirement{AuthorityClass: 1, KeyPurpose: 1, ObjectClass: "KeyAuthorizationRecord", RequirementID: "key-identity-root", SubjectField: 32}
	return record, requirement, kid, payload, authorityState{EvaluationTime: 1900000000, Generation: 1, Sequence: 1}
}

func TestTrustedSignerAuthorityBinding(t *testing.T) {
	record, requirement, kid, payload, state := validSigner(t)
	if _, reason := validateSigner(record, requirement, "KeyAuthorizationRecord", kid, 1900000000, state, payload); reason != "NONE" {
		t.Fatalf("valid signer: %s", reason)
	}
	tests := []struct {
		name, want string
		mut        func(*trustedSigner)
	}{
		{"operator identity", "ERR_IDENTITY", func(r *trustedSigner) { r.OperatorID = "00" + r.OperatorID[2:] }},
		{"noncanonical uppercase identity", "ERR_IDENTITY", func(r *trustedSigner) { r.OperatorID = strings.ToUpper(r.OperatorID) }},
		{"malformed signing key", "ERR_IDENTITY", func(r *trustedSigner) { r.SigningPublicKey = r.SigningPublicKey[2:] }},
		{"purpose", "ERR_KEY_PURPOSE", func(r *trustedSigner) { r.KeyPurpose = 9 }},
		{"authority class", "ERR_AUTHORITY", func(r *trustedSigner) { r.AuthorityClass = 6 }},
		{"lifecycle", "ERR_KEY_LIFECYCLE", func(r *trustedSigner) { r.KeyLifecycle = 3 }},
		{"revocation", "ERR_REVOKED", func(r *trustedSigner) { r.Revoked = true }},
		{"not yet valid", "ERR_FRESHNESS", func(r *trustedSigner) { r.NotBefore = 1900000001 }},
		{"expired", "ERR_FRESHNESS", func(r *trustedSigner) { r.ExpiresAt = 1900000000 }},
		{"timestamp above profile maximum", "ERR_FRESHNESS", func(r *trustedSigner) { r.ExpiresAt = 253402300800 }},
		{"generation", "ERR_REPLAY", func(r *trustedSigner) { r.Generation = 0 }},
		{"sequence", "ERR_REPLAY", func(r *trustedSigner) { r.Sequence = 0 }},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			mut := record
			tc.mut(&mut)
			if _, got := validateSigner(mut, requirement, "KeyAuthorizationRecord", kid, 1900000000, state, payload); got != tc.want {
				t.Fatalf("got %s want %s", got, tc.want)
			}
		})
	}
}

func TestTrustedSignerRequiresMatchingKidAndObjectClass(t *testing.T) {
	record, requirement, kid, payload, state := validSigner(t)
	if _, got := validateSigner(record, requirement, "DelegationRecord", kid, 1900000000, state, payload); got != "ERR_AUTHORITY" {
		t.Fatalf("class got %s", got)
	}
	if _, got := validateSigner(record, requirement, "KeyAuthorizationRecord", []byte("wrong"), 1900000000, state, payload); got != "ERR_IDENTITY" {
		t.Fatalf("kid got %s", got)
	}
}

func TestTrustedSignerRejectsCrossOperatorSubjectAndStaleAuthorityState(t *testing.T) {
	record, requirement, kid, payload, state := validSigner(t)
	other := payload
	other.Map[0].Value.Bytes = make([]byte, 32)
	if _, got := validateSigner(record, requirement, "KeyAuthorizationRecord", kid, 1900000000, state, other); got != "ERR_IDENTITY" {
		t.Fatalf("cross subject got %s", got)
	}
	state.Sequence = 2
	if _, got := validateSigner(record, requirement, "KeyAuthorizationRecord", kid, 1900000000, state, payload); got != "ERR_REPLAY" {
		t.Fatalf("stale authority got %s", got)
	}
}

func TestTrustedSignerRejectsNestedAuthorityKidMismatch(t *testing.T) {
	record, requirement, kid, payload, state := validSigner(t)
	authority, _ := cbor.Get(payload, 37)
	for i := range authority.Map {
		if authority.Map[i].Key.Uint == 3 {
			authority.Map[i].Value.Bytes = []byte("other-kid")
		}
	}
	for i := range payload.Map {
		if payload.Map[i].Key.Uint == 37 {
			payload.Map[i].Value = authority
		}
	}
	if _, got := validateSigner(record, requirement, "KeyAuthorizationRecord", kid, 1900000000, state, payload); got != "ERR_IDENTITY" {
		t.Fatalf("nested kid got %s", got)
	}
}
