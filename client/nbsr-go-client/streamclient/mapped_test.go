package streamclient

import (
	"bytes"
	"context"
	"errors"
	"io"
	"testing"

	"nbsr.local/client/nbsr-go-client/internal/authority"
	"nbsr.local/client/nbsr-go-client/internal/corestate"
	"nbsr.local/client/nbsr-go-client/internal/resolution"
)

type mappedWire struct {
	read   bytes.Reader
	writes bytes.Buffer
}

func newMappedWire() *mappedWire                         { return &mappedWire{read: *bytes.NewReader([]byte{0})} }
func (wire *mappedWire) Read(value []byte) (int, error)  { return wire.read.Read(value) }
func (wire *mappedWire) Write(value []byte) (int, error) { return wire.writes.Write(value) }
func (*mappedWire) Close() error                         { return nil }

func mappedConfig(wire Wire) OwnedChannelConfig {
	return OwnedChannelConfig{
		Now: 1_900_000_000, ExpiresAt: 1_900_001_000, TSGeneration: 1, ChannelGeneration: 1, AuthorityGeneration: 1,
		ChannelID: [16]byte{1}, DeviceID: filled(6), PolicyDigest: filled(7), ServiceDigest: filled(8),
		RouteGrantDigest: filled(9), ProofThumbprint: filled(10), SourceOperator: "source", Gateway: "gateway",
		ServiceIdentity: "service.api", Profile: ProfileID, Transport: "tcp",
		Open: func(context.Context) (Wire, uint64, error) { return wire, 4, nil },
	}
}

func TestMappedRouteOpenerRequiresMappingServiceBinding(t *testing.T) {
	wire := newMappedWire()
	config := mappedConfig(wire)
	channel, err := NewOwnedChannel(context.Background(), config)
	if err != nil {
		t.Fatal(err)
	}
	opener, err := NewMappedRouteOpener(channel)
	if err != nil {
		t.Fatal(err)
	}
	context := resolution.RouteContext{
		MappingID: 1, ServiceIdentity: config.ServiceIdentity, ServiceDigest: corestate.ServiceDigest(config.ServiceDigest),
		Intent: authority.RouteIntent{ServiceIdentity: config.ServiceIdentity, Transport: "tcp", Port: 443},
	}
	stream, err := opener.OpenVerifiedRoute(context2(), context)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := stream.Write([]byte("payload")); err != nil {
		t.Fatal(err)
	}
	if !bytes.Contains(wire.writes.Bytes(), []byte("payload")) {
		t.Fatal("payload did not use existing Application Stream")
	}
	_ = stream.Close()
	bad := context
	bad.ServiceDigest[0]++
	if _, err := opener.OpenVerifiedRoute(context2(), bad); !errors.Is(err, resolution.ErrRouteBinding) {
		t.Fatalf("mismatch error = %v", err)
	}
}

func context2() context.Context { return context.Background() }

var _ io.ReadWriteCloser = (*mappedWire)(nil)
