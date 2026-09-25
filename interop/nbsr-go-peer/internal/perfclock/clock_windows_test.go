package perfclock

import (
	"testing"
	"time"
)

func TestWindowsElapsedClockPreservesTwoHourIntervals(t *testing.T) {
	// Synthetic starting tick on the real QPC clock: no two-hour sleep required.
	start := Now() - performanceCounterFrequency*7200
	elapsed := Since(start)
	if elapsed < int64(2*time.Hour) || elapsed > int64(2*time.Hour+time.Second) {
		t.Fatalf("two-hour interval corrupted: frequency=%d elapsed_ns=%d", performanceCounterFrequency, elapsed)
	}
}

func TestCounterNanosecondsExactSignedConversion(t *testing.T) {
	for _, test := range []struct{ ticks, frequency, want int64 }{
		{0, 10_000_000, 0},
		{1, 10_000_000, 100},
		{1_234_567, 10_000_000, 123_456_700},
		{72_000_000_000, 10_000_000, 7_200_000_000_000},
		{-72_000_000_000, 10_000_000, -7_200_000_000_000},
		{9_999_999_999, 10_000_000_000, 999_999_999},
		{1<<63 - 1, 1_000_000_000, 1<<63 - 1},
		{-1 << 63, 1_000_000_000, -1 << 63},
	} {
		if got := counterNanoseconds(test.ticks, test.frequency); got != test.want {
			t.Fatalf("ticks=%d frequency=%d: got %d, want %d", test.ticks, test.frequency, got, test.want)
		}
	}
}
