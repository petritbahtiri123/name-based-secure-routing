package client

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"io"
	"net"
	"net/netip"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"nbsr.local/client/nbsr-go-client/demo/internal/fixture"
	"nbsr.local/client/nbsr-go-client/internal/corestate"
	"nbsr.local/client/nbsr-go-client/internal/identity"
	"nbsr.local/client/nbsr-go-client/internal/resolution"
	"nbsr.local/client/nbsr-go-client/internal/session"
)

func TestAssembledAuthorityCancellationCreatesNoTransportAndCleansFlow(t *testing.T) {
	connector := newPhaseConnector(true)
	h := newPhaseHarness(t, connector, newPhaseChannelOpener(phaseChannelBlock), fixture.WithDecisionBlock())
	connection := h.openProxyFlow(t, nil)
	waitForCondition(t, time.Second, func() bool { return h.authority.Manager().Usage().PendingCalls == 1 }, "blocked authority")
	h.cancel()
	_ = connection.Close()
	h.assertClean(t)
	if connector.calls.Load() != 0 {
		t.Fatal("authority cancellation created a TS")
	}
}

func TestAssembledTransportCancellationCreatesNoChannelAndCleansGrant(t *testing.T) {
	connector := newPhaseConnector(true)
	channel := newPhaseChannelOpener(phaseChannelBlock)
	h := newPhaseHarness(t, connector, channel)
	connection := h.openProxyFlow(t, nil)
	<-connector.started
	h.cancel()
	_ = connection.Close()
	h.assertClean(t)
	if channel.calls.Load() != 0 {
		t.Fatal("transport cancellation created a channel")
	}
}

func TestAssembledServiceChannelCancellationForwardsNoPayload(t *testing.T) {
	connector := newPhaseConnector(false)
	channel := newPhaseChannelOpener(phaseChannelBlock)
	h := newPhaseHarness(t, connector, channel)
	connection := h.openProxyFlow(t, []byte("forbidden-payload"))
	<-channel.started
	h.cancel()
	_ = connection.Close()
	h.assertClean(t)
	if channel.applicationOpens.Load() != 0 {
		t.Fatal("SC cancellation reached Stream Credit")
	}
}

func TestAssembledStreamAcceptRejectionWithholdsPayloadAndCleansCredit(t *testing.T) {
	connector := newPhaseConnector(false)
	channel := newPhaseChannelOpener(phaseChannelReject)
	h := newPhaseHarness(t, connector, channel)
	connection := h.openProxyFlow(t, []byte("forbidden-payload"))
	<-channel.prefaceReached
	wantPreface := []byte{0x1d, 0xa6, 0x00, 0x01, 0x01, 0x50,
		0x40, 0x41, 0x42, 0x43, 0x44, 0x45, 0x46, 0x47,
		0x48, 0x49, 0x4a, 0x4b, 0x4c, 0x4d, 0x4e, 0x4f,
		0x02, 0x01, 0x03, 0x01, 0x04, 0x00, 0x05, 0x04}
	if !bytes.Equal(channel.controlWrite, wantPreface) {
		t.Fatalf("credit preface = %x, want %x", channel.controlWrite, wantPreface)
	}
	if channel.payloadWrites.Load() != 0 {
		t.Fatalf("application payload writes before rejection = %d, want 0", channel.payloadWrites.Load())
	}
	close(channel.allowReject)
	<-channel.rejectionObserved
	_ = connection.Close()
	h.waitFlowClean(t)
	h.cancel()
	h.assertClean(t)
	if channel.applicationWrites.Load() != 1 || channel.payloadWrites.Load() != 0 {
		t.Fatalf("writes=%d payload=%d, want one credit preface and zero payload", channel.applicationWrites.Load(), channel.payloadWrites.Load())
	}
}

func TestAssembledForwardingDisconnectCreatesOneStreamAndCleansExactlyOnce(t *testing.T) {
	connector := newPhaseConnector(false)
	channel := newPhaseChannelOpener(phaseChannelAccept)
	h := newPhaseHarness(t, connector, channel)
	connection := h.openProxyFlow(t, []byte("payload-after-accept"))
	if err := <-h.routeDone; err != nil {
		t.Fatalf("secure route did not reach forwarding: %v", err)
	}
	<-channel.applicationAdmitted
	select {
	case <-channel.payloadReached:
	case <-channel.streamClosed:
		t.Fatalf("application stream closed before payload forwarding (writes=%d payload=%d)", channel.applicationWrites.Load(), channel.payloadWrites.Load())
	}
	if channel.applicationWrites.Load() < 2 || channel.payloadWrites.Load() == 0 {
		t.Fatalf("forwarding barrier reached with writes=%d payload=%d", channel.applicationWrites.Load(), channel.payloadWrites.Load())
	}
	_ = connection.Close()
	h.waitFlowClean(t)
	h.cancel()
	h.assertClean(t)
	if channel.applicationOpens.Load() != 1 || channel.streamCloses.Load() != 1 {
		t.Fatalf("opens=%d closes=%d", channel.applicationOpens.Load(), channel.streamCloses.Load())
	}
}

type phaseHarness struct {
	runtime   *Runtime
	opener    *SecureRouteOpener
	authority *AuthorityClient
	sessions  *session.Manager
	cancel    context.CancelFunc
	done      chan error
	routeDone chan error
}

func newPhaseHarness(t *testing.T, connector *phaseConnector, channel *phaseChannelOpener, options ...fixture.Option) *phaseHarness {
	t.Helper()
	private := ed25519.NewKeyFromSeed(bytes.Repeat([]byte{0x55}, ed25519.SeedSize))
	proof, err := NewTSProofOwner(private, 2)
	if err != nil {
		t.Fatal(err)
	}
	defaults, err := fixture.Start(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	request := defaults.AcquireRequest()
	defaults.Close()
	request.Key.ProofThumbprint = proof.KeyRef().Thumbprint
	view := session.DestinationRouteView{ServiceIdentity: request.Intent.ServiceIdentity, ServiceDigest: corestate.ServiceDigest(request.Key.ServiceDigest), Intent: request.Intent, ProofThumbprint: request.Key.ProofThumbprint}
	copy(view.ProofPublicKey[:], proof.PublicKey())
	allOptions := append([]fixture.Option{fixture.WithRouteInputs(request, view)}, options...)
	server, err := fixture.Start(t.TempDir(), allOptions...)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(server.Close)
	authorityClient, err := NewAuthorityClient(server)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = authorityClient.Close() })
	actual := server.AcquireRequest()
	proofKey := identity.TSProofKey{TSGeneration: 2, Key: proof.KeyRef()}
	local := identity.LocalStateIntegrityKey{Key: identity.KeyRef{ID: sha256.Sum256([]byte("phase-local")), Purpose: identity.PurposeLocalStateIntegrity, Generation: 1, Thumbprint: sha256.Sum256([]byte("phase-thumb"))}}
	registry, err := identity.NewMemoryRegistry(actual.Device, nil, []identity.TSProofKey{proofKey}, local)
	if err != nil {
		t.Fatal(err)
	}
	sessions, err := session.NewManager(task4SessionLimits(), fixedClock{server.NowUnix()}, authorityClient.Manager(), registry, connector, channel)
	if err != nil {
		t.Fatal(err)
	}
	spec := session.TransportSessionSpec{Generation: 2, ReuseKey: session.ReuseKey{SourceOperator: actual.Key.SourceOperator, Gateway: "destination.edge", Profile: actual.Key.Profile, Transport: "quic", DeviceID: actual.Key.DeviceID, DeviceGeneration: actual.Key.DeviceGeneration, PolicyDigest: actual.Key.PolicyHash, PolicyGeneration: actual.Key.PolicyGeneration}, Proof: proofKey}
	planner, err := NewSessionRoutePlanner(sessions, spec, proof)
	if err != nil {
		t.Fatal(err)
	}
	opener, err := NewSecureRouteOpener(SecureRouteOpenerConfig{Authority: authorityClient, Sessions: sessions, Planner: planner, AcquireTemplate: actual, ChannelID: corestate.ChannelID(sequence16(0x40))})
	if err != nil {
		t.Fatal(err)
	}
	routeDone := make(chan error, 1)
	runtime, err := NewRuntime(RuntimeConfig{ListenAddress: "127.0.0.1:0", SharedSyntheticIP: netip.MustParseAddr("127.0.0.2"), NowUnix: server.NowUnix(), MaxConnections: 2, MaxRequestBytes: 4096}, demoResolutionInput(), &phaseRouteOpener{SecureRouteOpener: opener, done: routeDone})
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() { done <- runtime.Serve(ctx) }()
	waitForCondition(t, time.Second, runtime.serving, "phase proxy")
	return &phaseHarness{runtime: runtime, opener: opener, authority: authorityClient, sessions: sessions, cancel: cancel, done: done, routeDone: routeDone}
}

type phaseRouteOpener struct {
	*SecureRouteOpener
	done chan<- error
}

func (opener *phaseRouteOpener) OpenVerifiedRoute(ctx context.Context, mapped *resolution.MappedRoute) (io.ReadWriteCloser, error) {
	stream, err := opener.SecureRouteOpener.OpenVerifiedRoute(ctx, mapped)
	opener.done <- err
	return stream, err
}

func (h *phaseHarness) openProxyFlow(t *testing.T, payload []byte) net.Conn {
	t.Helper()
	connection, err := net.DialTimeout("tcp", h.runtime.ProxyAddress(), time.Second)
	if err != nil {
		t.Fatal(err)
	}
	_, err = io.WriteString(connection, "CONNECT service-a.nbsr.test:8080 HTTP/1.1\r\n\r\n")
	if err != nil {
		t.Fatal(err)
	}
	if len(payload) != 0 {
		_, _ = connection.Write(payload)
	}
	return connection
}

func (h *phaseHarness) waitFlowClean(t *testing.T) {
	t.Helper()
	waitForCondition(t, 2*time.Second, func() bool {
		return h.runtime.FlowUsage().Entries == 0 && h.runtime.MappingReferences() == 0 && h.runtime.ProxyUsage().ActiveConnections == 0
	}, "phase flow cleanup")
}
func (h *phaseHarness) assertClean(t *testing.T) {
	t.Helper()
	_ = h.runtime.Close()
	select {
	case <-h.done:
	case <-time.After(2 * time.Second):
		t.Fatal("serve did not stop")
	}
	_ = h.opener.Close()
	h.waitFlowClean(t)
	usage := h.sessions.Usage()
	if usage.PendingSessions != 0 || usage.PendingChannels != 0 || usage.PendingAdmissions != 0 || usage.ApplicationStreams != 0 || usage.Sessions != 0 || usage.Channels != 0 {
		t.Fatalf("session leak: %+v", usage)
	}
	authorityUsage := h.authority.Manager().Usage()
	if authorityUsage.PendingCalls != 0 || authorityUsage.PendingWaiters != 0 {
		t.Fatalf("authority leak: %+v", authorityUsage)
	}
}

type phaseTransport struct{ closed atomic.Int32 }

func (transport *phaseTransport) Close() error { transport.closed.Add(1); return nil }

type phaseConnector struct {
	block   bool
	started chan struct{}
	calls   atomic.Int32
}

func newPhaseConnector(block bool) *phaseConnector {
	return &phaseConnector{block: block, started: make(chan struct{}, 1)}
}
func (connector *phaseConnector) Connect(ctx context.Context, _ session.TransportSessionAttempt) (session.Transport, error) {
	connector.calls.Add(1)
	select {
	case connector.started <- struct{}{}:
	default:
	}
	if connector.block {
		<-ctx.Done()
		return nil, ctx.Err()
	}
	return &phaseTransport{}, nil
}

type phaseChannelMode uint8

const (
	phaseChannelBlock phaseChannelMode = iota + 1
	phaseChannelReject
	phaseChannelAccept
)

type phaseChannelOpener struct {
	mode                                                                    phaseChannelMode
	started                                                                 chan struct{}
	prefaceReached, allowReject, rejectionObserved                          chan struct{}
	applicationAdmitted, payloadReached, streamClosed                       chan struct{}
	controlWrite                                                            []byte
	calls, applicationOpens, applicationWrites, payloadWrites, streamCloses atomic.Int32
}

func newPhaseChannelOpener(mode phaseChannelMode) *phaseChannelOpener {
	opener := &phaseChannelOpener{mode: mode, started: make(chan struct{}, 1), applicationAdmitted: make(chan struct{}), payloadReached: make(chan struct{}), streamClosed: make(chan struct{})}
	if mode == phaseChannelReject {
		opener.prefaceReached = make(chan struct{})
		opener.allowReject = make(chan struct{})
		opener.rejectionObserved = make(chan struct{})
	}
	return opener
}
func (opener *phaseChannelOpener) Open(ctx context.Context, _ session.Transport, attempt session.ServiceChannelAttempt) (session.WireChannel, error) {
	opener.calls.Add(1)
	select {
	case opener.started <- struct{}{}:
	default:
	}
	if opener.mode == phaseChannelBlock {
		<-ctx.Done()
		return nil, ctx.Err()
	}
	return &phaseWireChannel{owner: opener, id: attempt.ChannelID}, nil
}

type phaseWireChannel struct {
	owner *phaseChannelOpener
	id    corestate.ChannelID
}

func (channel *phaseWireChannel) ChannelID() corestate.ChannelID            { return channel.id }
func (*phaseWireChannel) ChannelGeneration() uint64                         { return 1 }
func (*phaseWireChannel) Close() error                                      { return nil }
func (*phaseWireChannel) StreamCreditProfile() string                       { return session.StreamCreditProfileID }
func (*phaseWireChannel) RefillStreamCredits(context.Context, uint64) error { return nil }
func (channel *phaseWireChannel) OpenApplicationStream(context.Context) (session.WireApplicationStream, error) {
	channel.owner.applicationOpens.Add(1)
	close(channel.owner.applicationAdmitted)
	return &phaseWireStream{owner: channel.owner, accept: channel.owner.mode == phaseChannelAccept, id: 4, closed: make(chan struct{})}, nil
}

type phaseWireStream struct {
	owner    *phaseChannelOpener
	accept   bool
	id       corestate.StreamID
	decision bool
	once     sync.Once
	closed   chan struct{}
}

func (stream *phaseWireStream) StreamID() corestate.StreamID { return stream.id }
func (stream *phaseWireStream) Write(payload []byte) (int, error) {
	if stream.owner.applicationWrites.Add(1) == 1 {
		stream.owner.controlWrite = append([]byte(nil), payload...)
		if stream.owner.prefaceReached != nil {
			close(stream.owner.prefaceReached)
		}
	} else {
		stream.owner.payloadWrites.Add(1)
		select {
		case <-stream.owner.payloadReached:
		default:
			close(stream.owner.payloadReached)
		}
	}
	return len(payload), nil
}

func (stream *phaseWireStream) Read(payload []byte) (int, error) {
	if !stream.decision {
		stream.decision = true
		if stream.accept {
			payload[0] = 0
		} else {
			<-stream.owner.allowReject
			payload[0] = 1
			close(stream.owner.rejectionObserved)
		}
		return 1, nil
	}
	<-stream.closed
	return 0, io.EOF
}
func (stream *phaseWireStream) Close() error {
	stream.once.Do(func() {
		stream.owner.streamCloses.Add(1)
		close(stream.closed)
		close(stream.owner.streamClosed)
	})
	return nil
}
