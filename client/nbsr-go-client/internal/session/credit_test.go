package session

import (
	"errors"
	"sync"
	"testing"
)

func TestStreamCreditInitialWindowAndOneUseReservation(t *testing.T) {
	fixture := newFixture(t)
	ts := fixture.createTS(t, 1)
	sc := fixture.createSC(t, fixture.channelRequest(ts.Generation, 1))

	snapshot, err := fixture.manager.CreditSnapshot(ts.Generation, sc.Handle)
	if err != nil {
		t.Fatal(err)
	}
	if snapshot.CurrentEpoch != 1 || snapshot.Available != 64 || snapshot.DrainingEpoch != 0 || snapshot.RefillPending {
		t.Fatalf("initial credit snapshot = %+v", snapshot)
	}
	first, err := fixture.manager.ReserveStreamCredit(ts.Generation, sc.Handle)
	if err != nil {
		t.Fatal(err)
	}
	if first.Epoch != 1 || first.Slot != 0 || first.Generation != ts.Generation || first.Handle != sc.Handle || first.ChannelID != sc.ChannelID {
		t.Fatalf("first reservation = %+v", first)
	}
	if _, err := fixture.manager.ReserveSpecificStreamCredit(first); !errors.Is(err, ErrCreditConsumed) {
		t.Fatalf("duplicate reservation = %v, want ErrCreditConsumed", err)
	}
}

func TestStreamCreditBindingAndTeardownFailClosed(t *testing.T) {
	fixture := newFixture(t)
	ts := fixture.createTS(t, 1)
	first := fixture.createSC(t, fixture.channelRequest(ts.Generation, 1))
	second := fixture.createSC(t, fixture.channelRequest(ts.Generation, 2))
	credit, err := fixture.manager.ReserveStreamCredit(ts.Generation, first.Handle)
	if err != nil {
		t.Fatal(err)
	}
	wrongSC := credit
	wrongSC.Handle = second.Handle
	if _, err := fixture.manager.ReserveSpecificStreamCredit(wrongSC); !errors.Is(err, ErrCreditBinding) {
		t.Fatalf("cross-SC reservation = %v, want ErrCreditBinding", err)
	}
	wrongTS := credit
	wrongTS.Generation++
	if _, err := fixture.manager.ReserveSpecificStreamCredit(wrongTS); !errors.Is(err, ErrCreditBinding) {
		t.Fatalf("cross-TS reservation = %v, want ErrCreditBinding", err)
	}
	if err := fixture.manager.CloseServiceChannel(ts.Generation, first.Handle); err != nil {
		t.Fatal(err)
	}
	if _, err := fixture.manager.CreditSnapshot(ts.Generation, first.Handle); !errors.Is(err, ErrCreditClosed) {
		t.Fatalf("SC teardown credit = %v, want ErrCreditClosed", err)
	}
	if err := fixture.manager.CloseTransportSession(ts.Generation); err != nil {
		t.Fatal(err)
	}
	if _, err := fixture.manager.CreditSnapshot(ts.Generation, second.Handle); !errors.Is(err, ErrCreditClosed) {
		t.Fatalf("TS teardown credit = %v, want ErrCreditClosed", err)
	}
}

func TestStreamCreditWatermarkRefillAndMaximumTwoEpochs(t *testing.T) {
	fixture := newFixture(t)
	ts := fixture.createTS(t, 1)
	sc := fixture.createSC(t, fixture.channelRequest(ts.Generation, 1))
	for range 48 {
		if _, err := fixture.manager.ReserveStreamCredit(ts.Generation, sc.Handle); err != nil {
			t.Fatal(err)
		}
	}
	next, err := fixture.manager.BeginCreditRefill(ts.Generation, sc.Handle)
	if err != nil || next != 2 {
		t.Fatalf("BeginCreditRefill = %d, %v", next, err)
	}
	if _, err := fixture.manager.BeginCreditRefill(ts.Generation, sc.Handle); !errors.Is(err, ErrRefillPending) {
		t.Fatalf("duplicate refill = %v, want ErrRefillPending", err)
	}
	if err := fixture.manager.CompleteCreditRefill(ts.Generation, sc.Handle, next); err != nil {
		t.Fatal(err)
	}
	snapshot, err := fixture.manager.CreditSnapshot(ts.Generation, sc.Handle)
	if err != nil {
		t.Fatal(err)
	}
	if snapshot.CurrentEpoch != 2 || snapshot.DrainingEpoch != 1 || snapshot.Available != 64 {
		t.Fatalf("refilled snapshot = %+v", snapshot)
	}
	for range 48 {
		if _, err := fixture.manager.ReserveStreamCredit(ts.Generation, sc.Handle); err != nil {
			t.Fatal(err)
		}
	}
	if _, err := fixture.manager.BeginCreditRefill(ts.Generation, sc.Handle); !errors.Is(err, ErrEpochCapacity) {
		t.Fatalf("third epoch = %v, want ErrEpochCapacity", err)
	}
}

func TestConcurrentStreamCreditConsumptionIsBounded(t *testing.T) {
	fixture := newFixture(t)
	ts := fixture.createTS(t, 1)
	sc := fixture.createSC(t, fixture.channelRequest(ts.Generation, 1))
	var wg sync.WaitGroup
	results := make(chan CreditReservation, 80)
	errs := make(chan error, 80)
	for range 80 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			credit, err := fixture.manager.ReserveStreamCredit(ts.Generation, sc.Handle)
			if err != nil {
				errs <- err
				return
			}
			results <- credit
		}()
	}
	wg.Wait()
	close(results)
	close(errs)
	seen := map[uint8]bool{}
	for credit := range results {
		if seen[credit.Slot] {
			t.Fatalf("duplicate slot %d", credit.Slot)
		}
		seen[credit.Slot] = true
	}
	if len(seen) != 64 {
		t.Fatalf("successful reservations = %d, want 64", len(seen))
	}
	for err := range errs {
		if !errors.Is(err, ErrCreditExhausted) {
			t.Fatalf("overflow error = %v", err)
		}
	}
}

func TestStreamCreditRevocationInvalidatesUnusedCredits(t *testing.T) {
	fixture := newFixture(t)
	ts := fixture.createTS(t, 1)
	sc := fixture.createSC(t, fixture.channelRequest(ts.Generation, 1))
	fixture.gate.invalidate()
	if _, err := fixture.manager.ReserveStreamCredit(ts.Generation, sc.Handle); !errors.Is(err, ErrCreditClosed) {
		t.Fatalf("reservation after revocation = %v, want ErrCreditClosed", err)
	}
	if usage := fixture.manager.Usage(); usage.Channels != 0 {
		t.Fatalf("revoked channel remains owned: %+v", usage)
	}
}

func TestStreamCreditRefillCancellationAndConcurrentCoalescing(t *testing.T) {
	fixture := newFixture(t)
	ts := fixture.createTS(t, 1)
	sc := fixture.createSC(t, fixture.channelRequest(ts.Generation, 1))
	if _, err := fixture.manager.BeginCreditRefill(ts.Generation, sc.Handle); !errors.Is(err, ErrRefillNotDue) {
		t.Fatalf("early refill = %v, want ErrRefillNotDue", err)
	}
	for range 48 {
		if _, err := fixture.manager.ReserveStreamCredit(ts.Generation, sc.Handle); err != nil {
			t.Fatal(err)
		}
	}
	var wg sync.WaitGroup
	results := make(chan error, 16)
	for range 16 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			_, err := fixture.manager.BeginCreditRefill(ts.Generation, sc.Handle)
			results <- err
		}()
	}
	wg.Wait()
	close(results)
	successes := 0
	for err := range results {
		if err == nil {
			successes++
		} else if !errors.Is(err, ErrRefillPending) {
			t.Fatalf("coalesced refill error = %v", err)
		}
	}
	if successes != 1 {
		t.Fatalf("successful refill leaders = %d, want 1", successes)
	}
	if err := fixture.manager.CancelCreditRefill(ts.Generation, sc.Handle); err != nil {
		t.Fatal(err)
	}
	if snapshot, err := fixture.manager.CreditSnapshot(ts.Generation, sc.Handle); err != nil || snapshot.RefillPending {
		t.Fatalf("snapshot after cancel = %+v, %v", snapshot, err)
	}
}
