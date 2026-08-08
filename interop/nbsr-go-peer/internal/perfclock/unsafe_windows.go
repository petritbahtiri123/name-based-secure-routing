package perfclock

import "unsafe"

func unsafePointer(value *int64) unsafe.Pointer { return unsafe.Pointer(value) }
