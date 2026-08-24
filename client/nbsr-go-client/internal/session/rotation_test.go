package session

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"
)

func TestRotateTransportSessionAtomicallyHandsOffAndPinsOldWork(t *testing.T) {
	fixture := newFixture(t)
	a := fixture.createTS(t, 1)
	oldChannel := fixture.createSC(t, fixture.channelRequest(a.Generation, 1))

	result, err := fixture.manager.RotateTransportSession(context.Background(), RotationRequest{
		CurrentGeneration: a.Generation,
		Replacement:       fixture.sessionSpec(2),
		Trigger:           RotationExplicit,
	})
	if err != nil {
		t.Fatal(err)
	}
	if result.Previous.State != TransportDraining || result.Current.Generation != 2 || result.Current.State != TransportCurrent {
		t.Fatalf("handoff = %+v", result)
	}
	if current, err := fixture.manager.CurrentTransportSession(a.ReuseKey); err != nil || current.Generation != 2 {
		t.Fatalf("current = %+v, %v", current, err)
	}
	if old, err := fixture.manager.ServiceChannel(1, oldChannel.Handle); err != nil || old.Generation != 1 {
		t.Fatalf("old channel moved or closed: %+v, %v", old, err)
	}
	if _, err := fixture.manager.CreateServiceChannel(context.Background(), fixture.channelRequest(1, 2)); !errors.Is(err, ErrGenerationNotCurrent) {
		t.Fatalf("new work on A = %v", err)
	}
	fixture.createSC(t, fixture.channelRequest(2, 3))
	if _, err := fixture.manager.RotateTransportSession(context.Background(), RotationRequest{CurrentGeneration: 2, Replacement: fixture.sessionSpec(3), Trigger: RotationExplicit}); !errors.Is(err, ErrGenerationCapacity) {
		t.Fatalf("third generation = %v", err)
	}
}

func TestRotationFailureKeepsOnlyEligibleCurrent(t *testing.T) {
	fixture := newFixture(t)
	a := fixture.createTS(t, 1)
	fixture.connector.fail = ErrTransport
	if _, err := fixture.manager.RotateTransportSession(context.Background(), RotationRequest{CurrentGeneration: 1, Replacement: fixture.sessionSpec(2), Trigger: RotationExplicit}); !errors.Is(err, ErrTransport) {
		t.Fatalf("benign failure = %v", err)
	}
	if current, err := fixture.manager.CurrentTransportSession(a.ReuseKey); err != nil || current.Generation != 1 {
		t.Fatalf("A not preserved = %+v, %v", current, err)
	}
	fixture.connector.fail = ErrTransport
	if _, err := fixture.manager.RotateTransportSession(context.Background(), RotationRequest{CurrentGeneration: 1, Replacement: fixture.sessionSpec(2), Trigger: RotationTransportFailure}); !errors.Is(err, ErrTransport) {
		t.Fatalf("failure trigger = %v", err)
	}
	if _, err := fixture.manager.CurrentTransportSession(a.ReuseKey); !errors.Is(err, ErrGenerationNotCurrent) {
		t.Fatalf("invalid A remained current: %v", err)
	}
}

func TestCoalescedRotationEscalatesAndCreatesOneReplacement(t *testing.T) {
	fixture := newFixture(t)
	fixture.createTS(t, 1)
	fixture.connector.block = make(chan struct{})
	first := make(chan error, 1)
	go func() {
		_, err := fixture.manager.RotateTransportSession(context.Background(), RotationRequest{CurrentGeneration: 1, Replacement: fixture.sessionSpec(2), Trigger: RotationExplicit})
		first <- err
	}()
	<-fixture.connector.started
	second := make(chan error, 1)
	go func() {
		_, err := fixture.manager.RotateTransportSession(context.Background(), RotationRequest{CurrentGeneration: 1, Replacement: fixture.sessionSpec(2), Trigger: RotationRevocation})
		second <- err
	}()
	for fixture.manager.Usage().RotationWaiters != 1 {
		time.Sleep(time.Millisecond)
	}
	close(fixture.connector.block)
	if err := <-first; err != nil {
		t.Fatal(err)
	}
	if err := <-second; err != nil {
		t.Fatal(err)
	}
	if fixture.connector.calls != 2 { // one cold start plus one replacement
		t.Fatalf("connect calls = %d", fixture.connector.calls)
	}
	if got := fixture.manager.EffectiveTrigger(fixture.sessionSpec(1).ReuseKey); got != RotationRevocation {
		t.Fatalf("effective trigger = %v", got)
	}
}

func TestDrainingDeadlineClosesDescendantsAndReleasesSlot(t *testing.T) {
	fixture := newFixture(t)
	fixture.manager.limits.DrainTimeout = 20 * time.Millisecond
	a := fixture.createTS(t, 1)
	channel := fixture.createSC(t, fixture.channelRequest(1, 1))
	if _, err := fixture.manager.RotateTransportSession(context.Background(), RotationRequest{CurrentGeneration: 1, Replacement: fixture.sessionSpec(2), Trigger: RotationExplicit}); err != nil {
		t.Fatal(err)
	}
	deadline := time.After(time.Second)
	for {
		if _, err := fixture.manager.ServiceChannel(1, channel.Handle); errors.Is(err, ErrChannelClosed) {
			break
		}
		select {
		case <-deadline:
			t.Fatal("draining generation did not expire")
		default:
			time.Sleep(time.Millisecond)
		}
	}
	for !fixture.connector.transports[0].isClosed() {
		select {
		case <-deadline:
			t.Fatal("expired A transport remained open")
		default:
			time.Sleep(time.Millisecond)
		}
	}
	if _, err := fixture.manager.RotateTransportSession(context.Background(), RotationRequest{CurrentGeneration: 2, Replacement: fixture.sessionSpec(3), Trigger: RotationExplicit}); err != nil {
		t.Fatalf("slot not released after deadline: %v", err)
	}
	_ = a
}

func TestFailedCurrentBDoesNotPromoteDrainingAOrCreateC(t *testing.T) {
	fixture := newFixture(t)
	a := fixture.createTS(t, 1)
	fixture.createSC(t, fixture.channelRequest(1, 1))
	if _, err := fixture.manager.RotateTransportSession(context.Background(), RotationRequest{CurrentGeneration: 1, Replacement: fixture.sessionSpec(2), Trigger: RotationExplicit}); err != nil {
		t.Fatal(err)
	}
	if err := fixture.manager.FailTransportSession(2, RotationTransportFailure); err != nil {
		t.Fatal(err)
	}
	if _, err := fixture.manager.CurrentTransportSession(a.ReuseKey); !errors.Is(err, ErrGenerationNotCurrent) {
		t.Fatalf("A was promoted or B stayed current: %v", err)
	}
	if _, err := fixture.manager.RotateTransportSession(context.Background(), RotationRequest{CurrentGeneration: 2, Replacement: fixture.sessionSpec(3), Trigger: RotationTransportFailure}); !errors.Is(err, ErrGenerationCapacity) {
		t.Fatalf("C before A removal = %v", err)
	}
	if err := fixture.manager.CloseTransportSession(1); err != nil {
		t.Fatal(err)
	}
	if _, err := fixture.manager.RotateTransportSession(context.Background(), RotationRequest{CurrentGeneration: 2, Replacement: fixture.sessionSpec(3), Trigger: RotationTransportFailure}); err != nil {
		t.Fatalf("fresh C after A removal = %v", err)
	}
}

func TestRotationDoesNotReplayApplicationPayload(t *testing.T) {
	fixture := newFixture(t)
	a := fixture.createTS(t, 1)
	sc := fixture.createSC(t, fixture.channelRequest(1, 1))
	wire := &testApplicationWire{id: 4, read: []byte{0}}
	fixture.opener.channels[0].next = wire
	stream, err := fixture.manager.OpenApplicationStream(context.Background(), 1, sc.Handle)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := stream.Write([]byte("once")); err != nil {
		t.Fatal(err)
	}
	if _, err := fixture.manager.RotateTransportSession(context.Background(), RotationRequest{CurrentGeneration: a.Generation, Replacement: fixture.sessionSpec(2), Trigger: RotationTransportFailure}); err != nil {
		t.Fatal(err)
	}
	if len(wire.writes) != 2 {
		t.Fatalf("A writes changed during rotation: %d", len(wire.writes))
	}
	if len(fixture.opener.channels) != 1 {
		t.Fatalf("rotation opened/migrated channel: %d", len(fixture.opener.channels))
	}
}

func TestReplayCapacityReplacementCannotResetOrReserveCreditOnA(t *testing.T) {
	fixture := newFixture(t)
	a := fixture.createTS(t, 1)
	sc := fixture.createSC(t, fixture.channelRequest(1, 1))
	credit, err := fixture.manager.ReserveStreamCredit(1, sc.Handle)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := fixture.manager.RotateTransportSession(context.Background(), RotationRequest{CurrentGeneration: a.Generation, Replacement: fixture.sessionSpec(2), Trigger: RotationReplayCapacity}); err != nil {
		t.Fatal(err)
	}
	credit.Slot++
	if _, err := fixture.manager.ReserveSpecificStreamCredit(credit); !errors.Is(err, ErrCreditClosed) {
		t.Fatalf("specific credit admitted on draining A = %v", err)
	}
	if _, err := fixture.manager.ReserveStreamCredit(1, sc.Handle); !errors.Is(err, ErrCreditClosed) {
		t.Fatalf("ordinary credit admitted on draining A = %v", err)
	}
}

func TestEscalatedFailureCannotRestoreA(t *testing.T) {
	fixture := newFixture(t)
	a := fixture.createTS(t, 1)
	fixture.connector.fail = ErrTransport
	fixture.connector.block = make(chan struct{})
	leader := make(chan error, 1)
	go func() {
		_, err := fixture.manager.RotateTransportSession(context.Background(), RotationRequest{CurrentGeneration: 1, Replacement: fixture.sessionSpec(2), Trigger: RotationExplicit})
		leader <- err
	}()
	<-fixture.connector.started
	follower := make(chan error, 1)
	go func() {
		_, err := fixture.manager.RotateTransportSession(context.Background(), RotationRequest{CurrentGeneration: 1, Replacement: fixture.sessionSpec(2), Trigger: RotationRevocation})
		follower <- err
	}()
	for fixture.manager.Usage().RotationWaiters != 1 {
		time.Sleep(time.Millisecond)
	}
	close(fixture.connector.block)
	if !errors.Is(<-leader, ErrTransport) || !errors.Is(<-follower, ErrTransport) {
		t.Fatal("coalesced callers did not receive replacement failure")
	}
	if _, err := fixture.manager.CurrentTransportSession(a.ReuseKey); !errors.Is(err, ErrGenerationNotCurrent) {
		t.Fatalf("revocation escalation was masked: %v", err)
	}
}

func TestRecoveryAttemptsAndCancellationAreBounded(t *testing.T) {
	fixture := newFixture(t)
	fixture.createTS(t, 1)
	fixture.connector.fail = ErrTransport
	if _, err := fixture.manager.RecoverTransportSession(context.Background(), RotationRequest{CurrentGeneration: 1, Replacement: fixture.sessionSpec(2), Trigger: RotationExplicit}); !errors.Is(err, ErrRecoveryExhausted) {
		t.Fatalf("recovery exhaustion = %v", err)
	}
	if fixture.connector.calls != 3 { // cold start plus exactly two attempts
		t.Fatalf("bounded connect calls = %d", fixture.connector.calls)
	}
	fixture.connector.fail = nil
	fixture.connector.block = make(chan struct{})
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() {
		_, err := fixture.manager.RotateTransportSession(ctx, RotationRequest{CurrentGeneration: 1, Replacement: fixture.sessionSpec(2), Trigger: RotationExplicit})
		done <- err
	}()
	<-fixture.connector.started
	cancel()
	if err := <-done; !errors.Is(err, context.Canceled) {
		t.Fatalf("canceled replacement = %v", err)
	}
	if usage := fixture.manager.Usage(); usage.PendingRotations != 0 || usage.PendingSessions != 0 || usage.RotationWaiters != 0 {
		t.Fatalf("pending recovery leaked = %+v", usage)
	}
}

func TestRotationFinalBarrierRejectsAuthorityChangeAndClosesB(t *testing.T) {
	fixture := newFixture(t)
	a := fixture.createTS(t, 1)
	fixture.connector.beforeReturn = fixture.gate.invalidate
	if _, err := fixture.manager.RotateTransportSession(context.Background(), RotationRequest{CurrentGeneration: 1, Replacement: fixture.sessionSpec(2), Trigger: RotationExplicit}); !errors.Is(err, ErrAuthorityStale) {
		t.Fatalf("authority change = %v", err)
	}
	if _, err := fixture.manager.CurrentTransportSession(a.ReuseKey); !errors.Is(err, ErrGenerationNotCurrent) {
		t.Fatalf("stale A remained current = %v", err)
	}
	if len(fixture.connector.transports) != 2 || !fixture.connector.transports[1].isClosed() {
		t.Fatal("stale B transport was published or leaked")
	}
}

func TestTransportTeardownCancelsPendingReplacement(t *testing.T) {
	fixture := newFixture(t)
	fixture.createTS(t, 1)
	fixture.connector.block = make(chan struct{})
	done := make(chan error, 1)
	go func() {
		_, err := fixture.manager.RotateTransportSession(context.Background(), RotationRequest{CurrentGeneration: 1, Replacement: fixture.sessionSpec(2), Trigger: RotationExplicit})
		done <- err
	}()
	<-fixture.connector.started
	if err := fixture.manager.CloseTransportSession(1); err != nil {
		t.Fatal(err)
	}
	select {
	case err := <-done:
		if !errors.Is(err, context.Canceled) && !errors.Is(err, ErrGenerationNotCurrent) {
			t.Fatalf("teardown result = %v", err)
		}
	case <-time.After(time.Second):
		t.Fatal("teardown did not cancel pending replacement")
	}
	if usage := fixture.manager.Usage(); usage.PendingRotations != 0 || usage.PendingSessions != 0 {
		t.Fatalf("pending replacement leaked = %+v", usage)
	}
}

func TestColdStartRestoresNoLiveGenerationOwnership(t *testing.T) {
	fixture := newFixture(t)
	fixture.createTS(t, 1)
	fixture.createSC(t, fixture.channelRequest(1, 1))

	restarted, err := newManager(fixture.manager.limits, fixture.clock, fixture.gate, fixture.registry, &testConnector{started: make(chan struct{}, 1)}, &testOpener{started: make(chan struct{}, 1)})
	if err != nil {
		t.Fatal(err)
	}
	if usage := restarted.Usage(); usage.Sessions != 0 || usage.Channels != 0 || usage.ApplicationStreams != 0 || usage.PendingRotations != 0 {
		t.Fatalf("cold start resurrected live ownership = %+v", usage)
	}
	if _, err := restarted.CurrentTransportSession(fixture.sessionSpec(1).ReuseKey); !errors.Is(err, ErrGenerationNotCurrent) {
		t.Fatalf("cold start current = %v", err)
	}
	if _, err := restarted.CreateTransportSession(context.Background(), fixture.sessionSpec(2)); err != nil {
		t.Fatalf("fresh post-restart generation = %v", err)
	}
}

var _ = sync.Mutex{}
