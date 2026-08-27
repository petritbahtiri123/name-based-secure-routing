package client

import (
	"crypto/sha256"
	"errors"
	"net/netip"
	"time"

	"nbsr.local/client/nbsr-go-client/demo/internal/bootstrap"
	democonfig "nbsr.local/client/nbsr-go-client/demo/internal/config"
	"nbsr.local/client/nbsr-go-client/internal/authority"
	"nbsr.local/client/nbsr-go-client/internal/corestate"
	"nbsr.local/client/nbsr-go-client/internal/identity"
	"nbsr.local/client/nbsr-go-client/internal/resolution"
	"nbsr.local/client/nbsr-go-client/internal/session"
	"nbsr.local/interop/nbsr-go-peer/wirepeer"
)

type StandaloneAssembly struct {
	Runtime   *Runtime
	Opener    *SecureRouteOpener
	Authority *AuthorityClient
	Sessions  *session.Manager
}

func NewStandaloneAssembly(configuration democonfig.Config, enrolled bootstrap.State, service democonfig.ServiceFixture, readiness wirepeer.Readiness) (*StandaloneAssembly, error) {
	if enrolled.Classification != bootstrap.Classification || configuration.Client.ACPEndpoint != enrolled.Endpoint || service.Classification != democonfig.DemoFixtureClassification || service.ServiceIdentity != enrolled.AcquireTemplate.Intent.ServiceIdentity || service.Transport != enrolled.AcquireTemplate.Intent.Transport || service.Port != enrolled.AcquireTemplate.Intent.Port {
		return nil, errors.New("standalone demo binding mismatch")
	}
	proof, err := NewTSProofOwner(enrolled.TSProofPrivate, uint64(enrolled.AcquireTemplate.Key.TSGeneration))
	if err != nil || authority.ProofKeyThumbprint(proof.KeyRef().Thumbprint) != enrolled.AcquireTemplate.Key.ProofThumbprint {
		return nil, session.ErrProofBinding
	}
	authorityClient, err := NewAuthorityClientFromConfig(AuthorityClientConfig{Endpoint: enrolled.Endpoint, TLSConfig: enrolled.TLSConfig, SourceOperator: enrolled.AcquireTemplate.Key.SourceOperator, Profile: enrolled.AcquireTemplate.Key.Profile, DeviceID: enrolled.AcquireTemplate.Key.DeviceID, DeviceGeneration: enrolled.AcquireTemplate.Key.DeviceGeneration, DeviceSigner: enrolled.DeviceSigner, Issuers: enrolled.Issuers, Checkpoint: enrolled.Checkpoint, NowUnix: enrolled.NowUnix})
	if err != nil {
		return nil, err
	}
	fail := func(err error) (*StandaloneAssembly, error) { _ = authorityClient.Close(); return nil, err }
	proofKey := identity.TSProofKey{TSGeneration: uint64(enrolled.AcquireTemplate.Key.TSGeneration), Key: proof.KeyRef()}
	local := identity.LocalStateIntegrityKey{Key: identity.KeyRef{ID: sha256.Sum256([]byte("task4-local-state")), Purpose: identity.PurposeLocalStateIntegrity, Generation: 1, Thumbprint: sha256.Sum256([]byte("task4-local-thumbprint"))}}
	registry, err := identity.NewMemoryRegistry(enrolled.AcquireTemplate.Device, nil, []identity.TSProofKey{proofKey}, local)
	if err != nil {
		return fail(err)
	}
	connector := &wireConnector{proof: proof, readiness: readiness, now: enrolled.NowUnix}
	channelOpener := &wireChannelOpener{proof: proof, issuerKID: enrolled.RouteIssuerKID, issuerPublicKey: enrolled.RouteIssuerPublic, now: enrolled.NowUnix}
	sessions, err := session.NewManager(task4SessionLimits(), fixedClock{enrolled.NowUnix}, authorityClient.Manager(), registry, connector, channelOpener)
	if err != nil {
		return fail(err)
	}
	spec := session.TransportSessionSpec{Generation: corestate.TSGeneration(enrolled.AcquireTemplate.Key.TSGeneration), ReuseKey: session.ReuseKey{SourceOperator: enrolled.AcquireTemplate.Key.SourceOperator, Gateway: "destination.edge", Profile: enrolled.AcquireTemplate.Key.Profile, Transport: "quic", DeviceID: enrolled.AcquireTemplate.Key.DeviceID, DeviceGeneration: enrolled.AcquireTemplate.Key.DeviceGeneration, PolicyDigest: enrolled.AcquireTemplate.Key.PolicyHash, PolicyGeneration: enrolled.AcquireTemplate.Key.PolicyGeneration}, Proof: proofKey}
	planner, err := NewSessionRoutePlanner(sessions, spec, proof)
	if err != nil {
		return fail(err)
	}
	opener, err := NewSecureRouteOpener(SecureRouteOpenerConfig{Authority: authorityClient, Sessions: sessions, Planner: planner, AcquireTemplate: enrolled.AcquireTemplate, ChannelID: corestate.ChannelID(sequence16(0x40))})
	if err != nil {
		return fail(err)
	}
	input := resolution.ResultInput{PresentationName: service.PresentationName, ServiceIdentity: service.ServiceIdentity, Intent: enrolled.AcquireTemplate.Intent, RecordExpiresAt: enrolled.AcquireTemplate.Intent.ExpiresAt}
	runtime, err := NewRuntime(RuntimeConfig{ListenAddress: configuration.Client.ProxyEndpoint, SharedSyntheticIP: netip.MustParseAddr(configuration.Client.SharedSyntheticIP), NowUnix: enrolled.NowUnix, MaxConnections: configuration.Limits.MaxProxyConnections, MaxRequestBytes: configuration.Limits.MaxRequestBytes}, input, opener)
	if err != nil {
		_ = opener.Close()
		return fail(err)
	}
	return &StandaloneAssembly{Runtime: runtime, Opener: opener, Authority: authorityClient, Sessions: sessions}, nil
}

func (assembly *StandaloneAssembly) Close() error {
	if assembly == nil {
		return nil
	}
	var runtimeErr error
	if assembly.Runtime != nil {
		runtimeErr = assembly.Runtime.Close()
	}
	var openerErr error
	if assembly.Opener != nil {
		openerErr = assembly.Opener.Close()
	}
	var authorityErr error
	if assembly.Authority != nil {
		authorityErr = assembly.Authority.Close()
	}
	return errors.Join(runtimeErr, openerErr, authorityErr)
}

func task4SessionLimits() session.Limits {
	return session.Limits{MaxReuseKeys: 1, MaxSessions: 2, MaxChannels: 2, MaxPendingSessions: 1, MaxPendingChannels: 1, MaxWaitersPerChannel: 1, MaxStreams: 4, MaxPendingAdmissions: 2, MaxReuseKeyBytes: 512, MaxServiceIdentityBytes: 128, MaxStateBytes: 64 << 10, MaxRotationWaiters: 1, MaxRecoveryAttempts: 1, DrainTimeout: 5 * time.Second, RecoveryBackoff: time.Millisecond}
}
