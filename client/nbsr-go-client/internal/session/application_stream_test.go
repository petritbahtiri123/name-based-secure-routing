package session

import (
	"bytes"
	"context"
	"errors"
	"io"
	"sync"
	"testing"
	"time"

	"nbsr.local/client/nbsr-go-client/internal/corestate"
)

func TestApplicationStreamPublishesOnlyAfterAcceptAndThenWritesPayload(t *testing.T) {
	fixture := newFixture(t)
	ts := fixture.createTS(t, 1)
	sc := fixture.createSC(t, fixture.channelRequest(ts.Generation, 1))
	wireChannel := fixture.opener.channels[0]
	wireChannel.next = &testApplicationWire{id: 4, read: []byte{0}}

	stream, err := fixture.manager.OpenApplicationStream(context.Background(), ts.Generation, sc.Handle)
	if err != nil {
		t.Fatal(err)
	}
	if stream.StreamID() != 4 || stream.State() != ApplicationStreamAccepted {
		t.Fatalf("stream = id %d state %d", stream.StreamID(), stream.State())
	}
	if len(wireChannel.next.writes) != 1 {
		t.Fatalf("writes before payload = %d, want preface only", len(wireChannel.next.writes))
	}
	if _, err := stream.Write([]byte("payload")); err != nil {
		t.Fatal(err)
	}
	if got := wireChannel.next.writes[1]; !bytes.Equal(got, []byte("payload")) {
		t.Fatalf("payload = %q", got)
	}
}

func TestApplicationStreamWriteBeforeAcceptFails(t *testing.T) {
	wire := &testApplicationWire{id: 4}
	stream := newApplicationStream(nil, CreditReservation{}, wire)
	if _, err := stream.Write([]byte("forbidden")); !errors.Is(err, ErrStreamNotAccepted) {
		t.Fatalf("pending write = %v, want ErrStreamNotAccepted", err)
	}
	if len(wire.writes) != 0 {
		t.Fatal("pending payload reached wire")
	}
}

func TestApplicationStreamRejectSendsNoPayloadAndConsumesCredit(t *testing.T) {
	fixture := newFixture(t)
	ts := fixture.createTS(t, 1)
	sc := fixture.createSC(t, fixture.channelRequest(ts.Generation, 1))
	wireChannel := fixture.opener.channels[0]
	wireChannel.next = &testApplicationWire{id: 4, read: []byte{1}}
	if _, err := fixture.manager.OpenApplicationStream(context.Background(), ts.Generation, sc.Handle); !errors.Is(err, ErrAdmissionRejected) {
		t.Fatalf("rejection = %v, want ErrAdmissionRejected", err)
	}
	if len(wireChannel.next.writes) != 1 || !wireChannel.next.closed {
		t.Fatalf("rejected wire writes=%d closed=%v", len(wireChannel.next.writes), wireChannel.next.closed)
	}
	snapshot, err := fixture.manager.CreditSnapshot(ts.Generation, sc.Handle)
	if err != nil || snapshot.Available != 63 {
		t.Fatalf("credit after reject = %+v, %v", snapshot, err)
	}
}

func TestApplicationStreamFinalBarrierAndTeardown(t *testing.T) {
	fixture := newFixture(t)
	ts := fixture.createTS(t, 1)
	sc := fixture.createSC(t, fixture.channelRequest(ts.Generation, 1))
	wireChannel := fixture.opener.channels[0]
	wire := &testApplicationWire{id: 4, read: []byte{0}, beforeRead: fixture.gate.invalidate}
	wireChannel.next = wire
	if _, err := fixture.manager.OpenApplicationStream(context.Background(), ts.Generation, sc.Handle); !errors.Is(err, ErrAuthorityStale) {
		t.Fatalf("authority race = %v, want ErrAuthorityStale", err)
	}
	if !wire.closed || fixture.manager.Usage().ApplicationStreams != 0 {
		t.Fatalf("orphan after authority race: closed=%v usage=%+v", wire.closed, fixture.manager.Usage())
	}
}

func TestApplicationStreamServiceChannelTeardownDuringAdmissionFailsClosed(t *testing.T) {
	fixture := newFixture(t)
	ts := fixture.createTS(t, 1)
	sc := fixture.createSC(t, fixture.channelRequest(ts.Generation, 1))
	wireChannel := fixture.opener.channels[0]
	wire := &testApplicationWire{id: 4, read: []byte{0}}
	wire.beforeRead = func() {
		if err := fixture.manager.CloseServiceChannel(ts.Generation, sc.Handle); err != nil {
			t.Errorf("CloseServiceChannel: %v", err)
		}
	}
	wireChannel.next = wire
	if _, err := fixture.manager.OpenApplicationStream(context.Background(), ts.Generation, sc.Handle); !errors.Is(err, ErrCreditBinding) {
		t.Fatalf("SC teardown race = %v, want ErrCreditBinding", err)
	}
	if !wire.closed || fixture.manager.Usage().ApplicationStreams != 0 || fixture.manager.Usage().PendingAdmissions != 0 {
		t.Fatalf("orphan after teardown: closed=%v usage=%+v", wire.closed, fixture.manager.Usage())
	}
}

func TestApplicationStreamTransportTeardownDuringAdmissionFailsClosed(t *testing.T) {
	fixture := newFixture(t)
	ts := fixture.createTS(t, 1)
	sc := fixture.createSC(t, fixture.channelRequest(ts.Generation, 1))
	wireChannel := fixture.opener.channels[0]
	wire := &testApplicationWire{id: 4, read: []byte{0}}
	wire.beforeRead = func() {
		if err := fixture.manager.CloseTransportSession(ts.Generation); err != nil {
			t.Errorf("CloseTransportSession: %v", err)
		}
	}
	wireChannel.next = wire
	if _, err := fixture.manager.OpenApplicationStream(context.Background(), ts.Generation, sc.Handle); !errors.Is(err, ErrCreditBinding) {
		t.Fatalf("TS teardown race = %v, want ErrCreditBinding", err)
	}
	if !wire.closed || fixture.manager.Usage().ApplicationStreams != 0 || fixture.manager.Usage().PendingAdmissions != 0 {
		t.Fatalf("orphan after TS teardown: closed=%v usage=%+v", wire.closed, fixture.manager.Usage())
	}
}

func TestApplicationStreamMalformedDecisionFailsClosed(t *testing.T) {
	fixture := newFixture(t)
	ts := fixture.createTS(t, 1)
	sc := fixture.createSC(t, fixture.channelRequest(ts.Generation, 1))
	wireChannel := fixture.opener.channels[0]
	wireChannel.next = &testApplicationWire{id: 4}
	if _, err := fixture.manager.OpenApplicationStream(context.Background(), ts.Generation, sc.Handle); !errors.Is(err, ErrAdmissionRejected) {
		t.Fatalf("empty decision = %v, want ErrAdmissionRejected", err)
	}
	if !wireChannel.next.closed || fixture.manager.Usage().PendingAdmissions != 0 {
		t.Fatalf("malformed cleanup: closed=%v usage=%+v", wireChannel.next.closed, fixture.manager.Usage())
	}
}

func TestApplicationStreamRejectsWrongProfileBeforeOpeningWire(t *testing.T) {
	fixture := newFixture(t)
	ts := fixture.createTS(t, 1)
	sc := fixture.createSC(t, fixture.channelRequest(ts.Generation, 1))
	wireChannel := fixture.opener.channels[0]
	wireChannel.profile = "legacy"
	wireChannel.next = &testApplicationWire{id: 4, read: []byte{0}}
	if _, err := fixture.manager.OpenApplicationStream(context.Background(), ts.Generation, sc.Handle); !errors.Is(err, ErrProfileUnsupported) {
		t.Fatalf("wrong profile = %v, want ErrProfileUnsupported", err)
	}
	if wireChannel.openCalls != 0 {
		t.Fatalf("wire opened under wrong profile: %d", wireChannel.openCalls)
	}
	snapshot, err := fixture.manager.CreditSnapshot(ts.Generation, sc.Handle)
	if err != nil || snapshot.Available != StreamCreditCount {
		t.Fatalf("wrong profile consumed credit: %+v, %v", snapshot, err)
	}
}

func TestApplicationStreamCapacityFailureDoesNotConsumeCredit(t *testing.T) {
	fixture := newFixture(t)
	fixture.manager.limits.MaxStreams = 1
	ts := fixture.createTS(t, 1)
	sc := fixture.createSC(t, fixture.channelRequest(ts.Generation, 1))
	wireChannel := fixture.opener.channels[0]
	wireChannel.next = &testApplicationWire{id: 4, read: []byte{0}}
	if _, err := fixture.manager.OpenApplicationStream(context.Background(), ts.Generation, sc.Handle); err != nil {
		t.Fatal(err)
	}
	wireChannel.next = &testApplicationWire{id: 8, read: []byte{0}}
	if _, err := fixture.manager.OpenApplicationStream(context.Background(), ts.Generation, sc.Handle); !errors.Is(err, ErrStreamCapacity) {
		t.Fatalf("capacity = %v", err)
	}
	snapshot, err := fixture.manager.CreditSnapshot(ts.Generation, sc.Handle)
	if err != nil || snapshot.Available != 63 {
		t.Fatalf("capacity consumed credit: %+v, %v", snapshot, err)
	}
}

func TestApplicationStreamProfileCallbackRunsOutsideOwnershipLock(t *testing.T) {
	fixture := newFixture(t)
	ts := fixture.createTS(t, 1)
	sc := fixture.createSC(t, fixture.channelRequest(ts.Generation, 1))
	wireChannel := fixture.opener.channels[0]
	wireChannel.profileHook = func() { _ = fixture.manager.Usage() }
	wireChannel.next = &testApplicationWire{id: 4, read: []byte{0}}
	done := make(chan error, 1)
	go func() {
		_, err := fixture.manager.OpenApplicationStream(context.Background(), ts.Generation, sc.Handle)
		done <- err
	}()
	select {
	case err := <-done:
		if err != nil {
			t.Fatal(err)
		}
	case <-time.After(time.Second):
		t.Fatal("profile callback ran under ownership lock")
	}
}

func TestApplicationStreamBlockedAdmissionIsCanceledByTeardown(t *testing.T) {
	fixture := newFixture(t)
	ts := fixture.createTS(t, 1)
	sc := fixture.createSC(t, fixture.channelRequest(ts.Generation, 1))
	wire := &testApplicationWire{id: 4, readStarted: make(chan struct{}), closeSignal: make(chan struct{})}
	fixture.opener.channels[0].next = wire
	done := make(chan error, 1)
	go func() {
		_, err := fixture.manager.OpenApplicationStream(context.Background(), ts.Generation, sc.Handle)
		done <- err
	}()
	select {
	case <-wire.readStarted:
	case <-time.After(time.Second):
		t.Fatal("admission read did not start")
	}
	if err := fixture.manager.CloseServiceChannel(ts.Generation, sc.Handle); err != nil {
		t.Fatal(err)
	}
	select {
	case err := <-done:
		if err == nil {
			t.Fatal("blocked admission survived teardown")
		}
	case <-time.After(time.Second):
		t.Fatal("teardown did not cancel blocked admission")
	}
	if fixture.manager.Usage().PendingAdmissions != 0 {
		t.Fatalf("pending admission leaked: %+v", fixture.manager.Usage())
	}
}

func TestApplicationStreamRefillIsAmortizedAtWatermark(t *testing.T) {
	fixture := newFixture(t)
	fixture.manager.limits.MaxStreams = 64
	fixture.manager.limits.MaxStateBytes = 16 * 1024
	ts := fixture.createTS(t, 1)
	sc := fixture.createSC(t, fixture.channelRequest(ts.Generation, 1))
	wireChannel := fixture.opener.channels[0]
	for index := uint64(1); index <= 48; index++ {
		wireChannel.next = &testApplicationWire{id: corestate.StreamID(index * 4), read: []byte{0}}
		stream, err := fixture.manager.OpenApplicationStream(context.Background(), ts.Generation, sc.Handle)
		if err != nil {
			t.Fatalf("stream %d: %v", index, err)
		}
		if err := stream.Close(); err != nil {
			t.Fatalf("close stream %d: %v", index, err)
		}
	}
	if wireChannel.refillCalls != 1 {
		t.Fatalf("refill calls = %d, want 1", wireChannel.refillCalls)
	}
	snapshot, err := fixture.manager.CreditSnapshot(ts.Generation, sc.Handle)
	if err != nil || snapshot.CurrentEpoch != 2 || snapshot.DrainingEpoch != 0 || snapshot.Available != 64 {
		t.Fatalf("refill snapshot = %+v, %v", snapshot, err)
	}
}

func TestApplicationStreamSequentialRefillsRetireInactiveEpochs(t *testing.T) {
	fixture := newFixture(t)
	fixture.manager.limits.MaxStreams = 128
	fixture.manager.limits.MaxStateBytes = 32 * 1024
	ts := fixture.createTS(t, 1)
	sc := fixture.createSC(t, fixture.channelRequest(ts.Generation, 1))
	wireChannel := fixture.opener.channels[0]
	for index := uint64(1); index <= 128; index++ {
		wireChannel.next = &testApplicationWire{id: corestate.StreamID(index * 4), read: []byte{0}}
		stream, err := fixture.manager.OpenApplicationStream(context.Background(), ts.Generation, sc.Handle)
		if err != nil {
			t.Fatalf("stream %d: %v", index, err)
		}
		if err := stream.Close(); err != nil {
			t.Fatalf("close %d: %v", index, err)
		}
	}
	if wireChannel.refillCalls != 2 {
		t.Fatalf("refills = %d, want 2", wireChannel.refillCalls)
	}
	snapshot, err := fixture.manager.CreditSnapshot(ts.Generation, sc.Handle)
	if err != nil || snapshot.CurrentEpoch != 3 || snapshot.DrainingEpoch != 0 || snapshot.Available != 32 {
		t.Fatalf("snapshot = %+v, %v", snapshot, err)
	}
}

func TestApplicationStreamDuplicateIDCloseAndSiblingIsolation(t *testing.T) {
	fixture := newFixture(t)
	ts := fixture.createTS(t, 1)
	sc := fixture.createSC(t, fixture.channelRequest(ts.Generation, 1))
	wireChannel := fixture.opener.channels[0]
	wireChannel.next = &testApplicationWire{id: 4, read: []byte{0}}
	first, err := fixture.manager.OpenApplicationStream(context.Background(), ts.Generation, sc.Handle)
	if err != nil {
		t.Fatal(err)
	}
	wireChannel.next = &testApplicationWire{id: 8, read: []byte{0}}
	second, err := fixture.manager.OpenApplicationStream(context.Background(), ts.Generation, sc.Handle)
	if err != nil {
		t.Fatal(err)
	}
	if err := first.Close(); err != nil {
		t.Fatal(err)
	}
	if err := first.Close(); err != nil {
		t.Fatalf("repeated close: %v", err)
	}
	if _, err := second.Write([]byte("sibling")); err != nil {
		t.Fatalf("sibling write: %v", err)
	}
	wireChannel.next = &testApplicationWire{id: 8, read: []byte{0}}
	if _, err := fixture.manager.OpenApplicationStream(context.Background(), ts.Generation, sc.Handle); !errors.Is(err, ErrDuplicateStream) {
		t.Fatalf("duplicate StreamID = %v, want ErrDuplicateStream", err)
	}
	if err := fixture.manager.CloseTransportSession(ts.Generation); err != nil {
		t.Fatal(err)
	}
	if _, err := second.Write([]byte("after-close")); !errors.Is(err, ErrStreamClosed) {
		t.Fatalf("post teardown write = %v, want ErrStreamClosed", err)
	}
}

type testApplicationWire struct {
	mu          sync.Mutex
	id          corestate.StreamID
	read        []byte
	writes      [][]byte
	closed      bool
	beforeRead  func()
	readStarted chan struct{}
	closeSignal chan struct{}
	closeOnce   sync.Once
}

func (wire *testApplicationWire) StreamID() corestate.StreamID { return wire.id }
func (wire *testApplicationWire) Write(value []byte) (int, error) {
	wire.mu.Lock()
	defer wire.mu.Unlock()
	copyValue := append([]byte(nil), value...)
	wire.writes = append(wire.writes, copyValue)
	return len(value), nil
}
func (wire *testApplicationWire) Read(value []byte) (int, error) {
	if wire.readStarted != nil {
		wire.closeOnce.Do(func() { close(wire.readStarted) })
		<-wire.closeSignal
		return 0, io.ErrClosedPipe
	}
	wire.mu.Lock()
	hook := wire.beforeRead
	wire.beforeRead = nil
	wire.mu.Unlock()
	if hook != nil {
		hook()
	}
	wire.mu.Lock()
	defer wire.mu.Unlock()
	if len(wire.read) == 0 {
		return 0, io.EOF
	}
	n := copy(value, wire.read)
	wire.read = wire.read[n:]
	return n, nil
}
func (wire *testApplicationWire) Close() error {
	wire.mu.Lock()
	wire.closed = true
	wire.mu.Unlock()
	if wire.closeSignal != nil {
		select {
		case <-wire.closeSignal:
		default:
			close(wire.closeSignal)
		}
	}
	return nil
}
