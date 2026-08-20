package authority

import (
	"sync"
	"time"
)

const (
	enrollmentStateDirectorySuffix  = `NBSR\GoClient\Enrollment`
	enrollmentStateFileName         = "enrollment-state.bin"
	enrollmentStateLockFileName     = "enrollment-state.lock"
	enrollmentStateIntegrityKeyName = "enrollment-state.integrity-key"

	enrollmentStateLockAcquireTimeout = 2 * time.Second
	enrollmentStateLockRetryDelay     = 25 * time.Millisecond
)

type EnrollmentStatePaths struct {
	Root       string
	StatePath  string
	LockPath   string
	sealedRoot string
}

type EnrollmentStateLock struct {
	closeFn   func() error
	closeOnce sync.Once
	closeErr  error
	Path      string
}

func (lock *EnrollmentStateLock) Close() error {
	if lock == nil || lock.closeFn == nil {
		return nil
	}
	lock.closeOnce.Do(func() {
		lock.closeErr = lock.closeFn()
	})
	return lock.closeErr
}
