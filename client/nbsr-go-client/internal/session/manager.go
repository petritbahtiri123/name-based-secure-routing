package session

import (
	"context"
	"errors"
	"math"
	"sync"
	"time"

	"nbsr.local/client/nbsr-go-client/internal/authority"
	"nbsr.local/client/nbsr-go-client/internal/corestate"
	"nbsr.local/client/nbsr-go-client/internal/identity"
)

type AuthorityBarrier interface {
	Capture() (authority.AuthorityGeneration, error)
	Validate(authority.AuthorityGeneration) error
	ValidateSession(ReuseKey, authority.AuthorityGeneration) error
	Preflight(ServiceChannelRequest, authority.AuthorityGeneration, uint64) ([]byte, error)
	Commit(ServiceChannelRequest, authority.AuthorityGeneration, uint64) (AuthorityToken, error)
	CommitApplication(AuthorityToken, authority.AdmissionOwner, uint64, func() error) error
}

type AuthorityToken struct {
	handle     authority.AuthorityHandle
	Generation authority.AuthorityGeneration
	Grant      corestate.RouteGrantDigest
	Revision   uint64
}

type managerAuthority struct{ manager *authority.Manager }

func (gate managerAuthority) Capture() (authority.AuthorityGeneration, error) {
	snapshot, err := gate.manager.CaptureGeneration()
	if err != nil {
		return 0, err
	}
	return snapshot.Generation(), nil
}
func (gate managerAuthority) Validate(generation authority.AuthorityGeneration) error {
	return gate.manager.ValidateGeneration(generation)
}
func (gate managerAuthority) ValidateSession(key ReuseKey, generation authority.AuthorityGeneration) error {
	return gate.manager.ValidateSessionBinding(generation, key.SourceOperator, key.Profile)
}
func (gate managerAuthority) Preflight(request ServiceChannelRequest, generation authority.AuthorityGeneration, now uint64) ([]byte, error) {
	if request.Reservation.TSGeneration() != authority.TSGeneration(request.Generation) || request.Reservation.AuthorityGeneration() != generation {
		return nil, authority.ErrBindingMismatch
	}
	return gate.manager.AdmissionMaterialForGeneration(request.Reservation, generation, request.ServiceIdentity, authority.ServiceDigest(request.ServiceDigest), request.ProofThumbprint, authority.RouteGrantDigest(request.RouteGrantDigest), now)
}
func (gate managerAuthority) Commit(request ServiceChannelRequest, generation authority.AuthorityGeneration, now uint64) (AuthorityToken, error) {
	handle, err := gate.manager.ConsumeForGeneration(request.Reservation, authority.AdmissionOwner{TSGeneration: authority.TSGeneration(request.Generation), ChannelID: [16]byte(request.ChannelID)}, generation, now)
	return AuthorityToken{handle: handle, Generation: generation, Grant: request.RouteGrantDigest, Revision: 1}, err
}
func (gate managerAuthority) CommitApplication(token AuthorityToken, owner authority.AdmissionOwner, now uint64, commit func() error) error {
	return gate.manager.ValidateHandleAndCommit(token.handle, owner, now, commit)
}

type transportEntry struct {
	snapshot       TransportSessionSnapshot
	transport      Transport
	nextHandle     corestate.ServiceHandle
	channels       map[corestate.ServiceHandle]*channelEntry
	byWire         map[corestate.ChannelID]corestate.ServiceHandle
	accountedBytes uint64
}
type channelEntry struct {
	snapshot       ServiceChannelSnapshot
	wire           WireChannel
	credits        creditWindow
	authority      AuthorityToken
	streams        map[corestate.StreamID]*ApplicationStream
	pending        map[uint64]*pendingAdmission
	accountedBytes uint64
}
type pendingChannel struct {
	done    chan struct{}
	waiters int
	request ServiceChannelRequest
	result  ServiceChannelSnapshot
	err     error
}
type channelKey struct {
	generation corestate.TSGeneration
	service    corestate.ServiceDigest
}

type Manager struct {
	mu                         sync.Mutex
	limits                     Limits
	clock                      Clock
	authority                  AuthorityBarrier
	registry                   identity.Registry
	connector                  Connector
	opener                     ChannelOpener
	sessions                   map[corestate.TSGeneration]*transportEntry
	byReuse                    map[ReuseKey]map[corestate.TSGeneration]*transportEntry
	pendingSessions            int
	pendingAdmissions          int
	nextPendingAdmission       uint64
	pendingChannels            map[channelKey]*pendingChannel
	highestGeneration          corestate.TSGeneration
	sessionBytes, channelBytes uint64
	streamBytes                uint64
	pendingRotations           map[ReuseKey]*pendingRotation
	effectiveTriggers          map[ReuseKey]RotationTrigger
	drainTimers                map[corestate.TSGeneration]*time.Timer
}

func NewManager(limits Limits, clock Clock, manager *authority.Manager, registry identity.Registry, connector Connector, opener ChannelOpener) (*Manager, error) {
	if manager == nil {
		return nil, ErrInvalidSession
	}
	return newManager(limits, clock, managerAuthority{manager}, registry, connector, opener)
}

func newManager(limits Limits, clock Clock, gate AuthorityBarrier, registry identity.Registry, connector Connector, opener ChannelOpener) (*Manager, error) {
	if err := limits.validate(); err != nil {
		return nil, err
	}
	if clock == nil || gate == nil || registry == nil || connector == nil || opener == nil {
		return nil, ErrInvalidSession
	}
	return &Manager{limits: limits, clock: clock, authority: gate, registry: registry, connector: connector, opener: opener, sessions: make(map[corestate.TSGeneration]*transportEntry), byReuse: make(map[ReuseKey]map[corestate.TSGeneration]*transportEntry), pendingChannels: make(map[channelKey]*pendingChannel), pendingRotations: make(map[ReuseKey]*pendingRotation), effectiveTriggers: make(map[ReuseKey]RotationTrigger), drainTimers: make(map[corestate.TSGeneration]*time.Timer)}, nil
}

// NewManagerWithBarrier wires an already-verified authority boundary into the
// production ownership manager. It is intended for concrete transport adapters.
func NewManagerWithBarrier(limits Limits, clock Clock, gate AuthorityBarrier, registry identity.Registry, connector Connector, opener ChannelOpener) (*Manager, error) {
	return newManager(limits, clock, gate, registry, connector, opener)
}

func (manager *Manager) CreateTransportSession(ctx context.Context, spec TransportSessionSpec) (TransportSessionSnapshot, error) {
	if ctx == nil {
		return TransportSessionSnapshot{}, ErrInvalidSession
	}
	generation, err := manager.authority.Capture()
	if err != nil {
		return TransportSessionSnapshot{}, authorityError(err)
	}
	device, proof, err := manager.validateSessionSpec(spec)
	if err != nil {
		return TransportSessionSnapshot{}, err
	}
	if err := manager.authority.ValidateSession(spec.ReuseKey, generation); err != nil {
		return TransportSessionSnapshot{}, sessionAuthorityError(err)
	}
	manager.mu.Lock()
	if err = manager.reserveSessionLocked(spec); err != nil {
		manager.mu.Unlock()
		return TransportSessionSnapshot{}, err
	}
	manager.pendingSessions++
	manager.mu.Unlock()
	transport, connectErr := manager.connector.Connect(ctx, TransportSessionAttempt{Generation: spec.Generation, ReuseKey: spec.ReuseKey, ProofKey: proof.Key, AuthorityGeneration: generation})
	if connectErr == nil && transport == nil {
		connectErr = ErrTransport
	}
	if connectErr == nil {
		connectErr = manager.authority.ValidateSession(spec.ReuseKey, generation)
	}
	if connectErr == nil {
		_, _, connectErr = manager.validateSessionSpec(spec)
	}
	manager.mu.Lock()
	manager.pendingSessions--
	if connectErr == nil {
		connectErr = manager.reserveSessionLocked(spec)
	}
	if connectErr == nil {
		snapshot := TransportSessionSnapshot{Generation: spec.Generation, ReuseKey: spec.ReuseKey, State: TransportCurrent, ProofThumbprint: proof.Key.Thumbprint, AuthorityGeneration: generation}
		entry := &transportEntry{snapshot: snapshot, transport: transport, nextHandle: 1, channels: make(map[corestate.ServiceHandle]*channelEntry), byWire: make(map[corestate.ChannelID]corestate.ServiceHandle)}
		entry.accountedBytes = transportSessionCost(spec)
		manager.sessions[spec.Generation] = entry
		if manager.byReuse[spec.ReuseKey] == nil {
			manager.byReuse[spec.ReuseKey] = make(map[corestate.TSGeneration]*transportEntry)
		}
		manager.byReuse[spec.ReuseKey][spec.Generation] = entry
		manager.highestGeneration = spec.Generation
		manager.sessionBytes += entry.accountedBytes
		manager.mu.Unlock()
		_ = device
		return snapshot, nil
	}
	manager.mu.Unlock()
	if transport != nil {
		_ = transport.Close()
	}
	return TransportSessionSnapshot{}, sessionAuthorityError(connectErr)
}

func (manager *Manager) validateSessionSpec(spec TransportSessionSpec) (identity.DeviceIdentity, identity.TSProofKey, error) {
	if spec.Generation == 0 || spec.ReuseKey.SourceOperator == "" || spec.ReuseKey.Gateway == "" || spec.ReuseKey.Profile == "" || spec.ReuseKey.Transport == "" || spec.ReuseKey.DeviceID == ([32]byte{}) || spec.ReuseKey.DeviceGeneration == 0 || spec.ReuseKey.PolicyDigest == ([32]byte{}) || spec.ReuseKey.PolicyGeneration == 0 {
		return identity.DeviceIdentity{}, identity.TSProofKey{}, ErrInvalidSession
	}
	if transportSessionCost(spec) > uint64(manager.limits.MaxReuseKeyBytes)+96 {
		return identity.DeviceIdentity{}, identity.TSProofKey{}, ErrSessionCapacity
	}
	device, err := manager.registry.Device()
	if err != nil || device.ID != spec.ReuseKey.DeviceID || device.SourceOperatorID != spec.ReuseKey.SourceOperator || device.CredentialGeneration != spec.ReuseKey.DeviceGeneration || manager.clock.NowUnix() >= device.CredentialExpiresAt {
		return identity.DeviceIdentity{}, identity.TSProofKey{}, ErrAuthorityStale
	}
	proof, err := manager.registry.TSProof(uint64(spec.Generation))
	local, localErr := manager.registry.LocalStateIntegrity()
	if err != nil || localErr != nil || proof != spec.Proof || proof.TSGeneration != uint64(spec.Generation) || proof.Key.Purpose != identity.PurposeTSProof || proof.Key.Generation != uint64(spec.Generation) || proof.Key.ID == ([32]byte{}) || proof.Key.Thumbprint == ([32]byte{}) || proof.Key.ID == device.SigningKey.ID || proof.Key.ID == local.Key.ID {
		return identity.DeviceIdentity{}, identity.TSProofKey{}, ErrProofBinding
	}
	return device, proof, nil
}

func (manager *Manager) reserveSessionLocked(spec TransportSessionSpec) error {
	if spec.Generation <= manager.highestGeneration || manager.sessions[spec.Generation] != nil {
		return ErrGenerationClosed
	}
	if len(manager.sessions)+manager.pendingSessions >= manager.limits.MaxSessions {
		return ErrSessionCapacity
	}
	cost := transportSessionCost(spec)
	if manager.sessionBytes+manager.channelBytes > manager.limits.MaxStateBytes || cost > manager.limits.MaxStateBytes-manager.sessionBytes-manager.channelBytes {
		return ErrSessionCapacity
	}
	group := manager.byReuse[spec.ReuseKey]
	if len(group) >= 2 {
		return ErrGenerationCapacity
	}
	if group == nil && len(manager.byReuse) >= manager.limits.MaxReuseKeys {
		return ErrSessionCapacity
	}
	for _, entry := range group {
		if entry.snapshot.State == TransportCurrent {
			return ErrGenerationNotCurrent
		}
	}
	if manager.pendingSessions >= manager.limits.MaxPendingSessions {
		return ErrPendingCapacity
	}
	return nil
}

func (manager *Manager) MarkDraining(generation corestate.TSGeneration) error {
	manager.mu.Lock()
	defer manager.mu.Unlock()
	entry := manager.sessions[generation]
	if entry == nil {
		return ErrGenerationClosed
	}
	entry.snapshot.State = TransportDraining
	manager.startDrainTimerLocked(generation)
	return nil
}

func (manager *Manager) CloseTransportSession(generation corestate.TSGeneration) error {
	manager.mu.Lock()
	if timer := manager.drainTimers[generation]; timer != nil {
		timer.Stop()
		delete(manager.drainTimers, generation)
	}
	entry := manager.sessions[generation]
	if entry == nil {
		manager.mu.Unlock()
		return nil
	}
	if pending := manager.pendingRotations[entry.snapshot.ReuseKey]; pending != nil {
		pending.cancel()
	}
	delete(manager.sessions, generation)
	manager.sessionBytes -= entry.accountedBytes
	group := manager.byReuse[entry.snapshot.ReuseKey]
	delete(group, generation)
	if len(group) == 0 {
		delete(manager.byReuse, entry.snapshot.ReuseKey)
	}
	wires := make([]WireChannel, 0, len(entry.channels))
	streams := make([]WireApplicationStream, 0)
	for _, channel := range entry.channels {
		wires = append(wires, channel.wire)
		for _, pending := range channel.pending {
			if pending.stop != nil {
				pending.stop()
			}
			pending.cancel()
			if pending.wire != nil {
				streams = append(streams, pending.wire)
			}
			manager.pendingAdmissions--
		}
		channel.pending = nil
		for _, stream := range channel.streams {
			stream.state.Store(uint32(ApplicationStreamClosed))
			streams = append(streams, stream.wire)
			manager.streamBytes -= applicationStreamCost
		}
		channel.streams = nil
		manager.channelBytes -= channel.accountedBytes
	}
	entry.channels = nil
	entry.byWire = nil
	manager.mu.Unlock()
	for _, stream := range streams {
		_ = stream.Close()
	}
	for _, wire := range wires {
		_ = wire.Close()
	}
	return entry.transport.Close()
}

func (manager *Manager) CreateServiceChannel(ctx context.Context, request ServiceChannelRequest) (ServiceChannelSnapshot, error) {
	if ctx == nil {
		return ServiceChannelSnapshot{}, ErrInvalidSession
	}
	key := channelKey{generation: request.Generation, service: request.ServiceDigest}
	manager.mu.Lock()
	entry := manager.sessions[request.Generation]
	if err := manager.validateChannelRequestLocked(entry, request, 0); err != nil {
		manager.mu.Unlock()
		return ServiceChannelSnapshot{}, err
	}
	if pending := manager.pendingChannels[key]; pending != nil {
		if pending.request != request {
			manager.mu.Unlock()
			return ServiceChannelSnapshot{}, ErrChannelBinding
		}
		if pending.waiters >= manager.limits.MaxWaitersPerChannel {
			manager.mu.Unlock()
			return ServiceChannelSnapshot{}, ErrPendingCapacity
		}
		pending.waiters++
		done := pending.done
		manager.mu.Unlock()
		select {
		case <-ctx.Done():
			manager.mu.Lock()
			if manager.pendingChannels[key] == pending && pending.waiters > 0 {
				pending.waiters--
			}
			manager.mu.Unlock()
			return ServiceChannelSnapshot{}, ctx.Err()
		case <-done:
			return pending.result, pending.err
		}
	}
	if len(manager.pendingChannels) >= manager.limits.MaxPendingChannels {
		manager.mu.Unlock()
		return ServiceChannelSnapshot{}, ErrPendingCapacity
	}
	pending := &pendingChannel{done: make(chan struct{}), request: request}
	manager.pendingChannels[key] = pending
	transport := entry.transport
	authorityGeneration := entry.snapshot.AuthorityGeneration
	manager.mu.Unlock()

	now := manager.clock.NowUnix()
	material, err := manager.authority.Preflight(request, authorityGeneration, now)
	var wire WireChannel
	if err == nil {
		wire, err = manager.opener.Open(ctx, transport, ServiceChannelAttempt{Generation: request.Generation, ChannelID: request.ChannelID, ServiceIdentity: request.ServiceIdentity, ServiceDigest: request.ServiceDigest, RouteGrant: request.RouteGrantDigest, ExactRouteGrant: material, ProofThumbprint: request.ProofThumbprint})
	}
	if err == nil && wire == nil {
		err = ErrTransport
	}
	if err == nil && (wire.ChannelID() != request.ChannelID || wire.ChannelGeneration() == 0) {
		err = ErrChannelBinding
	}
	if err == nil {
		err = manager.authority.Validate(authorityGeneration)
	}
	manager.mu.Lock()
	entry = manager.sessions[request.Generation]
	if err == nil {
		err = manager.validateChannelRequestLocked(entry, request, 1)
	}
	manager.mu.Unlock()
	var committedAuthority AuthorityToken
	if err == nil {
		committedAuthority, err = manager.authority.Commit(request, authorityGeneration, manager.clock.NowUnix())
	}
	manager.mu.Lock()
	entry = manager.sessions[request.Generation]
	if err == nil {
		err = manager.validateChannelRequestLocked(entry, request, 1)
	}
	var snapshot ServiceChannelSnapshot
	if err == nil {
		if entry.nextHandle == corestate.InvalidServiceHandle {
			err = ErrChannelCapacity
		} else {
			handle := entry.nextHandle
			if handle == corestate.ServiceHandle(math.MaxUint32) {
				entry.nextHandle = corestate.InvalidServiceHandle
			} else {
				entry.nextHandle++
			}
			snapshot = ServiceChannelSnapshot{Generation: request.Generation, Handle: handle, ChannelID: request.ChannelID, ChannelGeneration: wire.ChannelGeneration(), ServiceIdentity: request.ServiceIdentity, ServiceDigest: request.ServiceDigest, RouteGrantDigest: request.RouteGrantDigest, AuthorityGeneration: request.AuthorityGeneration}
			cost := serviceChannelCost(request)
			entry.channels[handle] = &channelEntry{snapshot: snapshot, wire: wire, credits: newCreditWindow(), authority: committedAuthority, streams: make(map[corestate.StreamID]*ApplicationStream), pending: make(map[uint64]*pendingAdmission), accountedBytes: cost}
			entry.byWire[request.ChannelID] = handle
			manager.channelBytes += cost
		}
	}
	delete(manager.pendingChannels, key)
	pending.result = snapshot
	pending.err = authorityError(err)
	close(pending.done)
	manager.mu.Unlock()
	if err != nil && wire != nil {
		_ = wire.Close()
	}
	return snapshot, authorityError(err)
}

func (manager *Manager) validateChannelRequestLocked(entry *transportEntry, request ServiceChannelRequest, excludePending int) error {
	if entry == nil {
		return ErrGenerationClosed
	}
	if entry.snapshot.State != TransportCurrent {
		return ErrGenerationNotCurrent
	}
	if request.ChannelID == (corestate.ChannelID{}) || request.ServiceIdentity == "" || request.ServiceDigest == (corestate.ServiceDigest{}) || request.RouteGrantDigest == (corestate.RouteGrantDigest{}) {
		return ErrServiceBinding
	}
	if len(request.ServiceIdentity) > manager.limits.MaxServiceIdentityBytes {
		return ErrChannelCapacity
	}
	if request.AuthorityGeneration != corestate.AuthorityGeneration(entry.snapshot.AuthorityGeneration) || request.ProofThumbprint != authority.ProofKeyThumbprint(entry.snapshot.ProofThumbprint) {
		return ErrAuthorityStale
	}
	if _, exists := entry.byWire[request.ChannelID]; exists {
		return ErrDuplicateChannel
	}
	pending := len(manager.pendingChannels) - excludePending
	if pending < 0 || manager.channelCountLocked()+pending >= manager.limits.MaxChannels {
		return ErrChannelCapacity
	}
	cost := serviceChannelCost(request)
	if manager.sessionBytes+manager.channelBytes > manager.limits.MaxStateBytes || cost > manager.limits.MaxStateBytes-manager.sessionBytes-manager.channelBytes {
		return ErrChannelCapacity
	}
	return nil
}

func (manager *Manager) CloseServiceChannel(generation corestate.TSGeneration, handle corestate.ServiceHandle) error {
	if handle == corestate.InvalidServiceHandle {
		return ErrChannelClosed
	}
	manager.mu.Lock()
	entry := manager.sessions[generation]
	if entry == nil {
		manager.mu.Unlock()
		return ErrChannelClosed
	}
	channel := entry.channels[handle]
	if channel == nil {
		manager.mu.Unlock()
		return nil
	}
	delete(entry.channels, handle)
	delete(entry.byWire, channel.snapshot.ChannelID)
	manager.channelBytes -= channel.accountedBytes
	streams := make([]WireApplicationStream, 0, len(channel.streams))
	for _, pending := range channel.pending {
		if pending.stop != nil {
			pending.stop()
		}
		pending.cancel()
		if pending.wire != nil {
			streams = append(streams, pending.wire)
		}
		manager.pendingAdmissions--
	}
	channel.pending = nil
	for _, stream := range channel.streams {
		stream.state.Store(uint32(ApplicationStreamClosed))
		streams = append(streams, stream.wire)
		manager.streamBytes -= applicationStreamCost
	}
	channel.streams = nil
	manager.mu.Unlock()
	for _, stream := range streams {
		_ = stream.Close()
	}
	return channel.wire.Close()
}
func (manager *Manager) ServiceChannel(generation corestate.TSGeneration, handle corestate.ServiceHandle) (ServiceChannelSnapshot, error) {
	if handle == corestate.InvalidServiceHandle {
		return ServiceChannelSnapshot{}, ErrChannelClosed
	}
	manager.mu.Lock()
	entry := manager.sessions[generation]
	if entry == nil || entry.channels[handle] == nil {
		manager.mu.Unlock()
		return ServiceChannelSnapshot{}, ErrChannelClosed
	}
	channel := entry.channels[handle]
	authorityGeneration := entry.snapshot.AuthorityGeneration
	manager.mu.Unlock()
	if err := manager.authority.Validate(authorityGeneration); err != nil {
		_ = manager.CloseServiceChannel(generation, handle)
		return ServiceChannelSnapshot{}, ErrAuthorityStale
	}
	manager.mu.Lock()
	defer manager.mu.Unlock()
	entry = manager.sessions[generation]
	if entry == nil || entry.channels[handle] != channel {
		return ServiceChannelSnapshot{}, ErrChannelClosed
	}
	return channel.snapshot, nil
}
func (manager *Manager) Usage() Usage {
	manager.mu.Lock()
	defer manager.mu.Unlock()
	waiters := 0
	for _, p := range manager.pendingChannels {
		waiters += p.waiters
	}
	rotationWaiters := 0
	for _, pending := range manager.pendingRotations {
		rotationWaiters += pending.waiters
	}
	return Usage{ReuseKeys: len(manager.byReuse), Sessions: len(manager.sessions), Channels: manager.channelCountLocked(), PendingSessions: manager.pendingSessions, PendingChannels: len(manager.pendingChannels), ChannelWaiters: waiters, ApplicationStreams: manager.streamCountLocked(), PendingAdmissions: manager.pendingAdmissions, SessionBytes: manager.sessionBytes, ChannelBytes: manager.channelBytes, StreamBytes: manager.streamBytes, StateBytes: manager.sessionBytes + manager.channelBytes + manager.streamBytes, PendingRotations: len(manager.pendingRotations), RotationWaiters: rotationWaiters}
}

func (manager *Manager) streamCountLocked() int {
	count := 0
	for _, entry := range manager.sessions {
		for _, channel := range entry.channels {
			count += len(channel.streams)
		}
	}
	return count
}
func (manager *Manager) channelCountLocked() int {
	count := 0
	for _, entry := range manager.sessions {
		count += len(entry.channels)
	}
	return count
}
func transportSessionCost(spec TransportSessionSpec) uint64 {
	return 96 + uint64(len(spec.ReuseKey.SourceOperator)+len(spec.ReuseKey.Gateway)+len(spec.ReuseKey.Profile)+len(spec.ReuseKey.Transport))
}
func serviceChannelCost(request ServiceChannelRequest) uint64 {
	const fixedCreditAndOwnershipBytes = 96
	return 140 + fixedCreditAndOwnershipBytes + uint64(len(request.ServiceIdentity))
}
func authorityError(err error) error {
	if err == nil {
		return nil
	}
	if errors.Is(err, authority.ErrStaleGeneration) || errors.Is(err, authority.ErrStaleFreshness) || errors.Is(err, authority.ErrExpired) || errors.Is(err, authority.ErrRevoked) {
		return ErrAuthorityStale
	}
	if errors.Is(err, authority.ErrBindingMismatch) || errors.Is(err, authority.ErrInvalidAuthority) {
		return ErrServiceBinding
	}
	return err
}

func sessionAuthorityError(err error) error {
	if err == nil {
		return nil
	}
	if errors.Is(err, authority.ErrStaleGeneration) || errors.Is(err, authority.ErrStaleFreshness) || errors.Is(err, authority.ErrExpired) || errors.Is(err, authority.ErrRevoked) || errors.Is(err, authority.ErrBindingMismatch) || errors.Is(err, authority.ErrInvalidAuthority) {
		return ErrAuthorityStale
	}
	return err
}
