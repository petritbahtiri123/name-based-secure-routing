package wirepeer

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"io"
	"os"
	"path/filepath"
	"reflect"
	"testing"
)

type validatedClientBoundary interface {
	SendEnvelope(Envelope) error
	SendRawControl([]byte) error
	ReceiveEnvelope() (Envelope, error)
	ExportKeyingMaterial([]byte) ([]byte, error)
	OpenApplication(context.Context) (ApplicationStream, error)
	RefillStreamCredits(context.Context, [16]byte, uint64) error
	Identity() string
	Close() error
}

func TestBuildRouteOpenUsesCanonicalGrantTranscriptAndActualProofSigner(t *testing.T) {
	root := filepath.Join("..", "..", "..", "vectors")
	exactGrant, err := os.ReadFile(filepath.Join(root, "wp8-f75-route-open", "route-grant.cose"))
	if err != nil {
		t.Fatal(err)
	}
	issuer := readHex32(t, filepath.Join(root, "core-v0.2", "keys", "test-only-route-grant-ed25519-public.hex"))
	seed := readHex32(t, filepath.Join(root, "core-v0.2", "keys", "test-only-session-ed25519-seed.hex"))
	private := ed25519.NewKeyFromSeed(seed[:])
	var proofPublic [32]byte
	copy(proofPublic[:], private.Public().(ed25519.PublicKey))
	contextWire, err := os.ReadFile(filepath.Join(root, "wp8-f75-route-open", "federation-context.cbor"))
	if err != nil {
		t.Fatal(err)
	}
	transport := &TransportSession{config: TransportSessionConfig{SessionID: sequence16(0x10), DestinationEdge: "destination.edge", ProofPublicKey: proofPublic}, edgeNonce: sequence32(0x80)}
	envelope, grant, err := buildRouteOpen(t.Context(), transport, ServiceChannelConfig{
		RequestID: [16]byte{0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16}, ChannelID: sequence16(0x40),
		ExactRouteGrant: exactGrant, IssuerPublicKey: issuer, IssuerKID: []byte("nbsr-test-route-grant-key"),
		OpenedAt: 1_893_456_000, FederationContextDigest: sha256.Sum256(contextWire), Federated: true,
		SignProof: func(_ context.Context, message []byte) ([]byte, error) { return ed25519.Sign(private, message), nil },
	})
	if err != nil {
		t.Fatal(err)
	}
	if envelope.MessageType != RouteOpen || envelope.Body[0] != uint64(2) || envelope.Body[4] != "tcp" || envelope.Body[5] != uint64(8443) {
		t.Fatalf("route envelope = %#v", envelope)
	}
	if grant.ServiceIdentity != "service.example" || !ed25519.Verify(private.Public().(ed25519.PublicKey), grant.ProofTranscript, envelope.Body[7].([]byte)) {
		t.Fatal("ROUTE_OPEN did not use the actual proof signer")
	}
}

func readHex32(t *testing.T, path string) [32]byte {
	t.Helper()
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	decoded, err := hex.DecodeString(string(bytes.TrimSpace(raw)))
	if err != nil || len(decoded) != 32 {
		t.Fatalf("decode %s: %v", path, err)
	}
	var value [32]byte
	copy(value[:], decoded)
	return value
}

func sequence16(start byte) (value [16]byte) {
	for index := range value {
		value[index] = start + byte(index)
	}
	return value
}

func sequence32(start byte) (value [32]byte) {
	for index := range value {
		value[index] = start + byte(index)
	}
	return value
}

var _ validatedClientBoundary = (*Client)(nil)
var _ io.ReadWriteCloser = (ApplicationStream)(nil)

func TestDialTransportSessionRejectsMissingProofOwnerBeforeNetwork(t *testing.T) {
	_, err := DialTransportSession(t.Context(), Readiness{}, TransportSessionConfig{})
	if !errors.Is(err, ErrInvalidSessionConfig) {
		t.Fatalf("missing proof owner error = %v", err)
	}
}

func TestClientHelloBindsActualProofPublicKeyAndRejectsDifferentEdgeHash(t *testing.T) {
	config := TransportSessionConfig{
		SessionID: [16]byte{1}, HelloRequestID: [16]byte{2}, SourceOperator: "source.operator",
		SourceEdge: "source.edge", DestinationOperator: "destination.operator", DestinationEdge: "destination.edge",
		ClientNonce: [32]byte{3}, ProofPublicKey: [32]byte{4}, NowUnix: 1_893_456_000,
	}
	hello := buildClientHello(config)
	if got, ok := hello.Body[6].([]byte); !ok || !bytes.Equal(got, config.ProofPublicKey[:]) {
		t.Fatalf("CLIENT_HELLO proof public key = %x", got)
	}
	edge := Envelope{ProtocolVersion: 2, MessageType: EdgeHello, RequestID: config.HelloRequestID, SessionID: config.SessionID, Sequence: 1,
		Body: map[uint64]any{0: uint64(1), 1: config.SourceEdge, 2: config.DestinationEdge, 3: config.ClientNonce[:], 4: bytes.Repeat([]byte{5}, 32), 5: sha256Bytes(config.ProofPublicKey[:]), 6: config.NowUnix}}
	if err := validateEdgeHello(config, edge); err != nil {
		t.Fatal(err)
	}
	wrong := sha256.Sum256([]byte("proof B"))
	edge.Body[5] = wrong[:]
	if !errors.Is(validateEdgeHello(config, edge), ErrProofBinding) {
		t.Fatal("EDGE_HELLO accepted proof B")
	}
}

func TestWirePeerAdapterPreservesValidatedRouteAndStreamSequence(t *testing.T) {
	want := []uint64{1, 2, 3, 4, 6, 7}
	got := []uint64{
		uint64(ClientHello), uint64(EdgeHello),
		uint64(RouteOpen), uint64(RouteAccept),
		uint64(StreamOpen), uint64(StreamAccept),
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("wire sequence codes = %v, want %v", got, want)
	}
	if ALPN != "nbsr-quic-1" || QUICVersion != "v1" || TLSVersion != "1.3" || StreamCreditProfile != "nbsr-stream-credit-1" {
		t.Fatalf("validated profiles drifted: %q %q %q %q", ALPN, QUICVersion, TLSVersion, StreamCreditProfile)
	}
}
