package authority

import (
	"context"
	"crypto/ed25519"
)

// DemoRouteGrantInput is a fixture-only construction boundary for producing
// an exact frozen RouteGrant. It does not verify or authorize the result.
type DemoRouteGrantInput struct {
	Key       AuthorityKey
	Intent    RouteIntent
	NotBefore uint64
	Nonce     [16]byte
	KID       []byte
}

// SignDemoRouteGrant uses the same deterministic CBOR and COSE Sign1 encoder
// consumed by the production verifier. It is intentionally unsuitable for a
// production key service because it accepts an in-memory private key.
func SignDemoRouteGrant(ctx context.Context, input DemoRouteGrantInput, private ed25519.PrivateKey) ([]byte, error) {
	if ctx == nil || ctx.Err() != nil || len(private) != ed25519.PrivateKeySize || len(input.KID) < 1 || len(input.KID) > 64 ||
		input.NotBefore == 0 || input.NotBefore >= input.Intent.ExpiresAt || input.Intent.ExpiresAt-input.NotBefore > maxRouteGrantLifetime {
		if ctx != nil && ctx.Err() != nil {
			return nil, ctx.Err()
		}
		return nil, ErrInvalidAuthority
	}
	payload, err := encodeCBOR(map[uint64]any{
		0: uint64(1), 1: input.Intent.RouteID[:], 2: input.Key.ServiceDigest[:], 3: input.Intent.ServiceIdentity,
		4: input.Key.SourceOperator, 5: input.Key.SourceEdge, 6: input.Key.TargetOperator,
		7: stringsToAny(input.Intent.TargetEdges), 8: []any{input.Key.Transport}, 9: []any{uint64(input.Key.Port)},
		10: input.Key.ProofThumbprint[:], 11: input.NotBefore, 12: input.Intent.ExpiresAt,
		13: input.Intent.LeaseID[:], 14: input.Intent.RecordSequence, 15: input.Key.PolicyHash[:], 16: input.Nonce[:],
	})
	if err != nil {
		return nil, ErrInvalidAuthority
	}
	protected, err := encodeCBOR(map[uint64]any{1: int64(-8), 4: append([]byte(nil), input.KID...)})
	if err != nil {
		return nil, ErrInvalidAuthority
	}
	structure, err := encodeCBOR([]any{"Signature1", protected, []byte{}, payload})
	if err != nil {
		return nil, ErrInvalidAuthority
	}
	wire, err := encodeCBOR([]any{protected, map[uint64]any{}, payload, ed25519.Sign(private, structure)})
	if err != nil {
		return nil, ErrInvalidAuthority
	}
	return append([]byte{0xd2}, wire...), nil
}

func stringsToAny(values []string) []any {
	result := make([]any, len(values))
	for index := range values {
		result[index] = values[index]
	}
	return result
}
