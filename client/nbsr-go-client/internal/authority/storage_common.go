package authority

import "time"

const (
	enrollmentStateDirectorySuffix  = `NBSR\GoClient\Enrollment`
	enrollmentStateFileName         = "enrollment-state.bin"
	enrollmentStateLockFileName     = "enrollment-state.lock"
	enrollmentStateIntegrityKeyName = "enrollment-state.integrity-key"

	enrollmentStateLockAcquireTimeout = 2 * time.Second
	enrollmentStateLockRetryDelay     = 25 * time.Millisecond
)

type EnrollmentStatePaths struct {
	Root      string
	StatePath string
	LockPath  string
}

type EnrollmentStateLock struct {
	closeFn func() error
	Path    string
}

func (lock *EnrollmentStateLock) Close() error {
	if lock == nil || lock.closeFn == nil {
		return nil
	}
	return lock.closeFn()
}
