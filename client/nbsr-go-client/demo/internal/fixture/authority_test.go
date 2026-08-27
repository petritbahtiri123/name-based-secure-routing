package fixture

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"errors"
	"strings"
	"testing"

	"nbsr.local/client/nbsr-go-client/internal/authority"
	"nbsr.local/client/nbsr-go-client/internal/corestate"
	"nbsr.local/client/nbsr-go-client/internal/session"
)

func TestRouteIssuerTrustIsPublicOnlyAndDefensivelyCopied(t *testing.T) {
	server, err := Start(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(server.Close)
	kid, public := server.RouteIssuerTrust()
	if len(kid) == 0 || public == ([32]byte{}) {
		t.Fatal("missing public RouteGrant issuer trust")
	}
	kid[0] ^= 1
	again, _ := server.RouteIssuerTrust()
	if bytes.Equal(kid, again) {
		t.Fatal("caller mutated fixture issuer KID")
	}
}

func TestAuthorityFixtureSignsOnlyExactCatalogRequest(t *testing.T) {
	server, err := Start(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(server.Close)
	request := server.AcquireRequest()
	if request.Key.ServiceDigest != authority.ServiceDigest([32]byte{0x07, 0xed, 0x4f, 0xf0, 0xa2, 0x36, 0x5c, 0xc9, 0x16, 0x49, 0xcf, 0x8a, 0x94, 0x05, 0xd2, 0xf1, 0xcd, 0x12, 0x61, 0xfc, 0xb2, 0x01, 0xa9, 0x22, 0xac, 0xdb, 0xf4, 0xf4, 0xbc, 0xf2, 0x13, 0xb5}) {
		t.Fatal("AuthorityKey is not derived from the canonical demo service name")
	}
}

func TestAuthorityFixtureAcceptsMappingOwnedRuntimeRouteAndActualProof(t *testing.T) {
	request, _, _, _, err := makeRequest()
	if err != nil {
		t.Fatal(err)
	}
	request.Intent.Port = 9443
	request.Intent.RecordSequence = 9
	request.Intent.Canonical = []byte("runtime route intent")
	request.Intent.Digest = authority.RouteIntentDigest(sha256.Sum256(request.Intent.Canonical))
	request.Intent.PolicyHash = authority.PolicyDigest(sha256.Sum256([]byte("runtime-policy")))
	request.Intent.RouteID = [16]byte{7}
	request.Intent.LeaseID = [16]byte{8}
	public := ed25519.NewKeyFromSeed(bytes32(4)).Public().(ed25519.PublicKey)
	thumbprint := sha256.Sum256(public)
	request.Key.IntentDigest = request.Intent.Digest
	request.Key.ServiceDigest = authority.ServiceDigest(sha256.Sum256([]byte("service-a.nbsr.test")))
	request.Key.Transport, request.Key.Port, request.Key.PolicyHash = request.Intent.Transport, request.Intent.Port, request.Intent.PolicyHash
	request.Key.TSGeneration, request.Key.ProofThumbprint = 5, thumbprint
	view := session.DestinationRouteView{ServiceIdentity: request.Intent.ServiceIdentity, ServiceDigest: corestate.ServiceDigest(request.Key.ServiceDigest), Intent: request.Intent, ProofThumbprint: thumbprint}
	copy(view.ProofPublicKey[:], public)
	server, err := Start(t.TempDir(), WithRouteInputs(request, view))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(server.Close)
	got := server.AcquireRequest()
	if got.Key.TSGeneration != 5 || got.Key.ProofThumbprint != thumbprint || got.Key.Port != 9443 || got.Intent.RecordSequence != 9 {
		t.Fatalf("runtime request = %+v", got)
	}
	var nonce [32]byte
	for index := range nonce {
		nonce[index] = byte(0x80 + index)
	}
	publicConfig, err := server.PublicRuntimeAdmissionConfig(nonce)
	if err != nil {
		t.Fatal(err)
	}
	for _, required := range []string{
		"NBSR-RUNTIME-ADMISSION-v1\n", "service_identity=nbsr-demo-service-a-v1\n",
		"port=9443\n", "record_sequence=9\n",
		"issuer_kid=nbsr-demo-route-grant-v1\n",
	} {
		if !strings.Contains(string(publicConfig), required) {
			t.Fatalf("public admission config missing %q", required)
		}
	}
	if strings.Contains(string(publicConfig), "ts_generation=") {
		t.Fatal("unenforceable ts_generation remained in destination config")
	}
	for _, forbidden := range []string{"private_key", "executable", "backend", "origin_endpoint"} {
		if strings.Contains(strings.ToLower(string(publicConfig)), forbidden) {
			t.Fatalf("public admission config exposed %q", forbidden)
		}
	}
}

func bytes32(seed byte) []byte {
	value := make([]byte, ed25519.SeedSize)
	for index := range value {
		value[index] = seed
	}
	return value
}

func bytes32Value(seed byte) (value [32]byte) {
	for index := range value {
		value[index] = seed
	}
	return value
}

func TestAuthorityFixtureRejectsUnknownServiceAndCancellation(t *testing.T) {
	server, err := Start(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(server.Close)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err := authority.SignDemoRouteGrant(ctx, authority.DemoRouteGrantInput{}, nil); !errors.Is(err, context.Canceled) {
		t.Fatalf("cancellation = %v", err)
	}
}
