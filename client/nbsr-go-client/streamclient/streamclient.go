// Package streamclient exposes the production P2D admission gate to concrete
// QUIC adapters without exposing internal ownership types.
package streamclient

import (
	"context"
	"errors"
	"io"
	"sync"

	"nbsr.local/client/nbsr-go-client/internal/authority"
	"nbsr.local/client/nbsr-go-client/internal/corestate"
	"nbsr.local/client/nbsr-go-client/internal/identity"
	"nbsr.local/client/nbsr-go-client/internal/session"
)

const ProfileID = session.StreamCreditProfileID

type Wire interface {
	io.Reader
	io.Writer
	io.Closer
}

type OpenFunc func(context.Context) (Wire, uint64, error)
type RefillFunc func(context.Context, uint64) error

type OwnedChannel struct {
	manager    *session.Manager
	generation corestate.TSGeneration
	handle     corestate.ServiceHandle
}
type OwnedChannelConfig struct {
	Now, ExpiresAt, TSGeneration, ChannelGeneration, AuthorityGeneration     uint64
	ChannelID                                                                [16]byte
	DeviceID, PolicyDigest, ServiceDigest, RouteGrantDigest, ProofThumbprint [32]byte
	SourceOperator, Gateway, ServiceIdentity, Profile, Transport             string
	Open                                                                     OpenFunc
	Refill                                                                   RefillFunc
}
type fixedClock struct{ now uint64 }

func (clock fixedClock) NowUnix() uint64 { return clock.now }

type fixedGate struct {
	generation authority.AuthorityGeneration
	expires    uint64
	grant      corestate.RouteGrantDigest
	mu         sync.Mutex
	valid      bool
}

func (gate *fixedGate) Capture() (authority.AuthorityGeneration, error) {
	gate.mu.Lock()
	defer gate.mu.Unlock()
	if !gate.valid {
		return 0, authority.ErrStaleGeneration
	}
	return gate.generation, nil
}
func (gate *fixedGate) Validate(g authority.AuthorityGeneration) error {
	gate.mu.Lock()
	defer gate.mu.Unlock()
	if !gate.valid || g != gate.generation {
		return authority.ErrStaleGeneration
	}
	return nil
}
func (gate *fixedGate) ValidateSession(_ session.ReuseKey, g authority.AuthorityGeneration) error {
	return gate.Validate(g)
}
func (gate *fixedGate) Preflight(r session.ServiceChannelRequest, g authority.AuthorityGeneration, now uint64) ([]byte, error) {
	if err := gate.Validate(g); err != nil {
		return nil, err
	}
	if now >= gate.expires || r.RouteGrantDigest != gate.grant {
		return nil, authority.ErrExpired
	}
	return []byte{1}, nil
}
func (gate *fixedGate) Commit(r session.ServiceChannelRequest, g authority.AuthorityGeneration, now uint64) (session.AuthorityToken, error) {
	_, err := gate.Preflight(r, g, now)
	return session.AuthorityToken{Generation: g, Grant: r.RouteGrantDigest, Revision: 1}, err
}
func (gate *fixedGate) CommitApplication(token session.AuthorityToken, owner authority.AdmissionOwner, now uint64, commit func() error) error {
	gate.mu.Lock()
	defer gate.mu.Unlock()
	if !gate.valid || token.Generation != gate.generation || token.Grant != gate.grant || token.Revision != 1 || now >= gate.expires || owner.TSGeneration == 0 || owner.ChannelID == ([16]byte{}) {
		return authority.ErrStaleGeneration
	}
	return commit()
}

type ownedTransport struct{}

func (ownedTransport) Close() error { return nil }

type ownedConnector struct{}

func (ownedConnector) Connect(context.Context, session.TransportSessionAttempt) (session.Transport, error) {
	return ownedTransport{}, nil
}

type ownedOpener struct{ channel *ownedWireChannel }

func (opener ownedOpener) Open(context.Context, session.Transport, session.ServiceChannelAttempt) (session.WireChannel, error) {
	return opener.channel, nil
}

type ownedWireChannel struct {
	id         corestate.ChannelID
	generation uint64
	profile    string
	open       OpenFunc
	refill     RefillFunc
}

func (c *ownedWireChannel) ChannelID() corestate.ChannelID { return c.id }
func (c *ownedWireChannel) ChannelGeneration() uint64      { return c.generation }
func (c *ownedWireChannel) Close() error                   { return nil }
func (c *ownedWireChannel) StreamCreditProfile() string    { return c.profile }
func (c *ownedWireChannel) OpenApplicationStream(ctx context.Context) (session.WireApplicationStream, error) {
	wire, id, err := c.open(ctx)
	if err != nil {
		return nil, err
	}
	return &wireAdapter{wire: wire, id: corestate.StreamID(id)}, nil
}
func (c *ownedWireChannel) RefillStreamCredits(ctx context.Context, epoch uint64) error {
	if c.refill == nil {
		return errors.New("stream-credit refill unavailable")
	}
	return c.refill(ctx, epoch)
}

func NewOwnedChannel(ctx context.Context, c OwnedChannelConfig) (*OwnedChannel, error) {
	if ctx == nil || c.Open == nil || c.TSGeneration == 0 || c.ChannelGeneration == 0 || c.AuthorityGeneration == 0 || c.Now >= c.ExpiresAt || c.ChannelID == ([16]byte{}) {
		return nil, session.ErrInvalidSession
	}
	deviceKey := identity.KeyRef{ID: filled(1), Purpose: identity.PurposeDeviceACPRequest, Generation: 1, Thumbprint: filled(2)}
	device := identity.DeviceIdentity{ID: c.DeviceID, SourceOperatorID: c.SourceOperator, CredentialGeneration: 1, CredentialNotBefore: c.Now - 1, CredentialExpiresAt: c.ExpiresAt, SigningKey: deviceKey}
	proof := identity.TSProofKey{TSGeneration: c.TSGeneration, Key: identity.KeyRef{ID: filled(3), Purpose: identity.PurposeTSProof, Generation: c.TSGeneration, Thumbprint: c.ProofThumbprint}}
	registry, err := identity.NewMemoryRegistry(device, nil, []identity.TSProofKey{proof}, identity.LocalStateIntegrityKey{Key: identity.KeyRef{ID: filled(4), Purpose: identity.PurposeLocalStateIntegrity, Generation: 1, Thumbprint: filled(5)}})
	if err != nil {
		return nil, err
	}
	gate := &fixedGate{generation: authority.AuthorityGeneration(c.AuthorityGeneration), expires: c.ExpiresAt, grant: corestate.RouteGrantDigest(c.RouteGrantDigest), valid: true}
	wireChannel := &ownedWireChannel{id: corestate.ChannelID(c.ChannelID), generation: c.ChannelGeneration, profile: c.Profile, open: c.Open, refill: c.Refill}
	limits := session.Limits{MaxReuseKeys: 1, MaxSessions: 1, MaxChannels: 1, MaxPendingSessions: 1, MaxPendingChannels: 1, MaxWaitersPerChannel: 1, MaxStreams: 64, MaxPendingAdmissions: 16, MaxReuseKeyBytes: 512, MaxServiceIdentityBytes: 256, MaxStateBytes: 64 * 1024}
	manager, err := session.NewManagerWithBarrier(limits, fixedClock{c.Now}, gate, registry, ownedConnector{}, ownedOpener{wireChannel})
	if err != nil {
		return nil, err
	}
	generation := corestate.TSGeneration(c.TSGeneration)
	reuse := session.ReuseKey{SourceOperator: c.SourceOperator, Gateway: c.Gateway, Profile: c.Profile, Transport: c.Transport, DeviceID: c.DeviceID, DeviceGeneration: 1, PolicyDigest: c.PolicyDigest, PolicyGeneration: 1}
	if _, err = manager.CreateTransportSession(ctx, session.TransportSessionSpec{Generation: generation, ReuseKey: reuse, Proof: proof}); err != nil {
		return nil, err
	}
	snapshot, err := manager.CreateServiceChannel(ctx, session.ServiceChannelRequest{Generation: generation, ChannelID: corestate.ChannelID(c.ChannelID), ServiceIdentity: c.ServiceIdentity, ServiceDigest: corestate.ServiceDigest(c.ServiceDigest), RouteGrantDigest: corestate.RouteGrantDigest(c.RouteGrantDigest), AuthorityGeneration: corestate.AuthorityGeneration(c.AuthorityGeneration), ProofThumbprint: authority.ProofKeyThumbprint(c.ProofThumbprint)})
	if err != nil {
		_ = manager.CloseTransportSession(generation)
		return nil, err
	}
	return &OwnedChannel{manager: manager, generation: generation, handle: snapshot.Handle}, nil
}
func filled(v byte) (out [32]byte) {
	for i := range out {
		out[i] = v
	}
	return
}
func (owner *OwnedChannel) Open(ctx context.Context) (*session.ApplicationStream, error) {
	return owner.manager.OpenApplicationStream(ctx, owner.generation, owner.handle)
}
func (owner *OwnedChannel) Close() error {
	return owner.manager.CloseTransportSession(owner.generation)
}

type Stream struct{ wire Wire }

func (stream *Stream) Read(value []byte) (int, error)  { return stream.wire.Read(value) }
func (stream *Stream) Write(value []byte) (int, error) { return stream.wire.Write(value) }
func (stream *Stream) Close() error                    { return stream.wire.Close() }

func Admit(ctx context.Context, profile string, open OpenFunc, channel [16]byte, channelGeneration, epoch uint64, slot uint8) (*Stream, error) {
	if open == nil {
		return nil, session.ErrTransport
	}
	opener := openerAdapter{profile: profile, open: open}
	credit := session.CreditReservation{ChannelID: corestate.ChannelID(channel), ChannelGeneration: channelGeneration, Epoch: epoch, Slot: slot}
	wire, err := session.OpenAdmittedWireApplication(ctx, opener, credit, nil)
	if err != nil {
		return nil, err
	}
	return &Stream{wire: wire.(*wireAdapter).wire}, nil
}

type openerAdapter struct {
	profile string
	open    OpenFunc
}

func (opener openerAdapter) StreamCreditProfile() string                       { return opener.profile }
func (opener openerAdapter) RefillStreamCredits(context.Context, uint64) error { return nil }
func (opener openerAdapter) OpenApplicationStream(ctx context.Context) (session.WireApplicationStream, error) {
	wire, id, err := opener.open(ctx)
	if err != nil {
		return nil, err
	}
	return &wireAdapter{wire: wire, id: corestate.StreamID(id)}, nil
}

type wireAdapter struct {
	wire Wire
	id   corestate.StreamID
}

func (wire *wireAdapter) Read(value []byte) (int, error)  { return wire.wire.Read(value) }
func (wire *wireAdapter) Write(value []byte) (int, error) { return wire.wire.Write(value) }
func (wire *wireAdapter) Close() error                    { return wire.wire.Close() }
func (wire *wireAdapter) StreamID() corestate.StreamID    { return wire.id }
