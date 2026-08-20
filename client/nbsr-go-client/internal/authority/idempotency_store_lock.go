package authority

import "sync"

type idempotencyFileLock struct {
	closeFn   func() error
	closeOnce sync.Once
	closeErr  error
}

func (lock *idempotencyFileLock) Close() error {
	if lock == nil || lock.closeFn == nil {
		return nil
	}
	lock.closeOnce.Do(func() { lock.closeErr = lock.closeFn() })
	return lock.closeErr
}
