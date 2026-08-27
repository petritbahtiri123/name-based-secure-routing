package client

import (
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/binary"
	"errors"

	"nbsr.local/client/nbsr-go-client/internal/corestate"
	"nbsr.local/client/nbsr-go-client/internal/identity"
	"nbsr.local/client/nbsr-go-client/internal/session"
	"nbsr.local/interop/nbsr-go-peer/wirepeer"
)

type TSProofOwner struct {
	private ed25519.PrivateKey
	public  [ed25519.PublicKeySize]byte
	ref     identity.KeyRef
}

func NewTSProofOwner(private ed25519.PrivateKey, generation uint64) (*TSProofOwner, error) {
	if len(private) != ed25519.PrivateKeySize || generation == 0 {
		return nil, session.ErrProofBinding
	}
	publicKey := private.Public().(ed25519.PublicKey)
	thumbprint := sha256.Sum256(publicKey)
	idInput := make([]byte, 8+len(publicKey))
	binary.BigEndian.PutUint64(idInput, generation)
	copy(idInput[8:], publicKey)
	owner := &TSProofOwner{private: append(ed25519.PrivateKey(nil), private...), ref: identity.KeyRef{
		ID: sha256.Sum256(idInput), Purpose: identity.PurposeTSProof, Generation: generation, Thumbprint: thumbprint,
	}}
	copy(owner.public[:], publicKey)
	return owner, nil
}

func (owner *TSProofOwner) KeyRef() identity.KeyRef {
	if owner == nil {
		return identity.KeyRef{}
	}
	return owner.ref
}

func (owner *TSProofOwner) PublicKey() []byte {
	if owner == nil {
		return nil
	}
	return append([]byte(nil), owner.public[:]...)
}

func (owner *TSProofOwner) Sign(ctx context.Context, message []byte) ([]byte, error) {
	if owner == nil {
		return nil, session.ErrProofBinding
	}
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	return ed25519.Sign(owner.private, message), nil
}

type wireConnector struct {
	proof     *TSProofOwner
	readiness wirepeer.Readiness
	now       uint64
}

func (connector *wireConnector) Connect(ctx context.Context, attempt session.TransportSessionAttempt) (session.Transport, error) {
	if connector == nil || connector.proof == nil || attempt.Generation == 0 || attempt.ProofKey != connector.proof.KeyRef() || uint64(attempt.Generation) != connector.proof.ref.Generation {
		return nil, session.ErrProofBinding
	}
	if connector.now == 0 {
		return nil, session.ErrTransport
	}
	var public [ed25519.PublicKeySize]byte
	copy(public[:], connector.proof.PublicKey())
	transport, err := wirepeer.DialTransportSession(ctx, connector.readiness, wirepeer.TransportSessionConfig{
		SessionID: sequence16(0x10), HelloRequestID: sequence16(0), SourceOperator: attempt.ReuseKey.SourceOperator,
		SourceEdge: "source.edge", DestinationOperator: "destination.operator", DestinationEdge: "destination.edge",
		ClientNonce: sequence32(0x60), ProofPublicKey: public, NowUnix: connector.now,
	})
	if err != nil {
		return nil, errors.Join(session.ErrTransport, err)
	}
	return &wireTransport{session: transport}, nil
}

type wireTransport struct{ session *wirepeer.TransportSession }

func (transport *wireTransport) Close() error {
	if transport == nil || transport.session == nil {
		return nil
	}
	return transport.session.Close()
}

type wireChannelOpener struct {
	proof                   *TSProofOwner
	issuerKID               []byte
	issuerPublicKey         [ed25519.PublicKeySize]byte
	now                     uint64
	federationContextDigest [32]byte
}

func (opener *wireChannelOpener) Open(ctx context.Context, transport session.Transport, attempt session.ServiceChannelAttempt) (session.WireChannel, error) {
	wireTransport, ok := transport.(*wireTransport)
	if !ok || wireTransport.session == nil || opener == nil || opener.proof == nil ||
		attempt.Generation == 0 || attempt.ProofThumbprint != opener.proof.ref.Thumbprint || len(attempt.ExactRouteGrant) == 0 {
		return nil, session.ErrProofBinding
	}
	channel, binding, err := wireTransport.session.OpenServiceChannel(ctx, wirepeer.ServiceChannelConfig{
		RequestID: [16]byte{0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16}, ChannelID: [16]byte(attempt.ChannelID),
		ExactRouteGrant: attempt.ExactRouteGrant, IssuerPublicKey: opener.issuerPublicKey, IssuerKID: append([]byte(nil), opener.issuerKID...),
		OpenedAt: opener.now, FederationContextDigest: opener.federationContextDigest, SignProof: opener.proof.Sign,
	})
	if err != nil {
		return nil, errors.Join(session.ErrTransport, err)
	}
	if binding.ServiceIdentity != attempt.ServiceIdentity || binding.GrantDigest != [32]byte(attempt.RouteGrant) {
		_ = channel.Close()
		return nil, session.ErrServiceBinding
	}
	return &wireChannel{channel: channel, id: attempt.ChannelID, generation: 1}, nil
}

type wireChannel struct {
	channel    *wirepeer.ServiceChannel
	id         corestate.ChannelID
	generation uint64
}

func (channel *wireChannel) ChannelID() corestate.ChannelID { return channel.id }
func (channel *wireChannel) ChannelGeneration() uint64      { return channel.generation }
func (channel *wireChannel) Close() error                   { return channel.channel.Close() }
func (channel *wireChannel) StreamCreditProfile() string    { return wirepeer.StreamCreditProfile }
func (channel *wireChannel) RefillStreamCredits(ctx context.Context, epoch uint64) error {
	return channel.channel.RefillStreamCredits(ctx, epoch)
}
func (channel *wireChannel) OpenApplicationStream(ctx context.Context) (session.WireApplicationStream, error) {
	stream, err := channel.channel.OpenApplication(ctx)
	if err != nil {
		return nil, err
	}
	return &wireApplicationStream{ApplicationStream: stream}, nil
}

type wireApplicationStream struct{ wirepeer.ApplicationStream }

func (stream *wireApplicationStream) StreamID() corestate.StreamID {
	return corestate.StreamID(stream.ApplicationStream.StreamID())
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
