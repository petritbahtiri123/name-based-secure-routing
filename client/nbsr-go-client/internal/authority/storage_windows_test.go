//go:build windows
// +build windows

package authority

import (
	"bytes"
	"context"
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
	storageStoreHelperEnv     = "NBSR_STORAGE_STORE_HELPER"
	storageStoreCrashStageEnv = "NBSR_STORAGE_STORE_CRASH_STAGE"
	lockBusyExitCode          = 3
	lockErrorExitCode         = 4
	storeTerminalExitCode     = 5
	storeCrashExitCode        = 6
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
		t.Fatalf("cannot create test junction: %v", err)
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
		t.Fatalf("cannot create test file symlink: %v", err)
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

func TestFileEnrollmentStateStoreDoesNotProvisionMissingRoot(t *testing.T) {
	root := filepath.Join(t.TempDir(), enrollmentStateDirectorySuffix)
	if _, err := newFileEnrollmentStateStoreForTest(root); !errors.Is(err, ErrStoragePathRejected) {
		t.Fatalf("newFileEnrollmentStateStoreForTest missing root error = %v, want %v", err, ErrStoragePathRejected)
	}
	if _, err := os.Stat(root); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("missing trusted root was created at runtime: %v", err)
	}
}

func TestEnrollmentStatePathResolutionRejectsBroadWritableACL(t *testing.T) {
	root := tempEnrollmentRoot(t)
	if err := grantEveryoneFullAccess(t, root); err != nil {
		t.Fatalf("cannot modify ACL for test fixture: %v", err)
	}
	_, err := ResolveEnrollmentStatePathsForTest(root)
	if !errors.Is(err, ErrStoragePathRejected) {
		t.Fatalf("errors.Is(%v, ErrStoragePathRejected) = false", err)
	}
}

func TestEnrollmentStatePathResolutionRejectsUnapprovedWriterSID(t *testing.T) {
	root := tempEnrollmentRoot(t)
	if err := grantSIDFullAccess(t, root, "S-1-5-19", true); err != nil {
		t.Fatalf("cannot add Local Service ACL fixture: %v", err)
	}
	_, err := ResolveEnrollmentStatePathsForTest(root)
	if !errors.Is(err, ErrStoragePathRejected) {
		t.Fatalf("errors.Is(%v, ErrStoragePathRejected) = false", err)
	}
}

func TestEnrollmentStatePathResolutionRejectsBroadGenericWriteACL(t *testing.T) {
	root := tempEnrollmentRoot(t)
	if err := grantEveryoneGenericWrite(t, root); err != nil {
		t.Fatalf("cannot modify ACL for test fixture: %v", err)
	}
	_, err := ResolveEnrollmentStatePathsForTest(root)
	if !errors.Is(err, ErrStoragePathRejected) {
		t.Fatalf("errors.Is(%v, ErrStoragePathRejected) = false", err)
	}
}

func TestEnrollmentStatePathResolutionRejectsBroadWritableLockACL(t *testing.T) {
	root := tempEnrollmentRoot(t)
	paths, err := ResolveEnrollmentStatePathsForTest(root)
	if err != nil {
		t.Fatalf("ResolveEnrollmentStatePathsForTest: %v", err)
	}
	if err := os.WriteFile(paths.LockPath, nil, 0o600); err != nil {
		t.Fatalf("WriteFile(lock): %v", err)
	}
	if err := grantEveryoneFileFullAccess(t, paths.LockPath); err != nil {
		t.Fatalf("cannot modify lock ACL for test fixture: %v", err)
	}
	_, err = ResolveEnrollmentStatePathsForTest(root)
	if !errors.Is(err, ErrStoragePathRejected) {
		t.Fatalf("errors.Is(%v, ErrStoragePathRejected) = false", err)
	}
}

func TestFileEnrollmentStateStoreRejectsBroadWritableStateAndKeyACLs(t *testing.T) {
	for _, target := range []string{"state", "key"} {
		t.Run(target, func(t *testing.T) {
			store, statePath := newTestFileEnrollmentStateStore(t)
			request := validEnrollmentRequestPayload()
			requestPayload, err := EncodeEnrollmentRequestPayload(request)
			if err != nil {
				t.Fatalf("EncodeEnrollmentRequestPayload: %v", err)
			}
			result := validEnrollmentResultPayloadBoundToRequest(request, requestPayload, EnrollmentStatusAccepted)
			if err := store.Store(context.Background(), *result.DeviceIdentity); err != nil {
				t.Fatalf("Store: %v", err)
			}
			path := statePath
			if target == "key" {
				path = filepath.Join(filepath.Dir(statePath), enrollmentStateIntegrityKeyName)
			}
			if err := grantEveryoneFileFullAccess(t, path); err != nil {
				t.Fatalf("cannot modify %s ACL: %v", target, err)
			}
			if _, _, err := store.Load(context.Background()); !errors.Is(err, ErrStoragePathRejected) {
				t.Fatalf("Load with broad %s ACL error = %v, want %v", target, err, ErrStoragePathRejected)
			}
		})
	}
}

func TestWindowsAtomicEnrollmentInstallNeverReplacesExistingState(t *testing.T) {
	root := tempEnrollmentRoot(t)
	paths, err := ResolveEnrollmentStatePathsForTest(root)
	if err != nil {
		t.Fatalf("ResolveEnrollmentStatePathsForTest: %v", err)
	}
	original := []byte("original")
	if err := os.WriteFile(paths.StatePath, original, 0o600); err != nil {
		t.Fatalf("WriteFile(original): %v", err)
	}
	if err := writeEnrollmentStateAtomically(paths.StatePath, []byte("replacement")); err == nil {
		t.Fatal("atomic installation replaced an existing create-once state")
	}
	got, err := os.ReadFile(paths.StatePath)
	if err != nil {
		t.Fatalf("ReadFile(original): %v", err)
	}
	if !bytes.Equal(got, original) {
		t.Fatalf("existing state changed: got=%q want=%q", got, original)
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

func TestEnrollmentStatePathResolutionRejectsMissingSystemAccess(t *testing.T) {
	root := tempEnrollmentRoot(t)
	cmd := exec.Command("icacls", root, "/remove:g", "*S-1-5-18")
	output, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("cannot create missing-SYSTEM ACL fixture: %v: %s", err, strings.TrimSpace(string(output)))
	}
	_, err = ResolveEnrollmentStatePathsForTest(root)
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

func TestEnrollmentStateLockRejectsCallerConstructedPaths(t *testing.T) {
	root := tempEnrollmentRoot(t)
	paths := EnrollmentStatePaths{
		Root:      root,
		StatePath: filepath.Join(root, enrollmentStateFileName),
		LockPath:  filepath.Join(root, enrollmentStateLockFileName),
	}
	if _, err := AcquireEnrollmentStateLock(paths); !errors.Is(err, ErrStoragePathRejected) {
		t.Fatalf("AcquireEnrollmentStateLock with caller paths error = %v, want %v", err, ErrStoragePathRejected)
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

func TestEnrollmentStateLockPreventsLockPathReplacement(t *testing.T) {
	root := tempEnrollmentRoot(t)
	paths, err := ResolveEnrollmentStatePathsForTest(root)
	if err != nil {
		t.Fatalf("ResolveEnrollmentStatePathsForTest: %v", err)
	}
	lock, err := AcquireEnrollmentStateLock(paths)
	if err != nil {
		t.Fatalf("AcquireEnrollmentStateLock: %v", err)
	}
	defer func() { _ = lock.Close() }()
	if err := os.Remove(paths.LockPath); err == nil {
		t.Fatal("locked pathname was removable, allowing a replacement lock inode")
	}
}

func TestEnrollmentStateLockCloseIsIdempotent(t *testing.T) {
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
		t.Fatalf("first Close: %v", err)
	}
	if err := lock.Close(); err != nil {
		t.Fatalf("second Close: %v", err)
	}
}

func TestEnrollmentStateLockConcurrentCloseIsSafe(t *testing.T) {
	root := tempEnrollmentRoot(t)
	paths, err := ResolveEnrollmentStatePathsForTest(root)
	if err != nil {
		t.Fatalf("ResolveEnrollmentStatePathsForTest: %v", err)
	}
	lock, err := AcquireEnrollmentStateLock(paths)
	if err != nil {
		t.Fatalf("AcquireEnrollmentStateLock: %v", err)
	}
	errorsSeen := make(chan error, 8)
	for i := 0; i < cap(errorsSeen); i++ {
		go func() { errorsSeen <- lock.Close() }()
	}
	for i := 0; i < cap(errorsSeen); i++ {
		if err := <-errorsSeen; err != nil {
			t.Fatalf("concurrent Close: %v", err)
		}
	}
}

func TestFileEnrollmentStateStoreFailsBusyWhileCrossProcessLockIsHeld(t *testing.T) {
	root := tempEnrollmentRoot(t)
	paths, err := ResolveEnrollmentStatePathsForTest(root)
	if err != nil {
		t.Fatalf("ResolveEnrollmentStatePathsForTest: %v", err)
	}
	lock, err := AcquireEnrollmentStateLock(paths)
	if err != nil {
		t.Fatalf("AcquireEnrollmentStateLock: %v", err)
	}
	defer func() {
		if err := lock.Close(); err != nil {
			t.Errorf("lock.Close: %v", err)
		}
	}()

	store, err := newFileEnrollmentStateStoreForTest(root)
	if err != nil {
		t.Fatalf("newFileEnrollmentStateStoreForTest: %v", err)
	}
	request := validEnrollmentRequestPayload()
	requestPayload, err := EncodeEnrollmentRequestPayload(request)
	if err != nil {
		t.Fatalf("EncodeEnrollmentRequestPayload: %v", err)
	}
	result := validEnrollmentResultPayloadBoundToRequest(request, requestPayload, EnrollmentStatusAccepted)
	if err := store.Store(context.Background(), *result.DeviceIdentity); !errors.Is(err, ErrStorageBusy) {
		t.Fatalf("Store while OS lock held error = %v, want %v", err, ErrStorageBusy)
	}
	for _, path := range []string{paths.StatePath, filepath.Join(paths.Root, enrollmentStateIntegrityKeyName)} {
		if _, err := os.Stat(path); !errors.Is(err, os.ErrNotExist) {
			t.Fatalf("storage side effect while lock unavailable at %s: %v", path, err)
		}
	}
}

func TestFileEnrollmentStateStoreRealSubprocessBusyThenStoresAfterRelease(t *testing.T) {
	root := tempEnrollmentRoot(t)
	paths, err := ResolveEnrollmentStatePathsForTest(root)
	if err != nil {
		t.Fatalf("ResolveEnrollmentStatePathsForTest: %v", err)
	}
	lock, err := AcquireEnrollmentStateLock(paths)
	if err != nil {
		t.Fatalf("AcquireEnrollmentStateLock: %v", err)
	}

	blocked := startStateStoreHelper(t, root)
	exitCode, stdout, stderr, err := runStorageLockHelper(t, blocked)
	if err == nil || exitCode != lockBusyExitCode || !strings.Contains(stdout+stderr, "BUSY") {
		t.Fatalf("store helper contention: err=%v code=%d stdout=%q stderr=%q", err, exitCode, stdout, stderr)
	}
	if _, err := os.Stat(paths.StatePath); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("state exists after busy subprocess: %v", err)
	}
	if err := lock.Close(); err != nil {
		t.Fatalf("lock.Close: %v", err)
	}

	after := startStateStoreHelper(t, root)
	code, stdout, stderr, err := runStorageLockHelper(t, after)
	if err != nil || code != 0 || !strings.Contains(stdout+stderr, "STORED") {
		t.Fatalf("store helper after release: err=%v code=%d stdout=%q stderr=%q", err, code, stdout, stderr)
	}
	restarted, err := newFileEnrollmentStateStoreForTest(root)
	if err != nil {
		t.Fatalf("newFileEnrollmentStateStoreForTest(restart): %v", err)
	}
	if _, found, err := restarted.Load(context.Background()); err != nil || !found {
		t.Fatalf("restart Load: found=%v err=%v", found, err)
	}
}

func TestFileEnrollmentStateStoreTwoRealProcessFirstWritersHaveOneWinner(t *testing.T) {
	root := tempEnrollmentRoot(t)
	first := startStateStoreHelper(t, root)
	second := startStateStoreHelper(t, root)
	type helperResult struct {
		code           int
		stdout, stderr string
		err            error
	}
	resultsChannel := make(chan helperResult, 2)
	for _, command := range []*exec.Cmd{first, second} {
		command := command
		go func() {
			code, stdout, stderr, err := runStorageLockHelper(t, command)
			resultsChannel <- helperResult{code: code, stdout: stdout, stderr: stderr, err: err}
		}()
	}
	firstResult := <-resultsChannel
	secondResult := <-resultsChannel
	results := []struct {
		code   int
		output string
		err    error
	}{
		{firstResult.code, firstResult.stdout + firstResult.stderr, firstResult.err},
		{secondResult.code, secondResult.stdout + secondResult.stderr, secondResult.err},
	}
	winners := 0
	terminals := 0
	for _, result := range results {
		if result.err == nil && result.code == 0 && strings.Contains(result.output, "STORED") {
			winners++
		}
		if result.code == storeTerminalExitCode && strings.Contains(result.output, "TERMINAL") {
			terminals++
		}
	}
	if winners != 1 || terminals != 1 {
		t.Fatalf("writer results: first=(%d,%q,%v) second=(%d,%q,%v)", firstResult.code, firstResult.stdout+firstResult.stderr, firstResult.err, secondResult.code, secondResult.stdout+secondResult.stderr, secondResult.err)
	}
}

func TestFileEnrollmentStateStoreRealProcessCrashBoundaries(t *testing.T) {
	for _, test := range []struct {
		name          string
		stage         enrollmentStateWriteStage
		wantInstalled bool
	}{
		{name: "after flushed close before move", stage: enrollmentStateWriteAfterClose},
		{name: "after move before validation", stage: enrollmentStateWriteAfterMove, wantInstalled: true},
	} {
		t.Run(test.name, func(t *testing.T) {
			root := tempEnrollmentRoot(t)
			paths, err := ResolveEnrollmentStatePathsForTest(root)
			if err != nil {
				t.Fatalf("ResolveEnrollmentStatePathsForTest: %v", err)
			}
			crasher := startStateStoreHelper(t, root)
			crasher.Env = append(crasher.Env, storageStoreCrashStageEnv+"="+string(test.stage))
			code, stdout, stderr, err := runStorageLockHelper(t, crasher)
			if err == nil || code != storeCrashExitCode {
				t.Fatalf("crash helper: err=%v code=%d stdout=%q stderr=%q", err, code, stdout, stderr)
			}

			_, stateErr := os.Stat(paths.StatePath)
			if test.wantInstalled && stateErr != nil {
				t.Fatalf("installed state after post-move crash: %v", stateErr)
			}
			if !test.wantInstalled && !errors.Is(stateErr, os.ErrNotExist) {
				t.Fatalf("state after pre-move crash: %v, want absent", stateErr)
			}
			if test.wantInstalled {
				store, err := newFileEnrollmentStateStoreForTest(root)
				if err != nil {
					t.Fatalf("newFileEnrollmentStateStoreForTest: %v", err)
				}
				if _, found, err := store.Load(context.Background()); err != nil || !found {
					t.Fatalf("Load installed state after crash: found=%v err=%v", found, err)
				}
				duplicate := startStateStoreHelper(t, root)
				code, stdout, stderr, err = runStorageLockHelper(t, duplicate)
				if err == nil || code != storeTerminalExitCode || !strings.Contains(stdout+stderr, "TERMINAL") {
					t.Fatalf("duplicate after post-move crash: err=%v code=%d stdout=%q stderr=%q", err, code, stdout, stderr)
				}
				return
			}

			if _, err := os.Stat(paths.StatePath + ".tmp"); err != nil {
				t.Fatalf("flushed orphan after pre-move crash: %v", err)
			}
			recovery := startStateStoreHelper(t, root)
			code, stdout, stderr, err = runStorageLockHelper(t, recovery)
			if err != nil || code != 0 || !strings.Contains(stdout+stderr, "STORED") {
				t.Fatalf("recovery after pre-move crash: err=%v code=%d stdout=%q stderr=%q", err, code, stdout, stderr)
			}
			if _, err := os.Stat(paths.StatePath + ".tmp"); !errors.Is(err, os.ErrNotExist) {
				t.Fatalf("orphan after recovery: %v", err)
			}
		})
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

func TestStorageStoreHelper(t *testing.T) {
	if os.Getenv(storageStoreHelperEnv) != "1" {
		return
	}
	root := os.Getenv(storageLockRootEnv)
	store, err := newFileEnrollmentStateStoreForTest(root)
	if err != nil {
		os.Exit(lockErrorExitCode)
	}
	if crashStage := os.Getenv(storageStoreCrashStageEnv); crashStage != "" {
		enrollmentStateWriteStageHook = func(path string, stage enrollmentStateWriteStage) {
			if filepath.Base(path) == enrollmentStateFileName && string(stage) == crashStage {
				os.Exit(storeCrashExitCode)
			}
		}
	}
	request := validEnrollmentRequestPayload()
	requestPayload, err := EncodeEnrollmentRequestPayload(request)
	if err != nil {
		os.Exit(lockErrorExitCode)
	}
	result := validEnrollmentResultPayloadBoundToRequest(request, requestPayload, EnrollmentStatusAccepted)
	err = store.Store(context.Background(), *result.DeviceIdentity)
	if errors.Is(err, ErrStorageBusy) {
		fmt.Println("BUSY")
		os.Exit(lockBusyExitCode)
	}
	if err != nil {
		if errors.Is(err, ErrTerminalEnrollment) {
			fmt.Println("TERMINAL")
			os.Exit(storeTerminalExitCode)
		}
		os.Exit(lockErrorExitCode)
	}
	fmt.Println("STORED")
}

func tempDir(t *testing.T) string {
	t.Helper()
	return t.TempDir()
}

func tempEnrollmentRoot(t *testing.T) string {
	t.Helper()
	return trustedEnrollmentTestRoot(t)
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
	cmd := exec.Command("cmd", "/C", "mklink", "/J", link, target)
	output, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("%w: %s", err, strings.TrimSpace(string(output)))
	}
	return nil
}

func makeFileSymlink(t *testing.T, link, target string) error {
	t.Helper()
	cmd := exec.Command("cmd", "/C", "mklink", link, target)
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

func grantEveryoneFileFullAccess(t *testing.T, path string) error {
	t.Helper()
	cmd := exec.Command("icacls", path, "/grant", "*S-1-1-0:F")
	output, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("%w: %s", err, strings.TrimSpace(string(output)))
	}
	return nil
}

func grantEveryoneGenericWrite(t *testing.T, path string) error {
	t.Helper()
	cmd := exec.Command("icacls", path, "/grant", "*S-1-1-0:(GW)")
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

func startStateStoreHelper(t *testing.T, root string) *exec.Cmd {
	t.Helper()
	exe, err := os.Executable()
	if err != nil {
		t.Fatalf("os.Executable: %v", err)
	}
	cmd := exec.Command(exe, "-test.run=^TestStorageStoreHelper$", "-test.v=false")
	cmd.Env = append(os.Environ(), storageStoreHelperEnv+"=1", storageLockRootEnv+"="+root)
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
