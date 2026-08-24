// Package streamclient exposes the production P2D admission gate to concrete
// QUIC adapters without exposing internal ownership types.
package streamclient

import (
	"context"
	"io"

	"nbsr.local/client/nbsr-go-client/internal/corestate"
	"nbsr.local/client/nbsr-go-client/internal/session"
)

const ProfileID = session.StreamCreditProfileID

type Wire interface {
	io.Reader
	io.Writer
	io.Closer
}

type OpenFunc func(context.Context) (Wire, uint64, error)

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
	wire, err := session.OpenAdmittedWireApplication(ctx, opener, credit)
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
