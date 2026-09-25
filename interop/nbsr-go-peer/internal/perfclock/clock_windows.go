package perfclock

import (
	"math/bits"
	"reflect"
	"syscall"
)

var (
	kernel32                    = syscall.NewLazyDLL("kernel32.dll")
	queryPerformanceCounter     = kernel32.NewProc("QueryPerformanceCounter")
	queryPerformanceFrequency   = kernel32.NewProc("QueryPerformanceFrequency")
	performanceCounterFrequency = frequency()
)

func frequency() int64 {
	var value int64
	result, _, callError := queryPerformanceFrequency.Call(reflect.ValueOf(&value).Pointer())
	if result == 0 {
		panic(callError)
	}
	return value
}

func Now() int64 {
	var value int64
	result, _, callError := queryPerformanceCounter.Call(reflect.ValueOf(&value).Pointer())
	if result == 0 {
		panic(callError)
	}
	return value
}

func Since(start int64) int64 {
	return counterNanoseconds(Now()-start, performanceCounterFrequency)
}

func counterNanoseconds(delta, frequency int64) int64 {
	ticks := uint64(delta)
	if delta < 0 {
		ticks = uint64(-delta)
	}
	// Widen the intermediate product: even a representable elapsed duration
	// can overflow delta*1e9 before division by the QPC frequency.
	hi, lo := bits.Mul64(ticks, 1_000_000_000)
	nanoseconds, _ := bits.Div64(hi, lo, uint64(frequency))
	if delta < 0 {
		return -int64(nanoseconds)
	}
	return int64(nanoseconds)
}
