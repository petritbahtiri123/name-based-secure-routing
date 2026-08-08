package perfclock

import "testing"

func TestQueryPerformanceCounterProvidesPositiveSubMillisecondDurations(t *testing.T) {
	start := Now()
	value := uint64(1)
	for index := 0; index < 1000; index++ {
		value = value*6364136223846793005 + 1
	}
	if value == 0 {
		t.Fatal("unexpected arithmetic result")
	}
	elapsed := Since(start)
	if elapsed <= 0 || elapsed >= 1_000_000 {
		t.Fatalf("expected positive sub-millisecond duration, got %d ns", elapsed)
	}
}
