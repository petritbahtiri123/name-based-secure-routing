package perfclock

import (
	"testing"
	"time"
)

func TestLinuxMonotonicElapsedNanoseconds(t *testing.T) {
	start := Now()
	previous := start
	for range 1000 {
		current := Now()
		if current < previous {
			t.Fatal("monotonic clock went backwards")
		}
		previous = current
	}
	time.Sleep(time.Millisecond)
	if elapsed := Since(start); elapsed < int64(time.Millisecond) {
		t.Fatalf("elapsed nanoseconds too small: %d", elapsed)
	}
}
