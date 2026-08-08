package perfclock

import "syscall"

var (
	kernel32                    = syscall.NewLazyDLL("kernel32.dll")
	queryPerformanceCounter     = kernel32.NewProc("QueryPerformanceCounter")
	queryPerformanceFrequency   = kernel32.NewProc("QueryPerformanceFrequency")
	performanceCounterFrequency = frequency()
)

func frequency() int64 {
	var value int64
	result, _, callError := queryPerformanceFrequency.Call(uintptr(unsafePointer(&value)))
	if result == 0 {
		panic(callError)
	}
	return value
}

func Now() int64 {
	var value int64
	result, _, callError := queryPerformanceCounter.Call(uintptr(unsafePointer(&value)))
	if result == 0 {
		panic(callError)
	}
	return value
}

func Since(start int64) int64 {
	delta := Now() - start
	return delta * 1_000_000_000 / performanceCounterFrequency
}
