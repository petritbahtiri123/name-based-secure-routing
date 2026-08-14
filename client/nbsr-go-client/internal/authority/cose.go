package authority

// COSE Sign1 verification is independent of the interop peer.  Its accepted
// profile is deliberately limited to the frozen Core v0.2 RouteGrant form.

import (
	"bytes"
	"crypto/ed25519"
	"errors"
)

type coseSign1 struct {
	protected []byte
	kid       []byte
	payload   []byte
	signature []byte
}

func parseRouteGrantSign1(exact []byte) (coseSign1, error) {
	if len(exact) < 2 || exact[0] != 0xd2 {
		return coseSign1{}, ErrInvalidAuthority
	}
	decoded, err := decodeCBORExact(exact[1:], defaultCBORLimits())
	if err != nil {
		return coseSign1{}, ErrInvalidAuthority
	}
	items, ok := decoded.([]any)
	if !ok || len(items) != 4 {
		return coseSign1{}, ErrInvalidAuthority
	}
	protected, protectedOK := items[0].([]byte)
	unprotected, unprotectedOK := items[1].(map[uint64]any)
	payload, payloadOK := items[2].([]byte)
	signature, signatureOK := items[3].([]byte)
	if !protectedOK || len(protected) == 0 || !unprotectedOK || len(unprotected) != 0 || !payloadOK || !signatureOK || len(signature) != ed25519.SignatureSize {
		return coseSign1{}, ErrInvalidAuthority
	}
	headersValue, err := decodeCBORExact(protected, defaultCBORLimits())
	if err != nil {
		return coseSign1{}, ErrInvalidAuthority
	}
	headers, ok := headersValue.(map[uint64]any)
	kid, kidOK := headers[4].([]byte)
	if !ok || len(headers) != 2 || headers[1] != int64(-8) || !kidOK || len(kid) < 1 || len(kid) > 64 {
		return coseSign1{}, ErrInvalidAuthority
	}
	return coseSign1{protected: append([]byte(nil), protected...), kid: append([]byte(nil), kid...), payload: append([]byte(nil), payload...), signature: append([]byte(nil), signature...)}, nil
}

func (sign1 coseSign1) verify(publicKey [32]byte) error {
	sigStructure, err := encodeCBOR([]any{"Signature1", sign1.protected, []byte{}, sign1.payload})
	if err != nil {
		return ErrInvalidAuthority
	}
	if !ed25519.Verify(ed25519.PublicKey(publicKey[:]), sigStructure, sign1.signature) {
		return ErrSignatureFailure
	}
	return nil
}

func sameKID(left, right []byte) bool  { return bytes.Equal(left, right) }
func validPublicKey(key [32]byte) bool { return !bytes.Equal(key[:], make([]byte, len(key))) }

var errNoStaticIssuer = errors.New("route grant issuer is not trusted")
