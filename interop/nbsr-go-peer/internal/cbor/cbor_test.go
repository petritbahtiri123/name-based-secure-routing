package cbor_test

import (
	"bytes"
	"testing"

	"nbsr.local/interop/nbsr-go-peer/internal/cbor"
)

func TestPreferredCBORRoundTripsLiteralEnvelope(t *testing.T) {
	wire := []byte{0xa2, 0x00, 0x02, 0x01, 0x63, 't', 'c', 'p'}
	value, err := cbor.DecodeExact(wire, cbor.DefaultLimits())
	if err != nil {
		t.Fatalf("decode preferred CBOR: %v", err)
	}
	encoded, err := cbor.Encode(value)
	if err != nil {
		t.Fatalf("encode preferred CBOR: %v", err)
	}
	if !bytes.Equal(encoded, wire) {
		t.Fatalf("round trip = %x, want %x", encoded, wire)
	}
}

func TestDecoderRejectsNonPreferredOrAmbiguousCBOR(t *testing.T) {
	cases := map[string][]byte{
		"duplicate map key": {0xa2, 0x00, 0x01, 0x00, 0x02},
		"non-shortest uint": {0x18, 0x17},
		"indefinite map":    {0xbf, 0xff},
		"tag":               {0xc0, 0x00},
		"float":             {0xf9, 0x00, 0x00},
		"invalid utf8":      {0x61, 0xff},
		"trailing data":     {0x00, 0x00},
	}
	for name, wire := range cases {
		t.Run(name, func(t *testing.T) {
			if _, err := cbor.DecodeExact(wire, cbor.DefaultLimits()); err == nil {
				t.Fatal("accepted malformed or non-preferred CBOR")
			}
		})
	}
}

func TestDecoderEnforcesDepthAndCollectionLimits(t *testing.T) {
	limits := cbor.DefaultLimits()
	limits.MaxDepth = 2
	if _, err := cbor.DecodeExact([]byte{0x81, 0x81, 0x81, 0x00}, limits); err == nil {
		t.Fatal("accepted excessive nesting")
	}
	limits = cbor.DefaultLimits()
	limits.MaxCollectionItems = 1
	if _, err := cbor.DecodeExact([]byte{0x82, 0x00, 0x01}, limits); err == nil {
		t.Fatal("accepted oversized collection")
	}
	limits = cbor.DefaultLimits()
	limits.MaxByteStringBytes = 1
	if _, err := cbor.DecodeExact([]byte{0x42, 0x00, 0x01}, limits); err == nil {
		t.Fatal("accepted oversized byte string")
	}
}
