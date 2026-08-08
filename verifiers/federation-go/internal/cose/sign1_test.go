package cose

import (
	"crypto/ed25519"
	"nbsr.example/federation-verifier/internal/cbor"
	"testing"
)

func TestSign1RoundTrip(t *testing.T) {
	pub, priv, _ := ed25519.GenerateKey(nil)
	protected, _ := cbor.Encode(cbor.Value{Kind: cbor.Map, Map: []cbor.Pair{{Key: cbor.Value{Kind: cbor.Uint, Uint: 1}, Value: cbor.Value{Kind: cbor.Nint, Uint: 7}}, {Key: cbor.Value{Kind: cbor.Uint, Uint: 4}, Value: cbor.Value{Kind: cbor.Bytes, Bytes: []byte("kid")}}}})
	payload := []byte("payload")
	ss, _ := cbor.Encode(cbor.Value{Kind: cbor.Array, Array: []cbor.Value{{Kind: cbor.Text, Text: "Signature1"}, {Kind: cbor.Bytes, Bytes: protected}, {Kind: cbor.Bytes, Bytes: []byte{}}, {Kind: cbor.Bytes, Bytes: payload}}})
	sig := ed25519.Sign(priv, ss)
	inner := cbor.Value{Kind: cbor.Array, Array: []cbor.Value{{Kind: cbor.Bytes, Bytes: protected}, {Kind: cbor.Map}, {Kind: cbor.Bytes, Bytes: payload}, {Kind: cbor.Bytes, Bytes: sig}}}
	raw, _ := cbor.Encode(cbor.Value{Kind: cbor.Tag, Tag: 18, Tagged: &inner})
	got, e := Parse(raw)
	if e != nil {
		t.Fatal(e)
	}
	if e = got.Verify(pub, payload, []byte("kid")); e != nil {
		t.Fatal(e)
	}
	got.Signature[0] ^= 1
	if e = got.Verify(pub, payload, []byte("kid")); e == nil {
		t.Fatal("accepted mutation")
	}
}
