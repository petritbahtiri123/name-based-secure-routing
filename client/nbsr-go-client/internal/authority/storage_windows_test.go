//go:build windows
// +build windows

package authority

import (
	"bytes"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"
)

const (
	storageLockHelperEnv      = "NBSR_STORAGE_LOCK_HELPER"
	storageLockRootEnv        = "NBSR_STORAGE_LOCK_ROOT"
	storageLockHoldMSEnv      = "NBSR_STORAGE_LOCK_HOLD_MS"
	storageLockEnteredFileEnv = "NBSR_STORAGE_LOCK_ENTERED"
	lockBusyExitCode          = 3
	lockErrorExitCode         = 4
)

func TestEnrollmentStatePathResolutionCanonicalNames(t *testing.T) {
	root := tempEnrollmentRoot(t)
	paths, err := ResolveEnrollmentStatePathsForTest(root)
	if err != nil {
		t.Fatalf("ResolveEnrollmentStatePathsForTest: %v", err)
	}
	if paths.Root != root {
		t.Fatalf("unexpected root: got=%s want=%s", paths.Root, root)
	}
	if filepath.Base(paths.StatePath) != enrollmentStateFileName {
		t.Fatalf("unexpected state path: %s", paths.StatePath)
	}
	if filepath.Base(paths.LockPath) != enrollmentStateLockFileName {
		t.Fatalf("unexpected lock path: %s", paths.LockPath)
	}
}

func TestEnrollmentStatePathResolutionRejectsRelativeRoot(t *testing.T) {
	_, err := ResolveEnrollmentStatePathsForTest(`.\nbsr-local`)
	if !errors.Is(err, ErrStoragePathRejected) {
		t.Fatalf("errors.Is(%v, ErrStoragePathRejected) = false", err)
	}
}

func TestEnrollmentStatePathResolutionRejectsUNC(t *testing.T) {
	_, err := ResolveEnrollmentStatePathsForTest(`\\127.0.0.1\share\NBSR\GoClient\Enrollment`)
	if !errors.Is(err, ErrStoragePathRejected) {
		t.Fatalf("errors.Is(%v, ErrStoragePathRejected) = false", err)
	}
}

func TestEnrollmentStatePathResolutionRejectsReparseParent(t *testing.T) {
	target := tempDir(t)
	junction := filepath.Join(target, "link-root")
	reifyDir(t, target)
	reifyDir(t, filepath.Join(target, "target"))

	err := makeDirectoryJunction(t, junction, filepath.Join(target, "target"))
	if err != nil {
		t.Skipf("cannot create test junction: %v", err)
	}
	_, err = ResolveEnrollmentStatePathsForTest(filepath.Join(junction, enrollmentStateDirectorySuffix))
	if !errors.Is(err, ErrStoragePathRejected) {
		t.Fatalf("errors.Is(%v, ErrStoragePathRejected) = false", err)
	}
}

func TestEnrollmentStatePathResolutionRejectsReparseLockTarget(t *testing.T) {
	root := tempEnrollmentRoot(t)
	paths, err := ResolveEnrollmentStatePathsForTest(root)
	if err != nil {
		t.Fatalf("ResolveEnrollmentStatePathsForTest: %v", err)
	}

	realLockTarget := filepath.Join(root, "real-lock-target.bin")
	if err := os.WriteFile(realLockTarget, []byte("real"), 0o600); err != nil {
		t.Fatalf("WriteFile(real lock target): %v", err)
	}
	if err := makeFileSymlink(t, paths.LockPath, realLockTarget); err != nil {
		t.Skipf("cannot create test file symlink: %v", err)
	}
	_, err = ResolveEnrollmentStatePathsForTest(root)
	if !errors.Is(err, ErrStoragePathRejected) {
		t.Fatalf("errors.Is(%v, ErrStoragePathRejected) = false", err)
	}
}

func TestEnrollmentStatePathResolutionRejectsNonDirectoryComponent(t *testing.T) {
	base := tempDir(t)
	fileParent := filepath.Join(base, "NBSR")
	if err := os.WriteFile(fileParent, []byte("no-dir"), 0o600); err != nil {
		t.Fatalf("WriteFile(file parent): %v", err)
	}
	_, err := ResolveEnrollmentStatePathsForTest(filepath.Join(fileParent, "GoClient", "Enrollment"))
	if !errors.Is(err, ErrStoragePathRejected) {
		t.Fatalf("errors.Is(%v, ErrStoragePathRejected) = false", err)
	}
}

func TestEnrollmentStatePathResolutionRejectsBroadWritableACL(t *testing.T) {
	root := tempEnrollmentRoot(t)
	if err := grantEveryoneFullAccess(t, root); err != nil {
		t.Skipf("cannot modify ACL for test fixture: %v", err)
	}
	_, err := ResolveEnrollmentStatePathsForTest(root)
	if !errors.Is(err, ErrStoragePathRejected) {
		t.Fatalf("errors.Is(%v, ErrStoragePathRejected) = false", err)
	}
}

func TestEnrollmentStatePathResolutionRejectsWrongOwnerContext(t *testing.T) {
	root := tempEnrollmentRoot(t)
	prev := getCurrentProcessSID
	defer func() { getCurrentProcessSID = prev }()
	getCurrentProcessSID = func() (string, error) {
		return "S-1-5-21-0-0-0-0", nil
	}
	_, err := ResolveEnrollmentStatePathsForTest(root)
	if !errors.Is(err, ErrStoragePathRejected) {
		t.Fatalf("errors.Is(%v, ErrStoragePathRejected) = false", err)
	}
}

func TestEnrollmentStatePathResolutionRejectsArbitraryFinalPath(t *testing.T) {
	root := tempEnrollmentRoot(t)
	paths, err := ResolveEnrollmentStatePathsForTest(root)
	if err != nil {
		t.Fatalf("ResolveEnrollmentStatePathsForTest: %v", err)
	}
	if filepath.Base(paths.StatePath) != enrollmentStateFileName {
		t.Fatalf("production API exposed writable final state filename: %s", paths.StatePath)
	}
	if filepath.Base(paths.LockPath) != enrollmentStateLockFileName {
		t.Fatalf("production API exposed writable lock filename: %s", paths.LockPath)
	}
}

func TestEnrollmentStateLockIsAcquiredBySingleProcess(t *testing.T) {
	root := tempEnrollmentRoot(t)
	paths, err := ResolveEnrollmentStatePathsForTest(root)
	if err != nil {
		t.Fatalf("ResolveEnrollmentStatePathsForTest: %v", err)
	}
	lock, err := AcquireEnrollmentStateLock(paths)
	if err != nil {
		t.Fatalf("AcquireEnrollmentStateLock: %v", err)
	}
	if err := lock.Close(); err != nil {
		t.Fatalf("lock.Close: %v", err)
	}
}

func TestEnrollmentStateLockFailsOnSecondProcess(t *testing.T) {
	root := tempEnrollmentRoot(t)
	firstMarker := filepath.Join(tempDir(t), "first-acquired")
	first := startStorageLockHelper(t, root, 10*time.Second, firstMarker)
	if err := first.Start(); err != nil {
		t.Fatalf("start first helper: %v", err)
	}
	if !waitForMarker(firstMarker, 5*time.Second) {
		t.Fatalf("first helper never acquired lock")
	}

	contenderMarker := filepath.Join(tempDir(t), "contender-acquired")
	second := startStorageLockHelper(t, root, 0, contenderMarker)
	exitCode, stdout, stderr, err := runStorageLockHelper(t, second)
	if err == nil {
		t.Fatalf("second helper unexpectedly succeeded with lock")
	}
	if !strings.Contains(stdout+stderr, "BUSY") {
		t.Fatalf("second helper result: code=%d stdout=%q stderr=%q", exitCode, stdout, stderr)
	}
	if exitCode != lockBusyExitCode {
		t.Fatalf("second helper exit code: got=%d want=%d", exitCode, lockBusyExitCode)
	}
	if _, err := os.Stat(contenderMarker); !os.IsNotExist(err) {
		t.Fatalf("second helper wrote entered marker despite failed acquisition")
	}

	if err := first.Process.Kill(); err != nil {
		t.Fatalf("kill first helper: %v", err)
	}
	_ = first.Wait()
}

func TestEnrollmentStateLockReleasedOnExitThenAcquirableByAnotherProcess(t *testing.T) {
	root := tempEnrollmentRoot(t)
	firstMarker := filepath.Join(tempDir(t), "first-acquired")
	first := startStorageLockHelper(t, root, 12*time.Second, firstMarker)
	if err := first.Start(); err != nil {
		t.Fatalf("start first helper: %v", err)
	}
	if !waitForMarker(firstMarker, 5*time.Second) {
		t.Fatalf("first helper never acquired lock")
	}

	contenderMarker := filepath.Join(tempDir(t), "contender-denied")
	denied := startStorageLockHelper(t, root, 0, contenderMarker)
	exitCode, stdout, stderr, err := runStorageLockHelper(t, denied)
	if err == nil || exitCode != lockBusyExitCode {
		t.Fatalf("expected first contender busy; got err=%v code=%d stdout=%q stderr=%q", err, exitCode, stdout, stderr)
	}

	if err := first.Process.Kill(); err != nil {
		t.Fatalf("kill first helper: %v", err)
	}
	_ = first.Wait()

	acquiredMarker := filepath.Join(tempDir(t), "contender-acquired")
	after := startStorageLockHelper(t, root, 0, acquiredMarker)
	code, _, _, err := runStorageLockHelper(t, after)
	if err != nil {
		t.Fatalf("third helper failed after release: code=%d err=%v", code, err)
	}
	if !waitForMarker(acquiredMarker, 3*time.Second) {
		t.Fatalf("third helper did not acquire lock after release")
	}
}

func TestStorageLockHelper(t *testing.T) {
	if os.Getenv(storageLockHelperEnv) != "1" {
		return
	}
	hold := 0
	if raw := os.Getenv(storageLockHoldMSEnv); raw != "" {
		if value, err := strconv.Atoi(raw); err == nil {
			hold = value
		}
	}
	root := os.Getenv(storageLockRootEnv)
	paths, err := ResolveEnrollmentStatePathsForTest(root)
	if err != nil {
		os.Exit(lockErrorExitCode)
	}
	lock, err := AcquireEnrollmentStateLock(paths)
	if err != nil {
		if errors.Is(err, ErrStorageBusy) {
			fmt.Println("BUSY")
			os.Exit(lockBusyExitCode)
		}
		os.Exit(lockErrorExitCode)
	}
	defer func() {
		_ = lock.Close()
	}()
	if marker := os.Getenv(storageLockEnteredFileEnv); marker != "" {
		_ = os.WriteFile(marker, []byte("acquired"), 0o600)
	}
	if hold > 0 {
		time.Sleep(time.Duration(hold) * time.Millisecond)
	}
}

func tempDir(t *testing.T) string {
	t.Helper()
	return t.TempDir()
}

func tempEnrollmentRoot(t *testing.T) string {
	t.Helper()
	root := filepath.Join(tempDir(t), enrollmentStateDirectorySuffix)
	if err := os.MkdirAll(root, 0o700); err != nil {
		t.Fatalf("MkdirAll(%s): %v", root, err)
	}
	return root
}

func reifyDir(t *testing.T, path string) string {
	t.Helper()
	if err := os.MkdirAll(path, 0o700); err != nil {
		t.Fatalf("MkdirAll(%s): %v", path, err)
	}
	return path
}

func makeDirectoryJunction(t *testing.T, link, target string) error {
	t.Helper()
	cmd := exec.Command("cmd", "/C", fmt.Sprintf("mklink /J %q %q", link, target))
	output, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("%w: %s", err, strings.TrimSpace(string(output)))
	}
	return nil
}

func makeFileSymlink(t *testing.T, link, target string) error {
	t.Helper()
	cmd := exec.Command("cmd", "/C", fmt.Sprintf("mklink %q %q", link, target))
	output, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("%w: %s", err, strings.TrimSpace(string(output)))
	}
	return nil
}

func grantEveryoneFullAccess(t *testing.T, path string) error {
	t.Helper()
	cmd := exec.Command("icacls", path, "/grant", "*S-1-1-0:(OI)(CI)F")
	output, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("%w: %s", err, strings.TrimSpace(string(output)))
	}
	return nil
}

func startStorageLockHelper(t *testing.T, root string, hold time.Duration, enteredPath string) *exec.Cmd {
	t.Helper()
	exe, err := os.Executable()
	if err != nil {
		t.Fatalf("os.Executable: %v", err)
	}
	args := []string{"-test.run=^TestStorageLockHelper$", "-test.v=false"}
	cmd := exec.Command(exe, args...)
	cmd.Env = append(os.Environ(),
		storageLockHelperEnv+"=1",
		storageLockRootEnv+"="+root,
		storageLockHoldMSEnv+"="+strconv.Itoa(int(hold/time.Millisecond)),
	)
	if enteredPath != "" {
		cmd.Env = append(cmd.Env, storageLockEnteredFileEnv+"="+enteredPath)
	}
	return cmd
}

func runStorageLockHelper(t *testing.T, cmd *exec.Cmd) (int, string, string, error) {
	t.Helper()
	var stdout bytes.Buffer
	var stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	err := cmd.Run()
	if err == nil {
		return 0, stdout.String(), stderr.String(), nil
	}
	exitCode := -1
	if exitErr, ok := err.(*exec.ExitError); ok {
		exitCode = exitErr.ExitCode()
	}
	return exitCode, stdout.String(), stderr.String(), err
}

func waitForMarker(path string, timeout time.Duration) bool {
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		if _, err := os.Stat(path); err == nil {
			return true
		}
		time.Sleep(25 * time.Millisecond)
	}
	return false
}
