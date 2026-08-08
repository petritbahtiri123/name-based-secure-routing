package core_test

import (
	"bytes"
	"os"
	"path/filepath"
	"testing"

	"nbsr.local/interop/nbsr-go-peer/internal/cbor"
	"nbsr.local/interop/nbsr-go-peer/internal/core"
)

func repositoryPath(parts ...string) string {
	all := append([]string{"..", "..", "..", ".."}, parts...)
	return filepath.Join(all...)
}

func TestFrozenCoreV02EnvelopesDecodeAndReencodeByteForByte(t *testing.T) {
	files := []string{"client-hello.cbor", "edge-hello.cbor", "route-open.cbor", "route-accept.cbor", "stream-open.cbor", "stream-accept.cbor"}
	for _, name := range files {
		t.Run(name, func(t *testing.T) {
			wire, err := os.ReadFile(repositoryPath("vectors", "core-v0.2", "artifacts", "valid", "envelopes", name))
			if err != nil {
				t.Fatal(err)
			}
			envelope, err := core.DecodeEnvelope(wire)
			if err != nil {
				t.Fatalf("decode: %v", err)
			}
			if envelope.ProtocolVersion != 2 {
				t.Fatalf("version = %d", envelope.ProtocolVersion)
			}
			encoded, err := core.EncodeEnvelope(envelope)
			if err != nil {
				t.Fatalf("encode: %v", err)
			}
			if !bytes.Equal(encoded, wire) {
				t.Fatalf("re-encoding differs\n got %x\nwant %x", encoded, wire)
			}
		})
	}
}

func TestF75RouteOpenV2BodyUsesExactClosedBinding(t *testing.T) {
	wire, err := os.ReadFile(repositoryPath("vectors", "wp8-f75-route-open", "route-open-body.cbor"))
	if err != nil {
		t.Fatal(err)
	}
	value, err := cbor.DecodeExact(wire, cbor.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	body, ok := value.(map[uint64]any)
	if !ok {
		t.Fatal("body is not a numeric-key map")
	}
	if err := core.ValidateBody(core.RouteOpen, body); err != nil {
		t.Fatalf("validate F75 body: %v", err)
	}
	if body[0] != uint64(2) {
		t.Fatalf("body version = %v", body[0])
	}
	binding := body[8].(map[uint64]any)
	if binding[0] != uint64(1) || binding[1] != uint64(1) || binding[2] != uint64(1) || binding[3] != "nbsr-federation-dev-v1" {
		t.Fatalf("wrong federation binding: %#v", binding)
	}
}

func TestControlFrameUsesShortestQUICVarintAndExactLength(t *testing.T) {
	payload := bytes.Repeat([]byte{0xa5}, 63)
	frame, err := core.EncodeControlFrame(payload)
	if err != nil {
		t.Fatal(err)
	}
	if frame[0] != 63 {
		t.Fatalf("prefix = %x, want one-byte 63", frame[0])
	}
	decoded, rest, err := core.DecodeControlFrame(frame)
	if err != nil {
		t.Fatal(err)
	}
	if len(rest) != 0 || !bytes.Equal(decoded, payload) {
		t.Fatal("frame round trip differs")
	}

	if _, _, err := core.DecodeControlFrame([]byte{0x40, 0x01, 0x00}); err == nil {
		t.Fatal("accepted non-shortest QUIC varint")
	}
	if _, _, err := core.DecodeControlFrame([]byte{0x05, 0x00}); err == nil {
		t.Fatal("accepted truncated control frame")
	}
}
