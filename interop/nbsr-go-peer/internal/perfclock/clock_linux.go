package perfclock

import "time"

// Preserve Time's monotonic component. Values are process-relative nanoseconds,
// not Unix time, so wall-clock adjustments cannot change benchmark intervals.
var origin = time.Now()

func Now() int64 {
	return time.Since(origin).Nanoseconds()
}

func Since(start int64) int64 {
	return Now() - start
}
