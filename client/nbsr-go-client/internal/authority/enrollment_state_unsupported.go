//go:build !windows
// +build !windows

package authority

func writeEnrollmentStateAtomically(path string, payload []byte) error {
	return ErrStorageUnsupported
}

func replaceEnrollmentStateAtomically(path string, payload []byte) error {
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

func readEnrollmentStateBlob(string) ([]byte, bool, error) {
	return nil, false, ErrStorageUnsupported
}

func cleanupEnrollmentStateTemps(string) error {
	return ErrStorageUnsupported
}
