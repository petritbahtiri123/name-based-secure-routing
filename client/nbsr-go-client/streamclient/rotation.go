package streamclient

import (
	"context"
	"errors"
	"sync"
	"time"

	"nbsr.local/client/nbsr-go-client/internal/authority"
	"nbsr.local/client/nbsr-go-client/internal/corestate"
	"nbsr.local/client/nbsr-go-client/internal/identity"
	"nbsr.local/client/nbsr-go-client/internal/session"
)

// GenerationSession is the concrete transport boundary used by the production
// ownership manager. Each value must own one distinct live Transport Session.
type GenerationSession interface {
	Close() error
	Identity() string
	Open(context.Context) (Wire, uint64, error)
	Refill(context.Context, [16]byte, uint64) error
}

type GenerationConfig struct {
	Generation, ChannelGeneration uint64
	ChannelID                     [16]byte
	ProofThumbprint               [32]byte
	Factory                       func(context.Context) (GenerationSession, error)
}
type RotationTrigger = session.RotationTrigger

const RotationExplicit = session.RotationExplicit

var ErrGenerationCapacity = session.ErrGenerationCapacity

type ApplicationStreamState = session.ApplicationStreamState

const (
	ApplicationStreamAccepted = session.ApplicationStreamAccepted
	ApplicationStreamClosed   = session.ApplicationStreamClosed
)

type RotationClientConfig struct {
	Now, ExpiresAt, AuthorityGeneration                          uint64
	DeviceID, PolicyDigest, ServiceDigest, RouteGrantDigest      [32]byte
	SourceOperator, Gateway, ServiceIdentity, Profile, Transport string
	DrainTimeout                                                 time.Duration
	Generations                                                  []GenerationConfig
}

type liveTransport struct{ session GenerationSession }

func (transport *liveTransport) Close() error { return transport.session.Close() }

type rotationConnector struct {
	mu       sync.Mutex
	configs  map[corestate.TSGeneration]GenerationConfig
	sessions map[corestate.TSGeneration]GenerationSession
}

func (connector *rotationConnector) Connect(ctx context.Context, attempt session.TransportSessionAttempt) (session.Transport, error) {
	connector.mu.Lock()
	config, ok := connector.configs[attempt.Generation]
	connector.mu.Unlock()
	if !ok || config.Factory == nil {
		return nil, session.ErrInvalidSession
	}
	live, err := config.Factory(ctx)
	if err != nil || live == nil {
		if live != nil {
			_ = live.Close()
		}
		return nil, err
	}
	connector.mu.Lock()
	if connector.sessions[attempt.Generation] != nil {
		connector.mu.Unlock()
		_ = live.Close()
		return nil, session.ErrGenerationClosed
	}
	connector.sessions[attempt.Generation] = live
	connector.mu.Unlock()
	return &liveTransport{session: live}, nil
}

type rotationOpener struct{ connector *rotationConnector }

func (opener rotationOpener) Open(_ context.Context, transport session.Transport, attempt session.ServiceChannelAttempt) (session.WireChannel, error) {
	live, ok := transport.(*liveTransport)
	if !ok || live.session == nil {
		return nil, session.ErrTransport
	}
	config := opener.connector.configs[attempt.Generation]
	if config.ChannelID != [16]byte(attempt.ChannelID) {
		return nil, session.ErrChannelBinding
	}
	channel := &ownedWireChannel{id: attempt.ChannelID, generation: config.ChannelGeneration, profile: ProfileID}
	channel.open = func(ctx context.Context) (Wire, uint64, error) { return live.session.Open(ctx) }
	channel.refill = func(ctx context.Context, epoch uint64) error {
		return live.session.Refill(ctx, config.ChannelID, epoch)
	}
	return channel, nil
}

type RotationClient struct {
	manager   *session.Manager
	gate      *fixedGate
	connector *rotationConnector
	reuse     session.ReuseKey
	configs   map[corestate.TSGeneration]GenerationConfig
	handles   map[corestate.TSGeneration]corestate.ServiceHandle
	common    RotationClientConfig
}

func NewRotationClient(ctx context.Context, config RotationClientConfig) (*RotationClient, error) {
	if ctx == nil || len(config.Generations) < 2 || config.Now >= config.ExpiresAt || config.DrainTimeout <= 0 || config.AuthorityGeneration == 0 {
		return nil, session.ErrInvalidSession
	}
	deviceKey := identity.KeyRef{ID: filled(1), Purpose: identity.PurposeDeviceACPRequest, Generation: 1, Thumbprint: filled(2)}
	device := identity.DeviceIdentity{ID: config.DeviceID, SourceOperatorID: config.SourceOperator, CredentialGeneration: 1, CredentialNotBefore: config.Now - 1, CredentialExpiresAt: config.ExpiresAt, SigningKey: deviceKey}
	proofs := make([]identity.TSProofKey, 0, len(config.Generations))
	configs := make(map[corestate.TSGeneration]GenerationConfig, len(config.Generations))
	for _, generation := range config.Generations {
		if generation.Generation == 0 || generation.ChannelGeneration == 0 || generation.ChannelID == ([16]byte{}) || generation.ProofThumbprint == ([32]byte{}) || generation.Factory == nil {
			return nil, session.ErrInvalidSession
		}
		value := corestate.TSGeneration(generation.Generation)
		if _, exists := configs[value]; exists {
			return nil, session.ErrInvalidSession
		}
		configs[value] = generation
		proofs = append(proofs, identity.TSProofKey{TSGeneration: generation.Generation, Key: identity.KeyRef{ID: filled(byte(30 + generation.Generation)), Purpose: identity.PurposeTSProof, Generation: generation.Generation, Thumbprint: generation.ProofThumbprint}})
	}
	registry, err := identity.NewMemoryRegistry(device, nil, proofs, identity.LocalStateIntegrityKey{Key: identity.KeyRef{ID: filled(4), Purpose: identity.PurposeLocalStateIntegrity, Generation: 1, Thumbprint: filled(5)}})
	if err != nil {
		return nil, err
	}
	connector := &rotationConnector{configs: configs, sessions: make(map[corestate.TSGeneration]GenerationSession)}
	gate := &fixedGate{generation: authority.AuthorityGeneration(config.AuthorityGeneration), expires: config.ExpiresAt, grant: corestate.RouteGrantDigest(config.RouteGrantDigest), valid: true}
	limits := session.Limits{MaxReuseKeys: 1, MaxSessions: 2, MaxChannels: 2, MaxPendingSessions: 1, MaxPendingChannels: 1, MaxWaitersPerChannel: 1, MaxStreams: 64, MaxPendingAdmissions: 16, MaxReuseKeyBytes: 512, MaxServiceIdentityBytes: 256, MaxStateBytes: 64 * 1024, MaxRotationWaiters: 1, MaxRecoveryAttempts: 2, DrainTimeout: config.DrainTimeout, RecoveryBackoff: 100 * time.Millisecond}
	manager, err := session.NewManagerWithBarrier(limits, fixedClock{config.Now}, gate, registry, connector, rotationOpener{connector})
	if err != nil {
		return nil, err
	}
	reuse := session.ReuseKey{SourceOperator: config.SourceOperator, Gateway: config.Gateway, Profile: config.Profile, Transport: config.Transport, DeviceID: config.DeviceID, DeviceGeneration: 1, PolicyDigest: config.PolicyDigest, PolicyGeneration: 1}
	client := &RotationClient{manager: manager, gate: gate, connector: connector, reuse: reuse, configs: configs, handles: make(map[corestate.TSGeneration]corestate.ServiceHandle), common: config}
	first := config.Generations[0]
	if _, err = manager.CreateTransportSession(ctx, client.spec(first)); err != nil {
		return nil, err
	}
	if err = client.openChannel(ctx, corestate.TSGeneration(first.Generation)); err != nil {
		_ = manager.CloseTransportSession(corestate.TSGeneration(first.Generation))
		return nil, err
	}
	return client, nil
}

func (client *RotationClient) spec(config GenerationConfig) session.TransportSessionSpec {
	proof := identity.TSProofKey{TSGeneration: config.Generation, Key: identity.KeyRef{ID: filled(byte(30 + config.Generation)), Purpose: identity.PurposeTSProof, Generation: config.Generation, Thumbprint: config.ProofThumbprint}}
	return session.TransportSessionSpec{Generation: corestate.TSGeneration(config.Generation), ReuseKey: client.reuse, Proof: proof}
}
func (client *RotationClient) openChannel(ctx context.Context, generation corestate.TSGeneration) error {
	config := client.configs[generation]
	snapshot, err := client.manager.CreateServiceChannel(ctx, session.ServiceChannelRequest{Generation: generation, ChannelID: corestate.ChannelID(config.ChannelID), ServiceIdentity: client.common.ServiceIdentity, ServiceDigest: corestate.ServiceDigest(client.common.ServiceDigest), RouteGrantDigest: corestate.RouteGrantDigest(client.common.RouteGrantDigest), AuthorityGeneration: corestate.AuthorityGeneration(client.common.AuthorityGeneration), ProofThumbprint: authority.ProofKeyThumbprint(config.ProofThumbprint)})
	if err == nil {
		client.handles[generation] = snapshot.Handle
	}
	return err
}
func (client *RotationClient) Rotate(ctx context.Context, generation uint64, trigger session.RotationTrigger) (session.RotationResult, error) {
	current, err := client.manager.CurrentTransportSession(client.reuse)
	if err != nil {
		return session.RotationResult{}, err
	}
	config, ok := client.configs[corestate.TSGeneration(generation)]
	if !ok {
		return session.RotationResult{}, session.ErrInvalidSession
	}
	result, err := client.manager.RotateTransportSession(ctx, session.RotationRequest{CurrentGeneration: current.Generation, Replacement: client.spec(config), Trigger: trigger})
	if err != nil {
		return result, err
	}
	if err = client.openChannel(ctx, result.Current.Generation); err != nil {
		_ = client.manager.CloseTransportSession(result.Current.Generation)
		return session.RotationResult{}, err
	}
	return result, nil
}
func (client *RotationClient) Open(ctx context.Context, generation uint64) (*session.ApplicationStream, error) {
	g := corestate.TSGeneration(generation)
	return client.manager.OpenApplicationStream(ctx, g, client.handles[g])
}
func (client *RotationClient) CloseGeneration(generation uint64) error {
	return client.manager.CloseTransportSession(corestate.TSGeneration(generation))
}
func (client *RotationClient) Current() (session.TransportSessionSnapshot, error) {
	return client.manager.CurrentTransportSession(client.reuse)
}
func (client *RotationClient) TransportIdentity(generation uint64) string {
	client.connector.mu.Lock()
	defer client.connector.mu.Unlock()
	value := client.connector.sessions[corestate.TSGeneration(generation)]
	if value == nil {
		return ""
	}
	return value.Identity()
}

type DrainingRejections struct{ ServiceChannel, Credit, Refill, ApplicationStream bool }

func (client *RotationClient) ProbeDraining(ctx context.Context, generation uint64) DrainingRejections {
	g := corestate.TSGeneration(generation)
	config := client.configs[g]
	_, scErr := client.manager.CreateServiceChannel(ctx, session.ServiceChannelRequest{Generation: g, ChannelID: corestate.ChannelID(config.ChannelID), ServiceIdentity: client.common.ServiceIdentity, ServiceDigest: corestate.ServiceDigest(client.common.ServiceDigest), RouteGrantDigest: corestate.RouteGrantDigest(client.common.RouteGrantDigest), AuthorityGeneration: corestate.AuthorityGeneration(client.common.AuthorityGeneration), ProofThumbprint: authority.ProofKeyThumbprint(config.ProofThumbprint)})
	_, creditErr := client.manager.ReserveStreamCredit(g, client.handles[g])
	_, refillErr := client.manager.BeginCreditRefill(g, client.handles[g])
	_, streamErr := client.manager.OpenApplicationStream(ctx, g, client.handles[g])
	return DrainingRejections{ServiceChannel: errors.Is(scErr, session.ErrGenerationNotCurrent), Credit: errors.Is(creditErr, session.ErrCreditClosed), Refill: errors.Is(refillErr, session.ErrCreditClosed), ApplicationStream: errors.Is(streamErr, session.ErrStreamClosed)}
}
func (client *RotationClient) Usage() session.Usage { return client.manager.Usage() }
