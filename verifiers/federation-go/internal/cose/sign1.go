package cose

import (
	"bytes"
	"crypto/ed25519"
	"fmt"

	"nbsr.example/federation-verifier/internal/cbor"
)

type Sign1 struct{ Protected, Kid, Payload, Signature []byte }

func Parse(raw []byte) (Sign1, error) {
	v, e := cbor.DecodeLimits(raw, cbor.Limits{MaxDepth: 8, MaxArray: 8, MaxMap: 8, MaxBytes: 1 << 16, MaxText: 256})
	if e != nil {
		return Sign1{}, e
	}
	if v.Kind != cbor.Tag || v.Tag != 18 || v.Tagged == nil || v.Tagged.Kind != cbor.Array || len(v.Tagged.Array) != 4 {
		return Sign1{}, fmt.Errorf("COSE Sign1 tag/shape")
	}
	a := v.Tagged.Array
	if a[0].Kind != cbor.Bytes || len(a[0].Bytes) == 0 || a[1].Kind != cbor.Map || len(a[1].Map) != 0 || a[2].Kind != cbor.Bytes || a[3].Kind != cbor.Bytes || len(a[3].Bytes) != 64 {
		return Sign1{}, fmt.Errorf("COSE field shape")
	}
	p, e := cbor.Decode(a[0].Bytes)
	if e != nil || p.Kind != cbor.Map || len(p.Map) != 2 {
		return Sign1{}, fmt.Errorf("COSE protected")
	}
	alg, ok := cbor.Get(p, 1)
	if !ok {
		return Sign1{}, fmt.Errorf("missing alg")
	}
	x, ok := cbor.Int(alg)
	if !ok || x != -8 {
		return Sign1{}, fmt.Errorf("alg")
	}
	kid, ok := cbor.Get(p, 4)
	if !ok || kid.Kind != cbor.Bytes || len(kid.Bytes) == 0 {
		return Sign1{}, fmt.Errorf("kid")
	}
	return Sign1{append([]byte(nil), a[0].Bytes...), append([]byte(nil), kid.Bytes...), append([]byte(nil), a[2].Bytes...), append([]byte(nil), a[3].Bytes...)}, nil
}
func (s Sign1) Verify(publicKey, expectedPayload, expectedKid []byte) error {
	if !bytes.Equal(s.Payload, expectedPayload) {
		return fmt.Errorf("payload mismatch")
	}
	if !bytes.Equal(s.Kid, expectedKid) {
		return fmt.Errorf("kid mismatch")
	}
	sig := cbor.Value{Kind: cbor.Array, Array: []cbor.Value{{Kind: cbor.Text, Text: "Signature1"}, {Kind: cbor.Bytes, Bytes: s.Protected}, {Kind: cbor.Bytes, Bytes: []byte{}}, {Kind: cbor.Bytes, Bytes: s.Payload}}}
	raw, e := cbor.Encode(sig)
	if e != nil {
		return e
	}
	if len(publicKey) != ed25519.PublicKeySize || !ed25519.Verify(ed25519.PublicKey(publicKey), raw, s.Signature) {
		return fmt.Errorf("signature invalid")
	}
	return nil
}
