//go:build windows
// +build windows

package authority

import (
	"errors"
	"fmt"
	"path/filepath"
	"strings"
	"sync"
	"time"
	"unsafe"

	"golang.org/x/sys/windows"
)

const (
	broadDirectoryWriteMask = uint32(
		windows.FILE_GENERIC_WRITE |
			windows.DELETE |
			windows.WRITE_DAC |
			windows.WRITE_OWNER |
			windows.GENERIC_ALL |
			windows.MAXIMUM_ALLOWED,
	)
)

var (
	systemSIDString     string
	systemSIDStringOnce sync.Once
	systemSIDStringErr  error
)

var (
	broadPrincipalSIDStrings     map[string]struct{}
	broadPrincipalSIDStringsOnce sync.Once
	broadPrincipalSIDStringsErr  error
)

var getCurrentProcessSID = func() (string, error) {
	user, err := windows.GetCurrentProcessToken().GetTokenUser()
	if err != nil {
		return "", err
	}
	if user == nil || user.User.Sid == nil {
		return "", fmt.Errorf("missing token user SID")
	}
	return user.User.Sid.String(), nil
}

func ResolveEnrollmentStatePaths() (EnrollmentStatePaths, error) {
	programData, err := windows.KnownFolderPath(windows.FOLDERID_ProgramData, 0)
	if err != nil {
		return EnrollmentStatePaths{}, withAuthorityError(err, ErrStoragePathRejected, "known folder")
	}
	return resolveEnrollmentStatePaths(filepath.Join(programData, enrollmentStateDirectorySuffix), true)
}

func ResolveEnrollmentStatePathsForTest(root string) (EnrollmentStatePaths, error) {
	return resolveEnrollmentStatePaths(root, false)
}

func AcquireEnrollmentStateLock(paths EnrollmentStatePaths) (*EnrollmentStateLock, error) {
	if err := validateEnrollmentStatePaths(paths); err != nil {
		return nil, err
	}
	lockPathW, err := pathW(paths.LockPath)
	if err != nil {
		return nil, withAuthorityError(err, ErrStoragePathRejected, paths.LockPath)
	}
	handle, err := windows.CreateFile(
		lockPathW,
		windows.GENERIC_READ|windows.GENERIC_WRITE,
		windows.FILE_SHARE_READ|windows.FILE_SHARE_WRITE|windows.FILE_SHARE_DELETE,
		nil,
		windows.OPEN_ALWAYS,
		windows.FILE_ATTRIBUTE_NORMAL|windows.FILE_FLAG_OPEN_REPARSE_POINT,
		0,
	)
	if err != nil {
		if errors.Is(err, windows.ERROR_LOCK_VIOLATION) {
			return nil, withAuthorityError(err, ErrStorageBusy, paths.LockPath)
		}
		return nil, withAuthorityError(err, ErrStoragePathRejected, paths.LockPath)
	}
	if err := lockHandle(handle); err != nil {
		_ = windows.Close(handle)
		return nil, err
	}
	return &EnrollmentStateLock{
		Path: paths.LockPath,
		closeFn: func() error {
			defer windows.Close(handle)
			ov := windows.Overlapped{}
			if err := windows.UnlockFileEx(handle, 0, 1, 0, &ov); err != nil {
				return withAuthorityError(err, ErrStoragePathRejected, paths.LockPath)
			}
			return nil
		},
	}, nil
}

func resolveEnrollmentStatePaths(root string, requireProductionPath bool) (EnrollmentStatePaths, error) {
	root = filepath.Clean(root)
	if root == "" {
		return EnrollmentStatePaths{}, withAuthorityError(nil, ErrStoragePathRejected, "empty enrollment root")
	}
	if !filepath.IsAbs(root) {
		return EnrollmentStatePaths{}, withAuthorityError(nil, ErrStoragePathRejected, root)
	}
	if strings.HasPrefix(root, `\\`) || strings.HasPrefix(root, `\\?\`) {
		return EnrollmentStatePaths{}, withAuthorityError(nil, ErrStoragePathRejected, "UNC or extended path")
	}
	if isNetworkDrive(root) {
		return EnrollmentStatePaths{}, withAuthorityError(nil, ErrStoragePathRejected, "network path")
	}

	if requireProductionPath {
		programData, err := windows.KnownFolderPath(windows.FOLDERID_ProgramData, 0)
		if err != nil {
			return EnrollmentStatePaths{}, withAuthorityError(err, ErrStoragePathRejected, "known folder")
		}
		expected := filepath.Clean(filepath.Join(programData, enrollmentStateDirectorySuffix))
		if !strings.EqualFold(root, expected) {
			return EnrollmentStatePaths{}, withAuthorityError(nil, ErrStoragePathRejected, "unexpected production root")
		}
	}

	if err := validateExistingDirectoryChain(root); err != nil {
		return EnrollmentStatePaths{}, err
	}
	if err := validateNoReparseFinalPath(root, filepath.Join(root, enrollmentStateFileName)); err != nil {
		return EnrollmentStatePaths{}, err
	}
	if err := validateNoReparseFinalPath(root, filepath.Join(root, enrollmentStateLockFileName)); err != nil {
		return EnrollmentStatePaths{}, err
	}
	if err := validateOwnershipAndACL(root); err != nil {
		return EnrollmentStatePaths{}, err
	}

	return EnrollmentStatePaths{
		Root:      root,
		StatePath: filepath.Join(root, enrollmentStateFileName),
		LockPath:  filepath.Join(root, enrollmentStateLockFileName),
	}, nil
}

func validateEnrollmentStatePaths(paths EnrollmentStatePaths) error {
	resolved, err := resolveEnrollmentStatePaths(paths.Root, false)
	if err != nil {
		return err
	}
	if !strings.EqualFold(filepath.Clean(paths.Root), filepath.Clean(resolved.Root)) {
		return withAuthorityError(nil, ErrStoragePathRejected, "root mismatch")
	}
	if !strings.EqualFold(filepath.Clean(filepath.Dir(paths.StatePath)), filepath.Clean(resolved.Root)) ||
		!strings.EqualFold(filepath.Base(paths.StatePath), enrollmentStateFileName) {
		return withAuthorityError(nil, ErrStoragePathRejected, "invalid state file path")
	}
	if !strings.EqualFold(filepath.Clean(filepath.Dir(paths.LockPath)), filepath.Clean(resolved.Root)) ||
		!strings.EqualFold(filepath.Base(paths.LockPath), enrollmentStateLockFileName) {
		return withAuthorityError(nil, ErrStoragePathRejected, "invalid lock file path")
	}
	return nil
}

func validateExistingDirectoryChain(root string) error {
	volume := filepath.VolumeName(root)
	if volume == "" {
		return withAuthorityError(nil, ErrStoragePathRejected, root)
	}
	remainder := strings.TrimPrefix(root, volume)
	remainder = strings.TrimPrefix(remainder, `\`)
	remainder = strings.TrimPrefix(remainder, `/`)

	current := volume
	if !strings.HasSuffix(current, `\`) && !strings.HasSuffix(current, `/`) {
		current += `\`
	}
	if current == "" {
		return withAuthorityError(nil, ErrStoragePathRejected, root)
	}
	if err := validateNoReparseDirectory(current); err != nil {
		return err
	}
	if strings.TrimSpace(remainder) != "" {
		for _, part := range strings.FieldsFunc(remainder, func(r rune) bool {
			return r == '/' || r == '\\'
		}) {
			current = filepath.Join(current, part)
			if err := validateNoReparseDirectory(current); err != nil {
				return err
			}
		}
	}
	return nil
}

func validateNoReparseDirectory(path string) error {
	info, err := queryPathAttributes(path, true)
	if err != nil {
		return withAuthorityError(err, ErrStoragePathRejected, path)
	}
	if info.FileAttributes&windows.FILE_ATTRIBUTE_REPARSE_POINT != 0 {
		return withAuthorityError(nil, ErrStoragePathRejected, "reparse directory: "+path)
	}
	if info.FileAttributes&windows.FILE_ATTRIBUTE_DIRECTORY == 0 {
		return withAuthorityError(nil, ErrStoragePathRejected, "non-directory component: "+path)
	}
	return nil
}

func validateNoReparseFinalPath(_ string, candidate string) error {
	info, err := queryPathAttributes(candidate, false)
	if err != nil {
		if errors.Is(err, windows.ERROR_FILE_NOT_FOUND) || errors.Is(err, windows.ERROR_PATH_NOT_FOUND) {
			return nil
		}
		return withAuthorityError(err, ErrStoragePathRejected, candidate)
	}
	if info.FileAttributes&windows.FILE_ATTRIBUTE_REPARSE_POINT != 0 {
		return withAuthorityError(nil, ErrStoragePathRejected, "reparse target: "+candidate)
	}
	if info.FileAttributes&windows.FILE_ATTRIBUTE_DIRECTORY != 0 {
		return withAuthorityError(nil, ErrStoragePathRejected, "non-file target: "+candidate)
	}
	return nil
}

func validateOwnershipAndACL(root string) error {
	sd, err := windows.GetNamedSecurityInfo(root, windows.SE_FILE_OBJECT, windows.OWNER_SECURITY_INFORMATION|windows.DACL_SECURITY_INFORMATION)
	if err != nil {
		return withAuthorityError(err, ErrStoragePathRejected, root)
	}

	owner, _, err := sd.Owner()
	if err != nil || owner == nil {
		return withAuthorityError(err, ErrStoragePathRejected, root)
	}
	processSid, err := getCurrentProcessSID()
	if err != nil {
		return withAuthorityError(err, ErrStoragePathRejected, "current process identity")
	}
	systemSid, err := localSystemSID()
	if err != nil {
		return withAuthorityError(err, ErrStoragePathRejected, "system SID")
	}
	if ownerStr := owner.String(); ownerStr != processSid && ownerStr != systemSid {
		return withAuthorityError(nil, ErrStoragePathRejected, "owner mismatch")
	}

	dacl, _, err := sd.DACL()
	if err != nil {
		return withAuthorityError(err, ErrStoragePathRejected, root)
	}
	if dacl == nil {
		return withAuthorityError(nil, ErrStoragePathRejected, "missing DACL")
	}

	broadSids, err := broadPrincipalSIDs()
	if err != nil {
		return withAuthorityError(err, ErrStoragePathRejected, "broad principal SID set")
	}
	for i := uint16(0); i < dacl.AceCount; i++ {
		var ace *windows.ACCESS_ALLOWED_ACE
		if err := windows.GetAce(dacl, uint32(i), &ace); err != nil {
			return withAuthorityError(err, ErrStoragePathRejected, "ACL parse")
		}
		if ace == nil {
			continue
		}
		if ace.Header.AceType != windows.ACCESS_ALLOWED_ACE_TYPE {
			continue
		}
		entrySID := (*windows.SID)(unsafe.Pointer(&ace.SidStart))
		if entrySID == nil {
			continue
		}
		if _, ok := broadSids[entrySID.String()]; !ok {
			continue
		}
		if uint32(ace.Mask)&broadDirectoryWriteMask != 0 {
			return withAuthorityError(nil, ErrStoragePathRejected, "broad write ACE")
		}
	}

	return nil
}

func lockHandle(handle windows.Handle) error {
	deadline := time.Now().Add(enrollmentStateLockAcquireTimeout)
	overlapped := windows.Overlapped{}
	for {
		err := windows.LockFileEx(
			handle,
			windows.LOCKFILE_EXCLUSIVE_LOCK|windows.LOCKFILE_FAIL_IMMEDIATELY,
			0,
			1,
			0,
			&overlapped,
		)
		if err == nil {
			return nil
		}
		if isRetryableLockFailure(err) && time.Now().Before(deadline) {
			time.Sleep(enrollmentStateLockRetryDelay)
			continue
		}
		if isRetryableLockFailure(err) {
			return withAuthorityError(err, ErrStorageBusy, "enrollment-state.lock")
		}
		return withAuthorityError(err, ErrStoragePathRejected, "enrollment-state.lock")
	}
}

func isRetryableLockFailure(err error) bool {
	return errors.Is(err, windows.ERROR_LOCK_VIOLATION) || errors.Is(err, windows.ERROR_SHARING_VIOLATION)
}

func isNetworkDrive(path string) bool {
	volume := filepath.VolumeName(path)
	if strings.HasPrefix(volume, `\\`) {
		return true
	}
	volume = strings.TrimSuffix(volume, `\`)
	if len(volume) == 2 && volume[1] == ':' {
		volRoot := volume + `\`
		volRootW, err := pathW(volRoot)
		if err != nil {
			return false
		}
		return windows.GetDriveType(volRootW) == windows.DRIVE_REMOTE
	}
	return false
}

func queryPathAttributes(path string, asDirectory bool) (*windows.ByHandleFileInformation, error) {
	access := uint32(windows.GENERIC_READ)
	flags := uint32(windows.FILE_FLAG_OPEN_REPARSE_POINT)
	if asDirectory {
		access |= windows.FILE_LIST_DIRECTORY
		flags |= windows.FILE_FLAG_BACKUP_SEMANTICS
	}
	pathW, err := pathW(path)
	if err != nil {
		return nil, err
	}
	h, err := windows.CreateFile(
		pathW,
		access,
		windows.FILE_SHARE_READ|windows.FILE_SHARE_WRITE|windows.FILE_SHARE_DELETE,
		nil,
		windows.OPEN_EXISTING,
		flags,
		0,
	)
	if err != nil {
		return nil, err
	}
	defer windows.Close(h)

	var info windows.ByHandleFileInformation
	if err := windows.GetFileInformationByHandle(h, &info); err != nil {
		return nil, err
	}
	return &info, nil
}

func localSystemSID() (string, error) {
	systemSIDStringOnce.Do(func() {
		var sid *windows.SID
		sid, systemSIDStringErr = windows.StringToSid("S-1-5-18")
		if systemSIDStringErr != nil {
			return
		}
		systemSIDString = sid.String()
	})
	return systemSIDString, systemSIDStringErr
}

func broadPrincipalSIDs() (map[string]struct{}, error) {
	broadPrincipalSIDStringsOnce.Do(func() {
		broadPrincipalSIDStrings = map[string]struct{}{}
		for _, sidType := range []windows.WELL_KNOWN_SID_TYPE{
			windows.WinWorldSid,
			windows.WinBuiltinUsersSid,
			windows.WinAuthenticatedUserSid,
		} {
			sid, err := windows.CreateWellKnownSid(sidType)
			if err != nil {
				broadPrincipalSIDStringsErr = err
				return
			}
			broadPrincipalSIDStrings[sid.String()] = struct{}{}
		}
	})
	return broadPrincipalSIDStrings, broadPrincipalSIDStringsErr
}

func withAuthorityError(cause error, kind *AuthorityError, resource string) error {
	copied := *kind
	copied.Resource = resource
	if cause == nil {
		return &copied
	}
	return fmt.Errorf("%w: %w", &copied, cause)
}

func pathW(path string) (*uint16, error) {
	return windows.UTF16PtrFromString(path)
}
