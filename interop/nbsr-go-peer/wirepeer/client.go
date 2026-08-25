// Package wirepeer exposes the validated independent Go peer transport without
// reimplementing its frozen Core framing, QUIC/TLS checks, or credit refill.
// It owns no NBSR authority and cannot create a Transport Session or Service
// Channel authorization decision.
package wirepeer

import (
	"context"

	quic "github.com/quic-go/quic-go"
	"nbsr.local/interop/nbsr-go-peer/internal/core"
	"nbsr.local/interop/nbsr-go-peer/internal/streamcredit"
	"nbsr.local/interop/nbsr-go-peer/internal/transport"
)

const (
	ALPN                = "nbsr-quic-1"
	QUICVersion         = "v1"
	TLSVersion          = "1.3"
	StreamCreditProfile = streamcredit.ProfileID

	ClientHello  = core.ClientHello
	EdgeHello    = core.EdgeHello
	RouteOpen    = core.RouteOpen
	RouteAccept  = core.RouteAccept
	RouteReject  = core.RouteReject
	StreamOpen   = core.StreamOpen
	StreamAccept = core.StreamAccept
	StreamReject = core.StreamReject
)

type MessageType = core.MessageType
type Envelope = core.Envelope
type Readiness = transport.Readiness

// ApplicationStream is the narrow source-bidirectional QUIC stream surface
// needed by the production Application Stream adapter.
type ApplicationStream interface {
	Read([]byte) (int, error)
	Write([]byte) (int, error)
	Close() error
	StreamID() quic.StreamID
}

// Client delegates to the already validated transport.Peer implementation.
// The wrapper exists so demo-only modules never copy QUIC/TLS or Core framing.
type Client struct{ peer *transport.Peer }

func LoadReadiness(path string) (Readiness, error) { return transport.LoadReadiness(path) }

func Dial(ctx context.Context, ready Readiness) (*Client, error) {
	peer, err := transport.Dial(ctx, ready)
	if err != nil {
		return nil, err
	}
	return &Client{peer: peer}, nil
}

func (client *Client) SendEnvelope(envelope Envelope) error {
	return client.peer.SendEnvelope(envelope)
}

func (client *Client) SendRawControl(payload []byte) error {
	return client.peer.SendRawControl(payload)
}

func (client *Client) ReceiveEnvelope() (Envelope, error) {
	return client.peer.ReceiveEnvelope()
}

func (client *Client) ExportKeyingMaterial(contextBytes []byte) ([]byte, error) {
	return client.peer.ExportKeyingMaterial(contextBytes)
}

func (client *Client) OpenApplication(ctx context.Context) (ApplicationStream, error) {
	return client.peer.OpenApplication(ctx)
}

func (client *Client) RefillStreamCredits(ctx context.Context, channel [16]byte, epoch uint64) error {
	return client.peer.RefillStreamCredits(ctx, channel, epoch)
}

func (client *Client) Identity() string { return client.peer.Identity() }
func (client *Client) Close() error     { return client.peer.Close() }
