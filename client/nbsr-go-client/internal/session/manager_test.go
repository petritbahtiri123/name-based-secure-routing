package session

import (
	"context"
	"errors"
	"runtime"
	"sync"
	"testing"

	"nbsr.local/client/nbsr-go-client/internal/authority"
	"nbsr.local/client/nbsr-go-client/internal/corestate"
	"nbsr.local/client/nbsr-go-client/internal/identity"
)

func TestTransportSessionOwnershipIsAuthorityAndProofBound(t *testing.T) {
	fixture := newFixture(t)
	snapshot, err := fixture.manager.CreateTransportSession(context.Background(), fixture.sessionSpec(1))
	if err != nil {
		t.Fatalf("CreateTransportSession: %v", err)
	}
	if snapshot.Generation != 1 || snapshot.State != TransportCurrent || snapshot.ProofThumbprint != fixture.proof(1).Key.Thumbprint {
		t.Fatalf("snapshot = %+v", snapshot)
	}

	wrong := fixture.sessionSpec(2)
	wrong.Proof = fixture.proof(1)
	if _, err := fixture.manager.CreateTransportSession(context.Background(), wrong); !errors.Is(err, ErrProofBinding) {
		t.Fatalf("wrong proof = %v, want ErrProofBinding", err)
	}
	wrongProfile := fixture.sessionSpec(2)
	wrongProfile.ReuseKey.Profile = "other-profile"
	if _, err := fixture.manager.CreateTransportSession(context.Background(), wrongProfile); !errors.Is(err, ErrAuthorityStale) {
		t.Fatalf("wrong authority profile = %v, want ErrAuthorityStale", err)
	}
	fixture.gate.invalidate()
	if _, err := fixture.manager.CreateTransportSession(context.Background(), fixture.sessionSpec(2)); !errors.Is(err, ErrAuthorityStale) {
		t.Fatalf("stale authority = %v, want ErrAuthorityStale", err)
	}
}

func TestTransportSessionMaxTwoGenerationsAndNoReuse(t *testing.T) {
	fixture := newFixture(t)
	first := fixture.createTS(t, 1)
	if err := fixture.manager.MarkDraining(first.Generation); err != nil {
		t.Fatalf("MarkDraining: %v", err)
	}
	fixture.createTS(t, 2)
	if _, err := fixture.manager.CreateTransportSession(context.Background(), fixture.sessionSpec(3)); !errors.Is(err, ErrGenerationCapacity) {
		t.Fatalf("third generation = %v, want ErrGenerationCapacity", err)
	}
	if err := fixture.manager.CloseTransportSession(1); err != nil {
		t.Fatalf("CloseTransportSession: %v", err)
	}
	if err := fixture.manager.CloseTransportSession(1); err != nil {
		t.Fatalf("repeated CloseTransportSession: %v", err)
	}
	if _, err := fixture.manager.CreateTransportSession(context.Background(), fixture.sessionSpec(1)); !errors.Is(err, ErrGenerationClosed) {
		t.Fatalf("generation reuse = %v, want ErrGenerationClosed", err)
	}
	if err := fixture.manager.MarkDraining(2); err != nil {
		t.Fatalf("MarkDraining generation 2: %v", err)
	}
	fixture.createTS(t, 3)
}

func TestServiceChannelCommitBarrierAndLocalHandle(t *testing.T) {
	fixture := newFixture(t)
	ts := fixture.createTS(t, 1)
	request := fixture.channelRequest(ts.Generation, 1)
	channel, err := fixture.manager.CreateServiceChannel(context.Background(), request)
	if err != nil {
		t.Fatalf("CreateServiceChannel: %v", err)
	}
	if channel.Handle == corestate.InvalidServiceHandle || channel.ChannelID != request.ChannelID || channel.ServiceDigest != request.ServiceDigest {
		t.Fatalf("channel = %+v", channel)
	}
	if channel.Handle == corestate.ServiceHandle(channel.ChannelID[0]) {
		t.Fatalf("local handle aliased wire channel_id: %+v", channel)
	}

	fixture.opener.beforeReturn = func() { fixture.gate.invalidate() }
	if _, err := fixture.manager.CreateServiceChannel(context.Background(), fixture.channelRequest(ts.Generation, 2)); !errors.Is(err, ErrAuthorityStale) {
		t.Fatalf("invalidation during creation = %v, want ErrAuthorityStale", err)
	}
	if fixture.manager.Usage().Channels != 1 {
		t.Fatalf("channels after failed commit = %d, want 1", fixture.manager.Usage().Channels)
	}
}

func TestServiceChannelBindingCapacityAndTeardown(t *testing.T) {
	fixture := newFixture(t)
	ts := fixture.createTS(t, 1)
	first := fixture.createSC(t, fixture.channelRequest(ts.Generation, 1))
	bad := fixture.channelRequest(ts.Generation, 2)
	bad.ServiceDigest[0]++
	if _, err := fixture.manager.CreateServiceChannel(context.Background(), bad); !errors.Is(err, ErrServiceBinding) {
		t.Fatalf("service mismatch = %v, want ErrServiceBinding", err)
	}
	wrongName := fixture.channelRequest(ts.Generation, 2)
	wrongName.ServiceIdentity = "other.example"
	if _, err := fixture.manager.CreateServiceChannel(context.Background(), wrongName); !errors.Is(err, ErrServiceBinding) {
		t.Fatalf("service identity mismatch = %v, want ErrServiceBinding", err)
	}
	second := fixture.createSC(t, fixture.channelRequest(ts.Generation, 3))
	if err := fixture.manager.CloseServiceChannel(first.Generation, first.Handle); err != nil {
		t.Fatalf("CloseServiceChannel: %v", err)
	}
	if _, err := fixture.manager.ServiceChannel(first.Generation, first.Handle); !errors.Is(err, ErrChannelClosed) {
		t.Fatalf("closed channel lookup = %v, want ErrChannelClosed", err)
	}
	if _, err := fixture.manager.ServiceChannel(second.Generation, second.Handle); err != nil {
		t.Fatalf("sibling channel: %v", err)
	}
	third := fixture.createSC(t, fixture.channelRequest(ts.Generation, 4))
	if third.Handle <= second.Handle {
		t.Fatalf("handle reused: second=%d third=%d", second.Handle, third.Handle)
	}
	if err := fixture.manager.CloseTransportSession(ts.Generation); err != nil {
		t.Fatalf("CloseTransportSession: %v", err)
	}
	if fixture.manager.Usage().Channels != 0 {
		t.Fatalf("orphan channels = %d", fixture.manager.Usage().Channels)
	}
	if _, err := fixture.manager.ServiceChannel(third.Generation, third.Handle); !errors.Is(err, ErrChannelClosed) {
		t.Fatalf("post-TS teardown lookup = %v, want ErrChannelClosed", err)
	}
}

func TestConcurrentSameServiceCoalescesAndDifferentServicesRemainIsolated(t *testing.T) {
	fixture := newFixture(t)
	ts := fixture.createTS(t, 1)
	fixture.opener.block = make(chan struct{})
	request := fixture.channelRequest(ts.Generation, 1)
	results := make(chan ServiceChannelSnapshot, 2)
	errs := make(chan error, 2)
	for range 2 {
		go func() {
			got, err := fixture.manager.CreateServiceChannel(context.Background(), request)
			results <- got
			errs <- err
		}()
	}
	<-fixture.opener.started
	for fixture.manager.Usage().ChannelWaiters != 1 {
		runtime.Gosched()
	}
	close(fixture.opener.block)
	first, second := <-results, <-results
	if err := <-errs; err != nil {
		t.Fatal(err)
	}
	if err := <-errs; err != nil {
		t.Fatal(err)
	}
	if first.Handle != second.Handle || fixture.opener.calls != 1 {
		t.Fatalf("coalescing: handles %d/%d calls=%d", first.Handle, second.Handle, fixture.opener.calls)
	}
}

func TestPendingSameServiceWithDifferentChannelBindingDoesNotCoalesce(t *testing.T) {
	fixture := newFixture(t)
	ts := fixture.createTS(t, 1)
	fixture.opener.block = make(chan struct{})
	first := fixture.channelRequest(ts.Generation, 1)
	started := make(chan error, 1)
	go func() { _, err := fixture.manager.CreateServiceChannel(context.Background(), first); started <- err }()
	<-fixture.opener.started
	conflict := first
	conflict.ChannelID[1] = 1
	if _, err := fixture.manager.CreateServiceChannel(context.Background(), conflict); !errors.Is(err, ErrChannelBinding) {
		t.Fatalf("different pending binding = %v, want ErrChannelBinding", err)
	}
	close(fixture.opener.block)
	if err := <-started; err != nil {
		t.Fatal(err)
	}
}

func TestCancelledCoalescedWaiterReleasesBoundedWaiterSlot(t *testing.T) {
	fixture := newFixture(t)
	fixture.manager.limits.MaxWaitersPerChannel = 1
	ts := fixture.createTS(t, 1)
	fixture.opener.block = make(chan struct{})
	request := fixture.channelRequest(ts.Generation, 1)
	leader := make(chan error, 1)
	go func() { _, err := fixture.manager.CreateServiceChannel(context.Background(), request); leader <- err }()
	<-fixture.opener.started
	ctx, cancel := context.WithCancel(context.Background())
	waiter := make(chan error, 1)
	go func() { _, err := fixture.manager.CreateServiceChannel(ctx, request); waiter <- err }()
	for fixture.manager.Usage().ChannelWaiters != 1 {
		runtime.Gosched()
	}
	cancel()
	if err := <-waiter; !errors.Is(err, context.Canceled) {
		t.Fatalf("cancelled waiter = %v", err)
	}
	if got := fixture.manager.Usage().ChannelWaiters; got != 0 {
		t.Fatalf("waiters after cancellation = %d, want 0", got)
	}
	second := make(chan error, 1)
	go func() { _, err := fixture.manager.CreateServiceChannel(context.Background(), request); second <- err }()
	for fixture.manager.Usage().ChannelWaiters != 1 {
		runtime.Gosched()
	}
	close(fixture.opener.block)
	if err := <-leader; err != nil {
		t.Fatal(err)
	}
	if err := <-second; err != nil {
		t.Fatal(err)
	}
}

func TestServiceChannelExactCapacityAndDuplicateChannelFailClosed(t *testing.T) {
	fixture := newFixture(t)
	ts := fixture.createTS(t, 1)
	for value := byte(1); value <= 4; value++ {
		fixture.createSC(t, fixture.channelRequest(ts.Generation, value))
	}
	if _, err := fixture.manager.CreateServiceChannel(context.Background(), fixture.channelRequest(ts.Generation, 5)); !errors.Is(err, ErrChannelCapacity) {
		t.Fatalf("fifth channel = %v, want ErrChannelCapacity", err)
	}
	duplicate := fixture.channelRequest(ts.Generation, 6)
	duplicate.ChannelID = fixture.channelRequest(ts.Generation, 1).ChannelID
	if _, err := fixture.manager.CreateServiceChannel(context.Background(), duplicate); !errors.Is(err, ErrDuplicateChannel) {
		t.Fatalf("duplicate channel_id = %v, want ErrDuplicateChannel", err)
	}
}

func TestTransportTeardownWhileChannelCreationPendingLeavesNoOrphan(t *testing.T) {
	fixture := newFixture(t)
	ts := fixture.createTS(t, 1)
	fixture.opener.block = make(chan struct{})
	result := make(chan error, 1)
	go func() {
		_, err := fixture.manager.CreateServiceChannel(context.Background(), fixture.channelRequest(ts.Generation, 1))
		result <- err
	}()
	<-fixture.opener.started
	if err := fixture.manager.CloseTransportSession(ts.Generation); err != nil {
		t.Fatalf("CloseTransportSession: %v", err)
	}
	close(fixture.opener.block)
	if err := <-result; !errors.Is(err, ErrGenerationClosed) {
		t.Fatalf("pending creation after teardown = %v, want ErrGenerationClosed", err)
	}
	if usage := fixture.manager.Usage(); usage.Sessions != 0 || usage.Channels != 0 || usage.PendingChannels != 0 {
		t.Fatalf("usage after teardown race = %+v", usage)
	}
}

func TestGenerationChangeDuringChannelCreationFailsCommit(t *testing.T) {
	fixture := newFixture(t)
	ts := fixture.createTS(t, 1)
	fixture.opener.beforeReturn = func() {
		if err := fixture.manager.MarkDraining(ts.Generation); err != nil {
			t.Errorf("MarkDraining: %v", err)
		}
	}
	if _, err := fixture.manager.CreateServiceChannel(context.Background(), fixture.channelRequest(ts.Generation, 1)); !errors.Is(err, ErrGenerationNotCurrent) {
		t.Fatalf("creation across current-to-draining = %v, want ErrGenerationNotCurrent", err)
	}
	if fixture.manager.Usage().Channels != 0 {
		t.Fatal("channel committed across TS state change")
	}
}

func TestAuthorityInvalidationMakesCommittedChannelUnusable(t *testing.T) {
	fixture := newFixture(t)
	ts := fixture.createTS(t, 1)
	channel := fixture.createSC(t, fixture.channelRequest(ts.Generation, 1))
	fixture.gate.invalidate()
	if _, err := fixture.manager.ServiceChannel(channel.Generation, channel.Handle); !errors.Is(err, ErrAuthorityStale) {
		t.Fatalf("lookup after invalidation = %v, want ErrAuthorityStale", err)
	}
	if fixture.manager.Usage().Channels != 0 {
		t.Fatal("stale channel remained owned")
	}
}

func TestTSProofKeyCannotReuseDeviceKeyReference(t *testing.T) {
	fixture := newFixture(t)
	device, err := fixture.registry.Device()
	if err != nil {
		t.Fatal(err)
	}
	bad := fixture.proof(1)
	bad.Key.ID = device.SigningKey.ID
	registry := proofOverrideRegistry{Registry: fixture.registry, proof: bad}
	manager, err := newManager(fixture.manager.limits, fixture.clock, fixture.gate, registry, fixture.connector, fixture.opener)
	if err != nil {
		t.Fatal(err)
	}
	spec := fixture.sessionSpec(1)
	spec.Proof = bad
	if _, err := manager.CreateTransportSession(context.Background(), spec); !errors.Is(err, ErrProofBinding) {
		t.Fatalf("reused device key = %v, want ErrProofBinding", err)
	}
}

type proofOverrideRegistry struct {
	identity.Registry
	proof identity.TSProofKey
}

func (registry proofOverrideRegistry) TSProof(uint64) (identity.TSProofKey, error) {
	return registry.proof, nil
}

type testGate struct {
	mu         sync.Mutex
	generation authority.AuthorityGeneration
	valid      bool
}

func (g *testGate) Capture() (authority.AuthorityGeneration, error) {
	if !g.valid {
		return 0, authority.ErrStaleGeneration
	}
	return g.current(), nil
}
func (g *testGate) Validate(generation authority.AuthorityGeneration) error {
	if !g.valid || generation != g.current() {
		return authority.ErrStaleGeneration
	}
	return nil
}
func (g *testGate) ValidateSession(key ReuseKey, generation authority.AuthorityGeneration) error {
	if key.SourceOperator != "source" || key.Profile != "nbsr" {
		return authority.ErrBindingMismatch
	}
	return g.Validate(generation)
}
func (g *testGate) Preflight(request ServiceChannelRequest, generation authority.AuthorityGeneration, _ uint64) ([]byte, error) {
	if err := g.Validate(generation); err != nil {
		return nil, err
	}
	if request.AuthorityGeneration != corestate.AuthorityGeneration(generation) || request.ServiceIdentity != "svc.example" || request.ServiceDigest[0]+10 != request.RouteGrantDigest[0] {
		return nil, authority.ErrBindingMismatch
	}
	return []byte{request.RouteGrantDigest[0]}, nil
}
func (g *testGate) Commit(request ServiceChannelRequest, generation authority.AuthorityGeneration, now uint64) (AuthorityToken, error) {
	_, err := g.Preflight(request, generation, now)
	return AuthorityToken{Generation: generation, Grant: request.RouteGrantDigest, Revision: 1}, err
}
func (g *testGate) CommitApplication(token AuthorityToken, owner authority.AdmissionOwner, _ uint64, commit func() error) error {
	if !g.valid || token.Generation != g.current() || token.Grant == (corestate.RouteGrantDigest{}) || owner.TSGeneration == 0 || owner.ChannelID == ([16]byte{}) {
		return authority.ErrStaleGeneration
	}
	return commit()
}
func (g *testGate) current() authority.AuthorityGeneration {
	g.mu.Lock()
	defer g.mu.Unlock()
	return g.generation
}
func (g *testGate) invalidate() { g.mu.Lock(); g.valid = false; g.generation++; g.mu.Unlock() }

type testConnector struct{ transports []*testTransport }

func (c *testConnector) Connect(_ context.Context, _ TransportSessionAttempt) (Transport, error) {
	t := &testTransport{}
	c.transports = append(c.transports, t)
	return t, nil
}

type testTransport struct{ closed bool }

func (t *testTransport) Close() error { t.closed = true; return nil }

type testOpener struct {
	mu           sync.Mutex
	calls        int
	channels     []*testWireChannel
	started      chan struct{}
	block        chan struct{}
	beforeReturn func()
}

func (o *testOpener) Open(_ context.Context, _ Transport, request ServiceChannelAttempt) (WireChannel, error) {
	o.mu.Lock()
	o.calls++
	started, block, hook := o.started, o.block, o.beforeReturn
	o.beforeReturn = nil
	o.mu.Unlock()
	select {
	case started <- struct{}{}:
	default:
	}
	if block != nil {
		<-block
	}
	if hook != nil {
		hook()
	}
	channel := &testWireChannel{id: request.ChannelID, generation: 1}
	o.mu.Lock()
	o.channels = append(o.channels, channel)
	o.mu.Unlock()
	return channel, nil
}

type testWireChannel struct {
	id          corestate.ChannelID
	generation  uint64
	closed      bool
	next        *testApplicationWire
	profile     string
	openCalls   int
	refillCalls int
	profileHook func()
}

func (c *testWireChannel) ChannelID() corestate.ChannelID { return c.id }
func (c *testWireChannel) ChannelGeneration() uint64      { return c.generation }
func (c *testWireChannel) Close() error                   { c.closed = true; return nil }
func (c *testWireChannel) StreamCreditProfile() string {
	if c.profileHook != nil {
		c.profileHook()
	}
	if c.profile != "" {
		return c.profile
	}
	return StreamCreditProfileID
}
func (c *testWireChannel) OpenApplicationStream(context.Context) (WireApplicationStream, error) {
	c.openCalls++
	if c.next == nil {
		return nil, ErrTransport
	}
	return c.next, nil
}
func (c *testWireChannel) RefillStreamCredits(context.Context, uint64) error {
	c.refillCalls++
	return nil
}

type fixture struct {
	t         *testing.T
	clock     *testClock
	gate      *testGate
	registry  *identity.MemoryRegistry
	connector *testConnector
	opener    *testOpener
	manager   *Manager
}
type testClock struct{ now uint64 }

func (c *testClock) NowUnix() uint64 { return c.now }

func newFixture(t *testing.T) *fixture {
	t.Helper()
	now := uint64(1_900_000_000)
	deviceKey := identity.KeyRef{ID: bytes32(1), Purpose: identity.PurposeDeviceACPRequest, Generation: 1, Thumbprint: bytes32(2)}
	device := identity.DeviceIdentity{ID: bytes32(3), SourceOperatorID: "source", CredentialGeneration: 1, CredentialNotBefore: now - 10, CredentialExpiresAt: now + 1000, SigningKey: deviceKey}
	proofs := []identity.TSProofKey{{TSGeneration: 1, Key: identity.KeyRef{ID: bytes32(11), Purpose: identity.PurposeTSProof, Generation: 1, Thumbprint: bytes32(21)}}, {TSGeneration: 2, Key: identity.KeyRef{ID: bytes32(12), Purpose: identity.PurposeTSProof, Generation: 2, Thumbprint: bytes32(22)}}, {TSGeneration: 3, Key: identity.KeyRef{ID: bytes32(13), Purpose: identity.PurposeTSProof, Generation: 3, Thumbprint: bytes32(23)}}}
	registry, err := identity.NewMemoryRegistry(device, nil, proofs, identity.LocalStateIntegrityKey{Key: identity.KeyRef{ID: bytes32(4), Purpose: identity.PurposeLocalStateIntegrity, Generation: 1, Thumbprint: bytes32(5)}})
	if err != nil {
		t.Fatal(err)
	}
	gate := &testGate{generation: 7, valid: true}
	connector := &testConnector{}
	opener := &testOpener{started: make(chan struct{}, 8)}
	clock := &testClock{now}
	manager, err := newManager(Limits{MaxReuseKeys: 2, MaxSessions: 4, MaxChannels: 4, MaxPendingSessions: 2, MaxPendingChannels: 2, MaxWaitersPerChannel: 2, MaxStreams: 8, MaxPendingAdmissions: 4, MaxReuseKeyBytes: 256, MaxServiceIdentityBytes: 128, MaxStateBytes: 4096}, clock, gate, registry, connector, opener)
	if err != nil {
		t.Fatal(err)
	}
	return &fixture{t: t, clock: clock, gate: gate, registry: registry, connector: connector, opener: opener, manager: manager}
}
func (f *fixture) proof(g uint64) identity.TSProofKey { p, _ := f.registry.TSProof(g); return p }
func (f *fixture) sessionSpec(g uint64) TransportSessionSpec {
	return TransportSessionSpec{Generation: corestate.TSGeneration(g), ReuseKey: ReuseKey{SourceOperator: "source", Gateway: "gateway", Profile: "nbsr", Transport: "quic", DeviceID: bytes32(3), DeviceGeneration: 1, PolicyDigest: bytes32(31), PolicyGeneration: 1}, Proof: f.proof(g)}
}
func (f *fixture) createTS(t *testing.T, g uint64) TransportSessionSnapshot {
	got, err := f.manager.CreateTransportSession(context.Background(), f.sessionSpec(g))
	if err != nil {
		t.Fatal(err)
	}
	return got
}
func (f *fixture) channelRequest(g corestate.TSGeneration, value byte) ServiceChannelRequest {
	var id corestate.ChannelID
	id[0] = value + 40
	return ServiceChannelRequest{Generation: g, ChannelID: id, ServiceIdentity: "svc.example", ServiceDigest: corestate.ServiceDigest(bytes32(value)), RouteGrantDigest: corestate.RouteGrantDigest(bytes32(value + 10)), AuthorityGeneration: corestate.AuthorityGeneration(f.gate.current()), ProofThumbprint: authority.ProofKeyThumbprint(f.proof(uint64(g)).Key.Thumbprint)}
}
func (f *fixture) createSC(t *testing.T, r ServiceChannelRequest) ServiceChannelSnapshot {
	got, err := f.manager.CreateServiceChannel(context.Background(), r)
	if err != nil {
		t.Fatal(err)
	}
	return got
}
func bytes32(v byte) [32]byte { var out [32]byte; out[0] = v; return out }

func TestLogicalStateBoundsAndTeardownAccounting(t *testing.T) {
	fixture := newFixture(t)
	session := fixture.createTS(t, 1)
	afterSession := fixture.manager.Usage()
	if afterSession.SessionBytes == 0 || afterSession.StateBytes != afterSession.SessionBytes {
		t.Fatalf("session usage = %+v, want non-zero session-only accounting", afterSession)
	}

	channel := fixture.createSC(t, fixture.channelRequest(session.Generation, 1))
	afterChannel := fixture.manager.Usage()
	if afterChannel.ChannelBytes == 0 || afterChannel.StateBytes != afterChannel.SessionBytes+afterChannel.ChannelBytes {
		t.Fatalf("channel usage = %+v, want bounded aggregate accounting", afterChannel)
	}
	if err := fixture.manager.CloseServiceChannel(session.Generation, channel.Handle); err != nil {
		t.Fatal(err)
	}
	if got := fixture.manager.Usage(); got.ChannelBytes != 0 || got.StateBytes != got.SessionBytes {
		t.Fatalf("usage after channel teardown = %+v", got)
	}
	if err := fixture.manager.CloseTransportSession(session.Generation); err != nil {
		t.Fatal(err)
	}
	if got := fixture.manager.Usage(); got.StateBytes != 0 {
		t.Fatalf("usage after session teardown = %+v", got)
	}

	tooLarge := fixture.sessionSpec(2)
	tooLarge.ReuseKey.Gateway = string(make([]byte, fixture.manager.limits.MaxReuseKeyBytes+1))
	if _, err := fixture.manager.CreateTransportSession(context.Background(), tooLarge); !errors.Is(err, ErrSessionCapacity) {
		t.Fatalf("oversized reuse key = %v, want ErrSessionCapacity", err)
	}
}
