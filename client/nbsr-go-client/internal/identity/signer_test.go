package identity

import (
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"errors"
	"reflect"
	"strings"
	"testing"
)

func TestSignerNeverExportsPrivateKey(t *testing.T) {
	typ := reflect.TypeOf((*Signer)(nil)).Elem()
	for i := 0; i < typ.NumMethod(); i++ {
		if strings.Contains(strings.ToLower(typ.Method(i).Name), "private") {
			t.Fatal(typ.Method(i).Name)
		}
	}
}

func TestSignerPurposeBoundsSignaturesAndReturnsDefensiveCopies(t *testing.T) {
	private := ed25519.NewKeyFromSeed(bytes32(8))
	public := private.Public().(ed25519.PublicKey)
	ref := keyRef(5, PurposeTSProof, 2)
	ref.Thumbprint = sha256.Sum256(public)
	signer, err := NewMemorySigner(ref, private)
	if err != nil {
		t.Fatal(err)
	}
	private[0] ^= 0xff
	returnedPublic, err := signer.PublicKey(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	returnedPublic[0] ^= 0xff
	verificationPublic, err := signer.PublicKey(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if returnedPublic[0] == verificationPublic[0] {
		t.Fatal("public key was not defensively copied")
	}
	message := []byte("test-message")
	signature, err := signer.SignPurposeBound(context.Background(), PurposeTSProof, message)
	if err != nil {
		t.Fatal(err)
	}
	if !ed25519.Verify(verificationPublic, append(append([]byte("NBSR-GO-CLIENT-KEY-PURPOSE-v1\x00"), byte(PurposeTSProof)), message...), signature) {
		t.Fatal("signature does not bind the required purpose domain")
	}
	signature[0] ^= 0xff
	second, err := signer.SignPurposeBound(context.Background(), PurposeTSProof, message)
	if err != nil || !ed25519.Verify(verificationPublic, append(append([]byte("NBSR-GO-CLIENT-KEY-PURPOSE-v1\x00"), byte(PurposeTSProof)), message...), second) {
		t.Fatal(err)
	}
	if _, err := signer.SignPurposeBound(context.Background(), PurposeDeviceACPRequest, message); !errors.Is(err, ErrInvalidKeyPurpose) {
		t.Fatal(err)
	}
}

func TestSignerRejectsWrongThumbprint(t *testing.T) {
	ref := keyRef(5, PurposeTSProof, 2)
	if _, err := NewMemorySigner(ref, ed25519.NewKeyFromSeed(bytes32(8))); !errors.Is(err, ErrInvalidIdentity) {
		t.Fatal(err)
	}
}

func bytes32(value byte) (result []byte) {
	return append([]byte{value}, make([]byte, ed25519.SeedSize-1)...)
}
