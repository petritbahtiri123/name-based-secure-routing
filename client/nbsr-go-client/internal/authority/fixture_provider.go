package authority

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/binary"
	"sync"
)

// FixtureProviderLimits bound the copied, local-only fixture script. They do
// not configure an authority service and cannot be used to create authority.
type FixtureProviderLimits struct {
	MaxEntries int
	MaxBytes   uint64
	MaxCalls   uint64
}

// FixtureGrant is a pre-signed provider candidate selected by one exact local
// request digest and operation. Operation is pendingAcquire or pendingRenew.
type FixtureGrant struct {
	Operation     uint8
	RequestDigest [32]byte
	Result        ProviderGrant
	Err           error
}

// FixtureFreshness is semantic fixture evidence selected by one exact local
// freshness request digest. Claims are interpreted only by the fixture
// checkpoint verifier below; no production checkpoint encoding is defined.
type FixtureFreshness struct {
	RequestDigest [32]byte
	Result        ProviderFreshness
	Claims        CheckpointClaims
	Err           error
}

type fixtureGrantKey struct {
	operation     pendingOperation
	requestDigest [32]byte
}

const (
	maxFixtureCheckpointEntries = 256
	maxFixtureCheckpointBytes   = 1 << 20
)

// FixtureProvider is finite deterministic test wiring. It has no signer,
// private key, network client, federation input, or background work.
type FixtureProvider struct {
	mu sync.Mutex

	limits FixtureProviderLimits
	grants map[fixtureGrantKey]FixtureGrant
	fresh  map[[32]byte]FixtureFreshness
	calls  uint64
	closed bool
}

var _ AuthorityProvider = (*FixtureProvider)(nil)

func NewFixtureProvider(limits FixtureProviderLimits, grants []FixtureGrant, freshness []FixtureFreshness) (*FixtureProvider, error) {
	if limits.MaxEntries <= 0 || limits.MaxBytes == 0 || limits.MaxCalls == 0 {
		return nil, ErrInvalidLimits
	}
	if len(grants)+len(freshness) > limits.MaxEntries {
		return nil, ErrCacheCapacity
	}
	provider := &FixtureProvider{limits: limits, grants: make(map[fixtureGrantKey]FixtureGrant, len(grants)), fresh: make(map[[32]byte]FixtureFreshness, len(freshness))}
	var used uint64
	for _, fixture := range grants {
		operation := pendingOperation(fixture.Operation)
		if (operation != pendingAcquire && operation != pendingRenew) || fixture.RequestDigest == ([32]byte{}) {
			return nil, ErrInvalidAuthority
		}
		copied, bytesUsed, err := copyFixtureGrant(fixture)
		if err != nil || bytesUsed > limits.MaxBytes-used {
			if err != nil {
				return nil, err
			}
			return nil, ErrCacheCapacity
		}
		key := fixtureGrantKey{operation: operation, requestDigest: fixture.RequestDigest}
		if _, exists := provider.grants[key]; exists {
			return nil, ErrInvalidAuthority
		}
		provider.grants[key] = copied
		used += bytesUsed
	}
	for _, fixture := range freshness {
		if fixture.RequestDigest == ([32]byte{}) {
			return nil, ErrInvalidAuthority
		}
		copied, bytesUsed, err := copyFixtureFreshness(fixture)
		if err != nil || bytesUsed > limits.MaxBytes-used {
			if err != nil {
				return nil, err
			}
			return nil, ErrCacheCapacity
		}
		if _, exists := provider.fresh[fixture.RequestDigest]; exists {
			return nil, ErrInvalidAuthority
		}
		provider.fresh[fixture.RequestDigest] = copied
		used += bytesUsed
	}
	return provider, nil
}

func (provider *FixtureProvider) Acquire(ctx context.Context, request AcquireRequest) (ProviderGrant, error) {
	return provider.grant(ctx, pendingAcquire, request, RenewRequest{})
}

func (provider *FixtureProvider) Renew(ctx context.Context, request RenewRequest) (ProviderGrant, error) {
	return provider.grant(ctx, pendingRenew, request.AcquireRequest, request)
}

func (provider *FixtureProvider) grant(ctx context.Context, operation pendingOperation, request AcquireRequest, renew RenewRequest) (ProviderGrant, error) {
	if err := fixtureContextError(ctx); err != nil {
		return ProviderGrant{}, err
	}
	if provider == nil {
		return ProviderGrant{}, ErrInvalidAuthority
	}
	digest := fixtureGrantDigest(operation, request, renew)
	provider.mu.Lock()
	if provider.closed {
		provider.mu.Unlock()
		return ProviderGrant{}, ErrClosed
	}
	if provider.calls >= provider.limits.MaxCalls {
		provider.mu.Unlock()
		return ProviderGrant{}, ErrProviderUnavailable
	}
	provider.calls++
	fixture, ok := provider.grants[fixtureGrantKey{operation: operation, requestDigest: digest}]
	provider.mu.Unlock()
	if !ok {
		return ProviderGrant{}, ErrProviderUnavailable
	}
	if fixture.Err != nil {
		return ProviderGrant{}, typedFixtureError(fixture.Err)
	}
	result, _, err := copyFixtureGrant(fixture)
	if err != nil {
		return ProviderGrant{}, err
	}
	return result.Result, nil
}

func (provider *FixtureProvider) Freshness(ctx context.Context, request FreshnessRequest) (ProviderFreshness, error) {
	if err := fixtureContextError(ctx); err != nil {
		return ProviderFreshness{}, err
	}
	if provider == nil {
		return ProviderFreshness{}, ErrInvalidAuthority
	}
	digest := fixtureFreshnessRequestDigest(request)
	provider.mu.Lock()
	if provider.closed {
		provider.mu.Unlock()
		return ProviderFreshness{}, ErrClosed
	}
	if provider.calls >= provider.limits.MaxCalls {
		provider.mu.Unlock()
		return ProviderFreshness{}, ErrProviderUnavailable
	}
	provider.calls++
	fixture, ok := provider.fresh[digest]
	provider.mu.Unlock()
	if !ok {
		return ProviderFreshness{}, ErrProviderUnavailable
	}
	if fixture.Err != nil {
		return ProviderFreshness{}, typedFixtureError(fixture.Err)
	}
	result, _, err := copyFixtureFreshness(fixture)
	if err != nil {
		return ProviderFreshness{}, err
	}
	return result.Result, nil
}

// Close is idempotent and never invokes external code.
func (provider *FixtureProvider) Close() error {
	if provider == nil {
		return ErrInvalidAuthority
	}
	provider.mu.Lock()
	provider.closed = true
	provider.mu.Unlock()
	return nil
}

type fixtureCheckpointVerifier struct{ fixtures map[[32]byte]FixtureFreshness }

var _ CheckpointEvidenceVerifier = (*fixtureCheckpointVerifier)(nil)

func NewFixtureCheckpointVerifier(fixtures []FixtureFreshness) (CheckpointEvidenceVerifier, error) {
	if len(fixtures) > maxFixtureCheckpointEntries {
		return nil, ErrCacheCapacity
	}
	verifier := &fixtureCheckpointVerifier{fixtures: make(map[[32]byte]FixtureFreshness, len(fixtures))}
	var used uint64
	for _, fixture := range fixtures {
		if fixture.RequestDigest == ([32]byte{}) {
			return nil, ErrInvalidAuthority
		}
		copied, bytesUsed, err := copyFixtureFreshness(fixture)
		if err != nil {
			return nil, err
		}
		if bytesUsed > maxFixtureCheckpointBytes-used {
			return nil, ErrCacheCapacity
		}
		if _, exists := verifier.fixtures[fixture.RequestDigest]; exists {
			return nil, ErrInvalidAuthority
		}
		verifier.fixtures[fixture.RequestDigest] = copied
		used += bytesUsed
	}
	return verifier, nil
}

func (verifier *fixtureCheckpointVerifier) VerifyFreshnessEvidence(ctx context.Context, freshness ProviderFreshness, request FreshnessRequest, _ uint64) (CheckpointClaims, error) {
	if err := fixtureContextError(ctx); err != nil {
		return CheckpointClaims{}, err
	}
	if verifier == nil {
		return CheckpointClaims{}, ErrInvalidAuthority
	}
	fixture, ok := verifier.fixtures[fixtureFreshnessRequestDigest(request)]
	if !ok || !sameProviderFreshness(fixture.Result, freshness) {
		return CheckpointClaims{}, ErrProviderUnavailable
	}
	if fixture.Err != nil {
		return CheckpointClaims{}, typedFixtureError(fixture.Err)
	}
	claims, err := copyFixtureClaims(fixture.Claims)
	if err != nil {
		return CheckpointClaims{}, err
	}
	return claims, nil
}

func fixtureGrantRequestDigest(request AcquireRequest) [32]byte {
	return fixtureGrantDigest(pendingAcquire, request, RenewRequest{})
}

func fixtureGrantDigest(operation pendingOperation, request AcquireRequest, renew RenewRequest) [32]byte {
	base := canonicalRequestDigest(pendingKey{authority: request.Key, operation: operation, previous: renew.PreviousGrant}, request, renew)
	hash := sha256.New()
	_, _ = hash.Write([]byte("NBSR-GO-CLIENT-FIXTURE-GRANT-v1\x00"))
	_, _ = hash.Write(base[:])
	_, _ = hash.Write(request.RequestID[:])
	var digest [32]byte
	copy(digest[:], hash.Sum(nil))
	return digest
}

func fixtureFreshnessRequestDigest(request FreshnessRequest) [32]byte {
	hash := sha256.New()
	_, _ = hash.Write([]byte("NBSR-GO-CLIENT-FIXTURE-FRESHNESS-v1\x00"))
	write := func(value []byte) {
		var length [8]byte
		binary.BigEndian.PutUint64(length[:], uint64(len(value)))
		_, _ = hash.Write(length[:])
		_, _ = hash.Write(value)
	}
	write([]byte(request.SourceOperator))
	write([]byte(request.Profile))
	write(request.DeviceID[:])
	var integer [8]byte
	for _, value := range []uint64{request.DeviceGeneration, uint64(request.AfterGeneration), request.DeadlineUnix} {
		binary.BigEndian.PutUint64(integer[:], value)
		write(integer[:])
	}
	write(request.AfterCheckpoint[:])
	var digest [32]byte
	copy(digest[:], hash.Sum(nil))
	return digest
}

func copyFixtureGrant(fixture FixtureGrant) (FixtureGrant, uint64, error) {
	if fixture.Err == nil {
		if len(fixture.Result.ExactRouteGrant) == 0 || fixture.Result.Profile == "" || fixture.Result.AuthorityGeneration == 0 || fixture.Result.Checkpoint == (CheckpointDigest{}) {
			return FixtureGrant{}, 0, ErrInvalidAuthority
		}
	}
	fixture.Result.ExactRouteGrant = append([]byte(nil), fixture.Result.ExactRouteGrant...)
	const fixed = 32 + 1 + 32 + 8
	return fixture, uint64(len(fixture.Result.ExactRouteGrant) + len(fixture.Result.Profile) + fixed), nil
}

func copyFixtureFreshness(fixture FixtureFreshness) (FixtureFreshness, uint64, error) {
	if fixture.Err == nil {
		if fixture.Result.SourceOperator == "" || fixture.Result.Profile == "" || len(fixture.Result.Evidence) == 0 {
			return FixtureFreshness{}, 0, ErrInvalidAuthority
		}
		if _, err := copyFixtureClaims(fixture.Claims); err != nil {
			return FixtureFreshness{}, 0, err
		}
	}
	fixture.Result.Evidence = append([]byte(nil), fixture.Result.Evidence...)
	fixture.Claims.RevokedGrants = append([]RouteGrantDigest(nil), fixture.Claims.RevokedGrants...)
	const fixed = 32 + 32 + 8*3
	return fixture, uint64(len(fixture.Result.SourceOperator) + len(fixture.Result.Profile) + len(fixture.Result.Evidence) + len(fixture.Claims.SourceOperator) + len(fixture.Claims.Profile) + len(fixture.Claims.RevokedGrants)*32 + fixed), nil
}

func copyFixtureClaims(claims CheckpointClaims) (CheckpointClaims, error) {
	if _, err := sealCheckpoint(claims, Limits{MaxCacheEntries: 256}); err != nil {
		return CheckpointClaims{}, err
	}
	claims.RevokedGrants = append([]RouteGrantDigest(nil), claims.RevokedGrants...)
	return claims, nil
}

func sameProviderFreshness(left, right ProviderFreshness) bool {
	return left.SourceOperator == right.SourceOperator && left.Profile == right.Profile && bytes.Equal(left.Evidence, right.Evidence)
}

func fixtureContextError(ctx context.Context) error {
	if ctx == nil {
		return ErrInvalidAuthority
	}
	if err := ctx.Err(); err != nil {
		return err
	}
	return nil
}

func typedFixtureError(err error) error {
	if typed, ok := err.(*AuthorityError); ok {
		return typed
	}
	return ErrProviderUnavailable
}
