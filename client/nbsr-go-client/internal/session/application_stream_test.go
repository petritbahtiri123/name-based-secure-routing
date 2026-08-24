package session

import (
	"bytes"
	"context"
	"errors"
	"io"
	"sync"
	"testing"

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
		if _, err := fixture.manager.OpenApplicationStream(context.Background(), ts.Generation, sc.Handle); err != nil {
			t.Fatalf("stream %d: %v", index, err)
		}
	}
	if wireChannel.refillCalls != 1 {
		t.Fatalf("refill calls = %d, want 1", wireChannel.refillCalls)
	}
	snapshot, err := fixture.manager.CreditSnapshot(ts.Generation, sc.Handle)
	if err != nil || snapshot.CurrentEpoch != 2 || snapshot.DrainingEpoch != 1 || snapshot.Available != 64 {
		t.Fatalf("refill snapshot = %+v, %v", snapshot, err)
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
	mu         sync.Mutex
	id         corestate.StreamID
	read       []byte
	writes     [][]byte
	closed     bool
	beforeRead func()
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
	return nil
}
