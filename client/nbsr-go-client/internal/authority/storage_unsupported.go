//go:build !windows
// +build !windows

package authority

func ResolveEnrollmentStatePaths() (EnrollmentStatePaths, error) {
	return EnrollmentStatePaths{}, ErrStorageUnsupported
}

func ResolveEnrollmentStatePathsForTest(root string) (EnrollmentStatePaths, error) {
	return EnrollmentStatePaths{}, ErrStorageUnsupported
}

func AcquireEnrollmentStateLock(_ EnrollmentStatePaths) (*EnrollmentStateLock, error) {
	return nil, ErrStorageUnsupported
}
