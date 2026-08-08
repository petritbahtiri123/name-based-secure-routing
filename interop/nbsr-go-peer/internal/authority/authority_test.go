package authority_test

import (
	"bytes"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/hex"
	"os"
	"path/filepath"
	"testing"

	"nbsr.local/interop/nbsr-go-peer/internal/authority"
	"nbsr.local/interop/nbsr-go-peer/internal/cbor"
)

func repo(parts ...string) string {
	return filepath.Join(append([]string{"..", "..", "..", ".."}, parts...)...)
}
func read(t *testing.T, parts ...string) []byte {
	t.Helper()
	value, err := os.ReadFile(repo(parts...))
	if err != nil {
		t.Fatal(err)
	}
	return value
}
func publicKey(t *testing.T, name string) ed25519.PublicKey {
	t.Helper()
	raw, err := hex.DecodeString(string(bytes.TrimSpace(read(t, "vectors", "core-v0.2", "keys", name))))
	if err != nil {
		t.Fatal(err)
	}
	return ed25519.PublicKey(raw)
}
func repeated(value byte) (result [32]byte) {
	for index := range result {
		result[index] = value
	}
	return
}

func TestRouteGrantAndF75TranscriptVerifyFromFrozenAuthority(t *testing.T) {
	grantWire := read(t, "vectors", "wp8-f75-route-open", "route-grant.cose")
	grant, err := authority.VerifyRouteGrant(
		grantWire,
		publicKey(t, "test-only-route-grant-ed25519-public.hex"),
		[]byte("nbsr-test-route-grant-key"),
		1_893_456_000,
	)
	if err != nil {
		t.Fatalf("verify RouteGrant: %v", err)
	}

	bodyWire := read(t, "vectors", "wp8-f75-route-open", "route-open-body.cbor")
	decoded, err := cbor.DecodeExact(bodyWire, cbor.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	body := decoded.(map[uint64]any)
	var sessionID, requestID [16]byte
	for index := range sessionID {
		sessionID[index] = byte(0x10 + index)
		requestID[index] = byte(index)
	}
	requestID[15] = 0x10
	transcript, err := authority.BuildF75Transcript(sessionID, requestID, "destination.edge", body, grant)
	if err != nil {
		t.Fatalf("build transcript: %v", err)
	}
	want := read(t, "vectors", "wp8-f75-route-open", "transcript.cbor")
	if !bytes.Equal(transcript, want) {
		t.Fatalf("transcript differs\n got %x\nwant %x", transcript, want)
	}
	signature := read(t, "vectors", "wp8-f75-route-open", "signature.bin")
	if !ed25519.Verify(publicKey(t, "test-only-session-ed25519-public.hex"), transcript, signature) {
		t.Fatal("valid F75 signature rejected")
	}
}

func TestRouteGrantAndF75MutationsFailClosed(t *testing.T) {
	grantWire := read(t, "vectors", "wp8-f75-route-open", "route-grant.cose")
	issuer := publicKey(t, "test-only-route-grant-ed25519-public.hex")
	if _, err := authority.VerifyRouteGrant(grantWire, issuer, []byte("wrong-kid"), 1_893_456_000); err == nil {
		t.Fatal("accepted wrong issuer kid")
	}
	mutated := append([]byte(nil), grantWire...)
	mutated[len(mutated)-1] ^= 1
	if _, err := authority.VerifyRouteGrant(mutated, issuer, []byte("nbsr-test-route-grant-key"), 1_893_456_000); err == nil {
		t.Fatal("accepted bad RouteGrant signature")
	}
	if _, err := authority.VerifyRouteGrant(grantWire, issuer, []byte("nbsr-test-route-grant-key"), 1_893_456_301); err == nil {
		t.Fatal("accepted expired RouteGrant")
	}

	transcript := read(t, "vectors", "wp8-f75-route-open", "transcript.cbor")
	signature := read(t, "vectors", "wp8-f75-route-open", "signature.bin")
	transcript[len(transcript)-1] ^= 1
	if ed25519.Verify(publicKey(t, "test-only-session-ed25519-public.hex"), transcript, signature) {
		t.Fatal("accepted mutated F75 transcript")
	}
}

func TestSourceAdmissionAttestationIsIndependentlyAuthenticatedAndBound(t *testing.T) {
	sourcePublic, _ := hex.DecodeString("f80cccdce4ae1c07ae208a2adf99a310ae4207e0306fa0236110b06827bbb8d0")
	grantDigest := sha256.Sum256(read(t, "vectors", "wp8-f75-route-open", "route-grant.cose"))
	contextDigest := sha256.Sum256(read(t, "vectors", "wp8-f75-route-open", "federation-context.cbor"))
	verify := func(wire []byte, routeDigest [32]byte) error {
		return authority.VerifySourceAdmission(wire, ed25519.PublicKey(sourcePublic), []byte("local-source"), authority.SourceAdmissionBinding{
			SourceOperatorID: repeated('S'), DestinationOperatorID: repeated('D'),
			CanonicalName: "service.example", Transport: "tcp", Port: 8443,
			RouteGrantDigest: routeDigest, FederationContextDigest: contextDigest,
			OpenedAt: 1_893_456_000,
		})
	}
	source := read(t, "vectors", "wp8-local-admission", "source.cose")
	if err := verify(source, grantDigest); err != nil {
		t.Fatalf("valid source admission rejected: %v", err)
	}
	if err := verify(read(t, "vectors", "wp8-local-admission", "destination.cose"), grantDigest); err == nil {
		t.Fatal("destination attestation satisfied source admission")
	}
	mutated := append([]byte(nil), source...)
	mutated[len(mutated)-1] ^= 1
	if err := verify(mutated, grantDigest); err == nil {
		t.Fatal("mutated source attestation accepted")
	}
	grantDigest[0] ^= 1
	if err := verify(source, grantDigest); err == nil {
		t.Fatal("source attestation accepted for another RouteGrant")
	}
	contextDigest[0] ^= 1
	grantDigest[0] ^= 1
	if err := authority.VerifySourceAdmission(source, ed25519.PublicKey(sourcePublic), []byte("local-source"), authority.SourceAdmissionBinding{
		SourceOperatorID: repeated('S'), DestinationOperatorID: repeated('D'),
		CanonicalName: "other.example", Transport: "tcp", Port: 8443,
		RouteGrantDigest: grantDigest, FederationContextDigest: contextDigest,
		OpenedAt: 1_893_456_000,
	}); err == nil {
		t.Fatal("source attestation accepted for another service/context")
	}
	contextDigest[0] ^= 1
	if err := authority.VerifySourceAdmission(source, ed25519.PublicKey(sourcePublic), []byte("local-source"), authority.SourceAdmissionBinding{
		SourceOperatorID: repeated('S'), DestinationOperatorID: repeated('D'),
		CanonicalName: "service.example", Transport: "tcp", Port: 8443,
		RouteGrantDigest: grantDigest, FederationContextDigest: contextDigest,
		OpenedAt: 1_893_456_301,
	}); err == nil {
		t.Fatal("expired source admission accepted")
	}
	for _, mutate := range []func(*authority.SourceAdmissionBinding){
		func(binding *authority.SourceAdmissionBinding) { binding.SourceOperatorID[0] ^= 1 },
		func(binding *authority.SourceAdmissionBinding) { binding.DestinationOperatorID[0] ^= 1 },
	} {
		binding := authority.SourceAdmissionBinding{SourceOperatorID: repeated('S'), DestinationOperatorID: repeated('D'), CanonicalName: "service.example", Transport: "tcp", Port: 8443, RouteGrantDigest: grantDigest, FederationContextDigest: contextDigest, OpenedAt: 1_893_456_000}
		mutate(&binding)
		if err := authority.VerifySourceAdmission(source, ed25519.PublicKey(sourcePublic), []byte("local-source"), binding); err == nil {
			t.Fatal("source admission accepted for another operator")
		}
	}
}
