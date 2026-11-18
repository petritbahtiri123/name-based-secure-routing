package authority

import (
	"context"
	"errors"
	"testing"
)

func TestEnrollmentCommitRejectsMismatchedRequestBinding(t *testing.T) {
	r := validEnrollmentRequestPayload()
	b, e := EncodeEnrollmentRequestPayload(r)
	if e != nil {
		t.Fatal(e)
	}
	result := validEnrollmentResultPayloadBoundToRequest(r, b, EnrollmentStatusAccepted)
	for _, kind := range []string{"id", "digest"} {
		t.Run(kind, func(t *testing.T) {
			s := NewMemoryEnrollmentStateStore()
			x := result
			if kind == "id" {
				x.RequestID[0] ^= 127
			} else {
				x.RequestDigest[0] ^= 127
			}
			_, e := ApplyVerifiedEnrollmentResult(context.Background(), r, x, s, x.DeviceIdentity.CredentialNotBefore+10)
			_, found, _ := s.Load(context.Background())
			t.Logf("mismatch=%s error=%v stored=%v", kind, e, found)
			if !errors.Is(e, ErrBindingMismatch) || found {
				t.Error("expected binding rejection and empty store")
			}
		})
	}
}
func TestCoalescedCallerKeepsOwnDeadline(t *testing.T) {
	p, m, r := coalesceFixture(t)
	defer m.Close()
	start := r.DeadlineUnix - 1
	clock := &mutableClock{now: start}
	m.clock = clock
	r.DeadlineUnix = start + 10
	short := r
	short.RequestID[0]++
	short.DeadlineUnix = start + 1
	a := make(chan error, 1)
	b := make(chan error, 1)
	go func() { _, e := m.Acquire(context.Background(), r); a <- e }()
	awaitCoalesce(t, p.started)
	go func() { _, e := m.Acquire(context.Background(), short); b <- e }()
	awaitWaiters(t, m, 2)
	clock.set(start + 2)
	p.releaseOnce()
	ea, eb := <-a, <-b
	if ea != nil {
		t.Fatalf("unexpired initiator failed: %v", ea)
	}
	if !errors.Is(eb, ErrExpired) {
		t.Errorf("expired joiner received %v", eb)
	}
}

func TestEnrollmentCommitAcceptsMatchingRequestBinding(t *testing.T) {
	request := validEnrollmentRequestPayload()
	payload, err := EncodeEnrollmentRequestPayload(request)
	if err != nil {
		t.Fatal(err)
	}
	result := validEnrollmentResultPayloadBoundToRequest(request, payload, EnrollmentStatusAccepted)
	store := NewMemoryEnrollmentStateStore()
	_, err = ApplyVerifiedEnrollmentResult(context.Background(), request, result, store, result.DeviceIdentity.CredentialNotBefore+10)
	if err != nil {
		t.Fatal(err)
	}
	_, found, err := store.Load(context.Background())
	if err != nil || !found {
		t.Fatalf("matching result was not stored: found=%v err=%v", found, err)
	}
}
