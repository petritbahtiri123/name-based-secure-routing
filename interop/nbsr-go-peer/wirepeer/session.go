package wirepeer

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"errors"
	"fmt"

	"nbsr.local/interop/nbsr-go-peer/internal/authority"
	"nbsr.local/interop/nbsr-go-peer/internal/cbor"
)

var ErrInvalidSessionConfig = errors.New("invalid transport session configuration")
var ErrProofBinding = errors.New("transport proof binding mismatch")

type TransportSessionConfig struct {
	SessionID           [16]byte
	HelloRequestID      [16]byte
	SourceOperator      string
	SourceEdge          string
	DestinationOperator string
	DestinationEdge     string
	ClientNonce         [32]byte
	ProofPublicKey      [32]byte
	NowUnix             uint64
}

type TransportSession struct {
	client    *Client
	config    TransportSessionConfig
	edgeNonce [32]byte
}

type ProofSignFunc func(context.Context, []byte) ([]byte, error)

type ServiceChannelConfig struct {
	RequestID               [16]byte
	ChannelID               [16]byte
	ExactRouteGrant         []byte
	IssuerPublicKey         [32]byte
	IssuerKID               []byte
	OpenedAt                uint64
	FederationContextDigest [32]byte
	Federated               bool
	SignProof               ProofSignFunc
}

type VerifiedRouteBinding struct {
	ServiceIdentity string
	RouteID         [16]byte
	GrantDigest     [32]byte
	PolicyHash      [32]byte
	Transport       string
	Port            uint16
	ProofTranscript []byte
}

type ServiceChannel struct {
	transport   *TransportSession
	channelID   [16]byte
	routeID     [16]byte
	grantDigest [32]byte
}

func DialTransportSession(ctx context.Context, readiness Readiness, config TransportSessionConfig) (*TransportSession, error) {
	if config.SessionID == ([16]byte{}) || config.HelloRequestID == ([16]byte{}) ||
		config.SourceOperator == "" || config.SourceEdge == "" || config.DestinationOperator == "" || config.DestinationEdge == "" ||
		config.ClientNonce == ([32]byte{}) || config.ProofPublicKey == ([32]byte{}) || config.NowUnix == 0 {
		return nil, ErrInvalidSessionConfig
	}
	client, err := Dial(ctx, readiness)
	if err != nil {
		return nil, err
	}
	fail := func(err error) (*TransportSession, error) {
		_ = client.Close()
		return nil, err
	}
	if err := client.SendEnvelope(buildClientHello(config)); err != nil {
		return fail(err)
	}
	edge, err := client.ReceiveEnvelope()
	if err != nil {
		return fail(err)
	}
	if err := validateEdgeHello(config, edge); err != nil {
		return fail(err)
	}
	var edgeNonce [32]byte
	copy(edgeNonce[:], edge.Body[4].([]byte))
	return &TransportSession{client: client, config: config, edgeNonce: edgeNonce}, nil
}

func buildClientHello(config TransportSessionConfig) Envelope {
	return Envelope{ProtocolVersion: 2, MessageType: ClientHello, RequestID: config.HelloRequestID, SessionID: config.SessionID, Sequence: 1,
		Body: map[uint64]any{0: uint64(1), 1: config.SourceOperator, 2: config.SourceEdge, 3: config.DestinationOperator,
			4: config.DestinationEdge, 5: config.ClientNonce[:], 6: config.ProofPublicKey[:], 7: config.NowUnix}}
}

func validateEdgeHello(config TransportSessionConfig, edge Envelope) error {
	edgeNonce, edgeNonceOK := edge.Body[4].([]byte)
	proofHash, proofHashOK := edge.Body[5].([]byte)
	if edge.MessageType != EdgeHello || edge.RequestID != config.HelloRequestID || edge.SessionID != config.SessionID || edge.Sequence != 1 ||
		edge.Body[0] != uint64(1) || edge.Body[1] != config.SourceEdge || edge.Body[2] != config.DestinationEdge ||
		!bytes.Equal(bytesValue(edge.Body[3]), config.ClientNonce[:]) || !edgeNonceOK || len(edgeNonce) != 32 || !proofHashOK ||
		!bytes.Equal(proofHash, sha256Bytes(config.ProofPublicKey[:])) {
		return ErrProofBinding
	}
	return nil
}

func bytesValue(value any) []byte {
	raw, _ := value.([]byte)
	return raw
}

func sha256Bytes(value []byte) []byte {
	digest := sha256.Sum256(value)
	return digest[:]
}

func buildRouteOpen(ctx context.Context, transport *TransportSession, config ServiceChannelConfig) (Envelope, VerifiedRouteBinding, error) {
	if ctx == nil || transport == nil || config.RequestID == ([16]byte{}) || config.ChannelID == ([16]byte{}) ||
		len(config.ExactRouteGrant) == 0 || config.IssuerPublicKey == ([32]byte{}) || len(config.IssuerKID) == 0 ||
		config.OpenedAt == 0 || config.SignProof == nil || (config.Federated && config.FederationContextDigest == ([32]byte{})) {
		return Envelope{}, VerifiedRouteBinding{}, ErrInvalidSessionConfig
	}
	grant, err := authority.VerifyRouteGrant(config.ExactRouteGrant, ed25519.PublicKey(config.IssuerPublicKey[:]), config.IssuerKID, config.OpenedAt)
	if err != nil {
		return Envelope{}, VerifiedRouteBinding{}, fmt.Errorf("%w: RouteGrant verification: %v", ErrProofBinding, err)
	}
	if len(grant.AllowedPorts) != 1 || grant.AllowedPorts[0] == 0 || grant.AllowedPorts[0] > 65535 {
		return Envelope{}, VerifiedRouteBinding{}, fmt.Errorf("%w: RouteGrant port set", ErrProofBinding)
	}
	body := map[uint64]any{
		0: uint64(1), 1: config.ChannelID[:], 2: append([]byte(nil), config.ExactRouteGrant...), 3: transport.edgeNonce[:],
		4: grant.AllowedTransport, 5: grant.AllowedPorts[0], 6: config.OpenedAt, 7: make([]byte, ed25519.SignatureSize),
	}
	var transcript []byte
	if config.Federated {
		body[0] = uint64(2)
		body[8] = map[uint64]any{0: uint64(1), 1: uint64(1), 2: uint64(1), 3: "nbsr-federation-dev-v1", 4: grant.Digest[:], 5: config.FederationContextDigest[:]}
		transcript, err = authority.BuildF75Transcript(transport.config.SessionID, config.RequestID, transport.config.DestinationEdge, body, grant)
	} else {
		transcript, err = cbor.Encode([]any{"NBSR-ROUTE-OPEN-v2", uint64(2), transport.config.SessionID[:], config.RequestID[:], config.ChannelID[:],
			grant.RouteID[:], grant.ServiceID, transport.config.DestinationEdge, transport.edgeNonce[:], grant.AllowedTransport,
			grant.AllowedPorts[0], grant.Digest[:], config.OpenedAt})
	}
	if err != nil {
		return Envelope{}, VerifiedRouteBinding{}, fmt.Errorf("%w: canonical transcript: %v", ErrProofBinding, err)
	}
	proof, err := config.SignProof(ctx, transcript)
	if err != nil {
		return Envelope{}, VerifiedRouteBinding{}, fmt.Errorf("%w: proof signer: %v", ErrProofBinding, err)
	}
	if len(proof) != ed25519.SignatureSize || !ed25519.Verify(ed25519.PublicKey(transport.config.ProofPublicKey[:]), transcript, proof) {
		return Envelope{}, VerifiedRouteBinding{}, fmt.Errorf("%w: proof signature", ErrProofBinding)
	}
	body[7] = append([]byte(nil), proof...)
	envelope := Envelope{ProtocolVersion: 2, MessageType: RouteOpen, RequestID: config.RequestID, SessionID: transport.config.SessionID, Sequence: 2, Body: body}
	return envelope, VerifiedRouteBinding{ServiceIdentity: grant.ServiceID, RouteID: grant.RouteID, GrantDigest: grant.Digest,
		PolicyHash: grant.PolicyHash, Transport: grant.AllowedTransport, Port: uint16(grant.AllowedPorts[0]), ProofTranscript: append([]byte(nil), transcript...)}, nil
}

func (transport *TransportSession) OpenServiceChannel(ctx context.Context, config ServiceChannelConfig) (*ServiceChannel, VerifiedRouteBinding, error) {
	envelope, binding, err := buildRouteOpen(ctx, transport, config)
	if err != nil {
		return nil, VerifiedRouteBinding{}, err
	}
	if err := transport.client.SendEnvelope(envelope); err != nil {
		return nil, VerifiedRouteBinding{}, err
	}
	accepted, err := transport.client.ReceiveEnvelope()
	if err != nil {
		return nil, VerifiedRouteBinding{}, err
	}
	channel := bytesValue(accepted.Body[1])
	route := bytesValue(accepted.Body[2])
	digest := bytesValue(accepted.Body[3])
	if accepted.MessageType != RouteAccept || accepted.SessionID != transport.config.SessionID || accepted.RequestID != config.RequestID || accepted.Sequence != 2 ||
		!bytes.Equal(channel, config.ChannelID[:]) || !bytes.Equal(route, binding.RouteID[:]) || !bytes.Equal(digest, binding.GrantDigest[:]) {
		return nil, VerifiedRouteBinding{}, fmt.Errorf("%w: ROUTE_ACCEPT correlation", ErrProofBinding)
	}
	return &ServiceChannel{transport: transport, channelID: config.ChannelID, routeID: binding.RouteID, grantDigest: binding.GrantDigest}, binding, nil
}

func (transport *TransportSession) Close() error {
	if transport == nil || transport.client == nil {
		return nil
	}
	return transport.client.Close()
}

func (channel *ServiceChannel) ChannelID() [16]byte { return channel.channelID }
func (channel *ServiceChannel) OpenApplication(ctx context.Context) (ApplicationStream, error) {
	return channel.transport.client.OpenApplication(ctx)
}
func (channel *ServiceChannel) RefillStreamCredits(ctx context.Context, epoch uint64) error {
	return channel.transport.client.RefillStreamCredits(ctx, channel.channelID, epoch)
}
func (channel *ServiceChannel) Close() error { return nil }
