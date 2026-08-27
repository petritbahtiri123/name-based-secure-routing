package client

import (
	"context"
	"crypto/tls"
	"sync/atomic"
	"time"

	"nbsr.local/client/nbsr-go-client/demo/internal/fixture"
	"nbsr.local/client/nbsr-go-client/internal/authority"
	"nbsr.local/client/nbsr-go-client/internal/identity"
)

type Option func(*options)
type options struct{ tls *tls.Config }

func WithTLSConfig(value *tls.Config) Option { return func(o *options) { o.tls = value } }

type AuthorityClient struct {
	manager  *authority.Manager
	provider *authority.HTTPProvider
	now      uint64
}

type AuthorityClientConfig struct {
	Endpoint                string
	TLSConfig               *tls.Config
	SourceOperator, Profile string
	DeviceID                [32]byte
	DeviceGeneration        uint64
	DeviceSigner            identity.Signer
	Issuers                 *authority.StaticIssuerResolver
	Checkpoint              authority.CheckpointClaims
	NowUnix                 uint64
}

func NewAuthorityClient(server *fixture.Server, opts ...Option) (*AuthorityClient, error) {
	var cfg options
	for _, apply := range opts {
		apply(&cfg)
	}
	tlsConfig := server.ClientTLSConfig()
	if cfg.tls != nil {
		tlsConfig = cfg.tls.Clone()
	}
	request := server.AcquireRequest()
	return NewAuthorityClientFromConfig(AuthorityClientConfig{Endpoint: server.Endpoint(), TLSConfig: tlsConfig, SourceOperator: request.Key.SourceOperator, Profile: request.Key.Profile, DeviceID: request.Key.DeviceID, DeviceGeneration: request.Key.DeviceGeneration, DeviceSigner: server.DeviceSigner(), Issuers: server.Issuers(), Checkpoint: server.CheckpointClaims(), NowUnix: server.NowUnix()})
}

func NewAuthorityClientFromConfig(config AuthorityClientConfig) (*AuthorityClient, error) {
	if config.Endpoint == "" || config.TLSConfig == nil || config.DeviceSigner == nil || config.Issuers == nil || config.NowUnix == 0 {
		return nil, authority.ErrInvalidAuthority
	}
	requestIDs := &requestIDs{}
	provider, err := authority.NewHTTPProvider(authority.HTTPProviderConfig{Endpoint: config.Endpoint, TLSConfig: config.TLSConfig.Clone(), SourceOperator: config.SourceOperator, Profile: config.Profile, Signer: config.DeviceSigner, ResultIssuers: config.Issuers, RequestIDs: requestIDs, Options: authority.HTTPProviderOptions{MaxAttempts: 1, MaxConcurrent: 4, AttemptTimeout: 2 * time.Second}, NowUnix: func() uint64 { return config.NowUnix }})
	if err != nil {
		return nil, err
	}
	verifier, err := authority.NewVerifier(config.Issuers)
	if err != nil {
		_ = provider.Close()
		return nil, err
	}
	manager, err := authority.NewManager(authority.Limits{MaxCacheEntries: 8, MaxPending: 4, MaxWaitersPerPending: 4, MaxRequestRecords: 64, MaxCacheBytes: 1 << 20, MaxPendingBytes: 1 << 20, MaxRequestBytes: 1 << 20, MaxGrantBytes: 128 << 10, MaxCheckpointEvidenceBytes: 1024, MaxServiceIdentityBytes: 128}, fixedClock{config.NowUnix}, provider, verifier, checkpointVerifier{claims: config.Checkpoint}, authority.NewMemoryGenerationFloorStore(1024), discardObserver{})
	if err != nil {
		_ = provider.Close()
		return nil, err
	}
	freshness := authority.FreshnessRequest{SourceOperator: config.SourceOperator, Profile: config.Profile, DeviceID: config.DeviceID, DeviceGeneration: config.DeviceGeneration, DeadlineUnix: config.NowUnix + 30}
	supplied, err := provider.Freshness(context.Background(), freshness)
	if err != nil {
		_ = manager.Close()
		return nil, err
	}
	if _, err = manager.PublishFreshness(context.Background(), freshness, supplied); err != nil {
		_ = manager.Close()
		return nil, err
	}
	return &AuthorityClient{manager: manager, provider: provider, now: config.NowUnix}, nil
}

func (c *AuthorityClient) AcquireRoute(ctx context.Context, request authority.AcquireRequest) (authority.Reservation, error) {
	return c.manager.Acquire(ctx, request)
}
func (c *AuthorityClient) Manager() *authority.Manager { return c.manager }
func (c *AuthorityClient) Close() error {
	if c == nil || c.manager == nil {
		return authority.ErrInvalidAuthority
	}
	return c.manager.Close()
}

type fixedClock struct{ now uint64 }

func (c fixedClock) NowUnix() uint64 { return c.now }

type requestIDs struct{ next atomic.Uint64 }

func (r *requestIDs) NewRequestID() (authority.RequestID, error) {
	n := r.next.Add(1)
	return authority.RequestID{byte(n), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1}, nil
}

type checkpointVerifier struct{ claims authority.CheckpointClaims }

func (v checkpointVerifier) VerifyFreshnessEvidence(ctx context.Context, f authority.ProviderFreshness, r authority.FreshnessRequest, now uint64) (authority.CheckpointClaims, error) {
	if err := ctx.Err(); err != nil {
		return authority.CheckpointClaims{}, err
	}
	if f.SourceOperator != r.SourceOperator || f.Profile != r.Profile || string(f.Evidence) != "demo-freshness-v1" || now >= v.claims.FreshUntil {
		return authority.CheckpointClaims{}, authority.ErrStaleFreshness
	}
	return v.claims, nil
}

type discardObserver struct{}

func (discardObserver) Observe(authority.Event) {}
