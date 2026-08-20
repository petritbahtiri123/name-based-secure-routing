//go:build windows
// +build windows

package authority

import (
	"errors"
	"io"
	"os"
	"path/filepath"
	"unsafe"

	"golang.org/x/sys/windows"
)

type enrollmentStateWriteStage string

const (
	enrollmentStateWriteAfterClose enrollmentStateWriteStage = "after-close-before-move"
	enrollmentStateWriteAfterMove  enrollmentStateWriteStage = "after-move-before-validation"
)

var enrollmentStateWriteStageHook = func(string, enrollmentStateWriteStage) {}

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
	if err := validateOwnershipAndACL(parent); err != nil {
		return err
	}

	tempPath := path + ".tmp"
	temp, err := os.OpenFile(tempPath, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o600)
	if err != nil {
		return err
	}
	defer func() {
		_ = os.Remove(tempPath)
	}()
	if err := applyDirectorySecurityToPath(tempPath, parent); err != nil {
		_ = temp.Close()
		return err
	}
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
	enrollmentStateWriteStageHook(path, enrollmentStateWriteAfterClose)
	moveFlags := uint32(windows.MOVEFILE_WRITE_THROUGH)
	if err := windows.MoveFileEx(
		fileNameWide(tempPath),
		fileNameWide(path),
		moveFlags,
	); err != nil {
		return err
	}
	enrollmentStateWriteStageHook(path, enrollmentStateWriteAfterMove)
	return validateOwnershipAndACL(path)
}

func readEnrollmentStateBlob(path string) ([]byte, bool, error) {
	pathPtr, err := pathW(path)
	if err != nil {
		return nil, false, withAuthorityError(err, ErrStoragePathRejected, path)
	}
	handle, err := windows.CreateFile(
		pathPtr,
		windows.GENERIC_READ,
		windows.FILE_SHARE_READ,
		nil,
		windows.OPEN_EXISTING,
		windows.FILE_ATTRIBUTE_NORMAL|windows.FILE_FLAG_OPEN_REPARSE_POINT,
		0,
	)
	if err != nil {
		if errors.Is(err, windows.ERROR_FILE_NOT_FOUND) || errors.Is(err, windows.ERROR_PATH_NOT_FOUND) {
			return nil, false, nil
		}
		return nil, false, withAuthorityError(err, ErrStoragePathRejected, path)
	}
	file := os.NewFile(uintptr(handle), path)
	if file == nil {
		_ = windows.Close(handle)
		return nil, false, ErrStoragePathRejected
	}
	defer file.Close()
	if err := validateRegularNonReparseHandle(handle, path); err != nil {
		return nil, false, err
	}
	if err := validateOwnershipAndACL(path); err != nil {
		return nil, false, err
	}
	var info windows.ByHandleFileInformation
	if err := windows.GetFileInformationByHandle(handle, &info); err != nil {
		return nil, false, withAuthorityError(err, ErrStoragePathRejected, path)
	}
	size := uint64(info.FileSizeHigh)<<32 | uint64(info.FileSizeLow)
	if size == 0 || size > maxEnrollmentStateBytes {
		return nil, false, ErrInvalidAuthority
	}
	raw, err := io.ReadAll(io.LimitReader(file, maxEnrollmentStateBytes+1))
	if err != nil {
		return nil, false, withAuthorityError(err, ErrStoragePathRejected, path)
	}
	if len(raw) == 0 || len(raw) > maxEnrollmentStateBytes {
		return nil, false, ErrInvalidAuthority
	}
	return raw, true, nil
}

func cleanupEnrollmentStateTemps(root string) error {
	for _, candidate := range []string{
		filepath.Join(root, enrollmentStateFileName) + ".tmp",
		filepath.Join(root, enrollmentStateIntegrityKeyName) + ".tmp",
	} {
		if validationErr := validateNoReparseFinalPath(root, candidate); validationErr != nil {
			return validationErr
		}
		if securityErr := validateSecurityIfPresent(candidate); securityErr != nil {
			return securityErr
		}
		if removeErr := os.Remove(candidate); removeErr != nil && !errors.Is(removeErr, os.ErrNotExist) {
			return withAuthorityError(removeErr, ErrStoragePathRejected, candidate)
		}
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
