//go:build windows
// +build windows

package authority

import (
	"errors"
	"os"
	"path/filepath"
	"unsafe"

	"golang.org/x/sys/windows"
)

const moveFileFailIfExists uint32 = 0x00000001

var enrollmentStateInvalidPathError = errors.New("invalid enrollment state path")

func writeEnrollmentStateAtomically(path string, payload []byte) error {
	return writeBoundedBlobAtomically(path, payload)
}

func writeEnrollmentStateIntegrityBlobAtomically(path string, blob []byte) error {
	return writeBoundedBlobAtomically(path, blob)
}

func protectEnrollmentStateIntegrityBlob(raw []byte) ([]byte, error) {
	if len(raw) == 0 || len(raw) > maxEnrollmentStateBytes {
		return nil, ErrInvalidAuthority
	}
	inBlob := dataBlob(raw)
	var outBlob windows.DataBlob
	if err := windows.CryptProtectData(
		&inBlob,
		nil,
		nil,
		0,
		nil,
		windows.CRYPTPROTECT_UI_FORBIDDEN,
		&outBlob,
	); err != nil {
		return nil, err
	}
	defer windows.LocalFree(windows.Handle(uintptr(unsafe.Pointer(outBlob.Data))))
	if outBlob.Size == 0 {
		return nil, enrollmentStateInvalidPathError
	}
	protected, err := copyDataBlob(outBlob)
	if err != nil {
		return nil, err
	}
	if len(protected) > maxEnrollmentStateBytes {
		return nil, ErrInvalidAuthority
	}
	return protected, nil
}

func unprotectEnrollmentStateIntegrityBlob(raw []byte) ([]byte, error) {
	if len(raw) == 0 || len(raw) > maxEnrollmentStateBytes {
		return nil, ErrInvalidAuthority
	}
	inBlob := dataBlob(raw)
	var outBlob windows.DataBlob
	if err := windows.CryptUnprotectData(
		&inBlob,
		nil,
		nil,
		0,
		nil,
		windows.CRYPTPROTECT_UI_FORBIDDEN,
		&outBlob,
	); err != nil {
		return nil, err
	}
	defer windows.LocalFree(windows.Handle(uintptr(unsafe.Pointer(outBlob.Data))))
	if outBlob.Size == 0 {
		return nil, enrollmentStateInvalidPathError
	}
	return copyDataBlob(outBlob)
}

func writeBoundedBlobAtomically(path string, payload []byte) error {
	if path == "" || len(payload) == 0 || len(payload) > maxEnrollmentStateBytes {
		return ErrInvalidAuthority
	}
	parent := filepath.Dir(path)
	if err := os.MkdirAll(parent, 0o700); err != nil {
		return err
	}

	temp, err := os.CreateTemp(parent, "nbsr-enrollment-state-")
	if err != nil {
		return err
	}
	tempPath := temp.Name()
	defer func() {
		_ = os.Remove(tempPath)
	}()
	if _, err := temp.Write(payload); err != nil || len(payload) == 0 {
		_ = temp.Close()
		if err != nil {
			return err
		}
		return ErrInvalidAuthority
	}
	if err := temp.Sync(); err != nil {
		_ = temp.Close()
		return err
	}
	if err := windows.FlushFileBuffers(windows.Handle(temp.Fd())); err != nil {
		_ = temp.Close()
		return err
	}
	if err := temp.Close(); err != nil {
		return err
	}
	if err := applyDirectorySecurityToPath(tempPath, parent); err != nil {
		return err
	}
	moveFlags := windows.MOVEFILE_WRITE_THROUGH | moveFileFailIfExists
	if err := windows.MoveFileEx(
		fileNameWide(tempPath),
		fileNameWide(path),
		moveFlags,
	); err != nil {
		return err
	}
	return nil
}

func applyDirectorySecurityToPath(filePath, source string) error {
	sd, err := windows.GetNamedSecurityInfo(source, windows.SE_FILE_OBJECT, windows.OWNER_SECURITY_INFORMATION|windows.DACL_SECURITY_INFORMATION)
	if err != nil {
		return err
	}
	owner, _, err := sd.Owner()
	if err != nil {
		return err
	}
	dacl, _, err := sd.DACL()
	if err != nil {
		return err
	}
	return windows.SetNamedSecurityInfo(
		filePath,
		windows.SE_FILE_OBJECT,
		windows.OWNER_SECURITY_INFORMATION|windows.DACL_SECURITY_INFORMATION,
		owner,
		nil,
		dacl,
		nil,
	)
}

func dataBlob(payload []byte) windows.DataBlob {
	if len(payload) == 0 {
		return windows.DataBlob{}
	}
	return windows.DataBlob{
		Size: uint32(len(payload)),
		Data: &payload[0],
	}
}

func copyDataBlob(blob windows.DataBlob) ([]byte, error) {
	if blob.Size == 0 {
		return nil, nil
	}
	if blob.Data == nil {
		return nil, ErrInvalidAuthority
	}
	raw := unsafe.Slice(blob.Data, blob.Size)
	return append([]byte(nil), raw...), nil
}

func fileNameWide(path string) *uint16 {
	ptr, err := windows.UTF16PtrFromString(path)
	if err != nil {
		panic(err)
	}
	return ptr
}
