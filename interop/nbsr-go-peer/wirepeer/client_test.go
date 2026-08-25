package wirepeer

import (
	"context"
	"io"
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

var _ validatedClientBoundary = (*Client)(nil)
var _ io.ReadWriteCloser = (ApplicationStream)(nil)

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
