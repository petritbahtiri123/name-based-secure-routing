package identity

import (
	"context"
	"crypto/ed25519"
	"crypto/sha256"
)

var signingDomain = []byte("NBSR-GO-CLIENT-KEY-PURPOSE-v1\x00")

// MemorySigner is a test-only signer that retains a private-key copy in memory.
type MemorySigner struct {
	ref     KeyRef
	private ed25519.PrivateKey
	public  ed25519.PublicKey
}

func NewMemorySigner(ref KeyRef, private ed25519.PrivateKey) (*MemorySigner, error) {
	if err := validateKeyRef(ref, ref.Purpose); err != nil {
		return nil, err
	}
	if len(private) != ed25519.PrivateKeySize {
		return nil, &IdentityError{Code: CodeInvalidIdentity, Resource: "private key"}
	}
	privateCopy := append(ed25519.PrivateKey(nil), private...)
	public := append(ed25519.PublicKey(nil), privateCopy.Public().(ed25519.PublicKey)...)
	if sha256.Sum256(public) != ref.Thumbprint {
		return nil, &IdentityError{Code: CodeInvalidIdentity, Resource: "key thumbprint"}
	}
	return &MemorySigner{ref: ref, private: privateCopy, public: public}, nil
}

func (s *MemorySigner) KeyRef() KeyRef {
	if s == nil {
		return KeyRef{}
	}
	return s.ref
}

func (s *MemorySigner) PublicKey(ctx context.Context) ([]byte, error) {
	if err := contextError(ctx); err != nil {
		return nil, err
	}
	if s == nil {
		return nil, ErrUnknownIdentity
	}
	return append([]byte(nil), s.public...), nil
}

func (s *MemorySigner) SignPurposeBound(ctx context.Context, purpose Purpose, message []byte) ([]byte, error) {
	if err := contextError(ctx); err != nil {
		return nil, err
	}
	if s == nil {
		return nil, ErrUnknownIdentity
	}
	if purpose != s.ref.Purpose {
		return nil, &IdentityError{Code: CodeInvalidKeyPurpose, Resource: "signing purpose"}
	}
	payload := make([]byte, 0, len(signingDomain)+1+len(message))
	payload = append(payload, signingDomain...)
	payload = append(payload, byte(purpose))
	payload = append(payload, message...)
	return ed25519.Sign(s.private, payload), nil
}

func contextError(ctx context.Context) error {
	if ctx == nil {
		return nil
	}
	return ctx.Err()
}

var _ Signer = (*MemorySigner)(nil)
