//go:build !windows
// +build !windows

package authority

func writeEnrollmentStateAtomically(path string, payload []byte) error {
	return ErrStorageUnsupported
}

func writeEnrollmentStateIntegrityBlobAtomically(path string, blob []byte) error {
	return ErrStorageUnsupported
}

func protectEnrollmentStateIntegrityBlob(raw []byte) ([]byte, error) {
	return nil, ErrStorageUnsupported
}

func unprotectEnrollmentStateIntegrityBlob(raw []byte) ([]byte, error) {
	return nil, ErrStorageUnsupported
}
