package client

import (
	"testing"
	"time"
)

func TestIdleObservationWaitsForAllOwnership(t *testing.T) {
	calls := 0
	got, ok := awaitRuntimeIdle(func() runtimeIdleSnapshot {
		calls++
		if calls == 1 {
			return runtimeIdleSnapshot{0, 1, 1}
		}
		return runtimeIdleSnapshot{}
	}, time.Now().Add(time.Second))
	if !ok || got != (runtimeIdleSnapshot{}) || calls != 2 {
		t.Fatalf("accepted early: %+v %v calls=%d", got, ok, calls)
	}
}
func TestIdleObservationRetainsFailureSnapshot(t *testing.T) {
	want := runtimeIdleSnapshot{0, 0, 1}
	got, ok := awaitRuntimeIdle(func() runtimeIdleSnapshot { return want }, time.Now().Add(-time.Second))
	if ok || got != want {
		t.Fatalf("lost failure: %+v %v", got, ok)
	}
}
func TestIdleObservationAcceptsAlreadyIdle(t *testing.T) {
	got, ok := awaitRuntimeIdle(func() runtimeIdleSnapshot { return runtimeIdleSnapshot{} }, time.Now().Add(-time.Second))
	if !ok || got != (runtimeIdleSnapshot{}) {
		t.Fatal("idle rejected")
	}
}

func TestIdleObservationEachCounterBlocksUntilReleased(t *testing.T) {
	for _, tc := range []struct {
		name  string
		value runtimeIdleSnapshot
	}{
		{"active", runtimeIdleSnapshot{1, 0, 0}},
		{"flows", runtimeIdleSnapshot{0, 1, 0}},
		{"refs", runtimeIdleSnapshot{0, 0, 1}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			calls := 0
			got, ok := awaitRuntimeIdle(func() runtimeIdleSnapshot {
				calls++
				if calls < 3 {
					return tc.value
				}
				return runtimeIdleSnapshot{}
			}, time.Now().Add(time.Second))
			if !ok || got != (runtimeIdleSnapshot{}) || calls != 3 {
				t.Fatalf("counter ignored: %+v %v calls=%d", got, ok, calls)
			}
		})
	}
}
func TestIdleObservationPersistentCounterFailsAtDeadline(t *testing.T) {
	for _, tc := range []struct {
		name  string
		value runtimeIdleSnapshot
	}{
		{"active", runtimeIdleSnapshot{1, 0, 0}},
		{"flows", runtimeIdleSnapshot{0, 1, 0}},
		{"refs", runtimeIdleSnapshot{0, 0, 1}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			calls := 0
			deadline := time.Now().Add(3 * time.Millisecond)
			got, ok := awaitRuntimeIdle(func() runtimeIdleSnapshot { calls++; return tc.value }, deadline)
			if ok || got != tc.value || calls < 1 || time.Now().Before(deadline) {
				t.Fatalf("persistent ownership accepted: %+v %v calls=%d", got, ok, calls)
			}
		})
	}
}
