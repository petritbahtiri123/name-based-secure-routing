//go:build windows

package authority

import (
	"errors"
	"os"
	"path/filepath"
	"testing"

	"golang.org/x/sys/windows"
)

func TestIdempotencyStorageShortPathBoundary(t *testing.T) {
	root, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	ptr, err := windows.UTF16PtrFromString(root)
	if err != nil {
		t.Fatal(err)
	}
	buffer := make([]uint16, 32768)
	n, err := windows.GetShortPathName(ptr, &buffer[0], uint32(len(buffer)))
	if err != nil {
		t.Fatal(err)
	}
	if n >= uint32(len(buffer)) {
		t.Fatal("short path exceeds buffer")
	}
	short := windows.UTF16ToString(buffer[:n])
	if sameFilesystemPath(root, short) {
		t.Skip("filesystem does not provide distinct short names")
	}
	resolved, err := filepath.EvalSymlinks(short)
	if err != nil {
		t.Fatal(err)
	}
	if !sameFilesystemPath(root, resolved) {
		t.Fatalf("resolved alias %q differs from owned root %q", resolved, root)
	}
	sd, err := windows.GetNamedSecurityInfo(root, windows.SE_FILE_OBJECT, windows.OWNER_SECURITY_INFORMATION|windows.DACL_SECURITY_INFORMATION)
	if err != nil {
		t.Fatal(err)
	}
	t.Logf("TEMP=%q TMP=%q owned=%q short=%q resolved=%q descriptor=%s", os.Getenv("TEMP"), os.Getenv("TMP"), root, short, resolved, sd.String())
	shortFile := filepath.Join(short, "idempotency.cbor")
	if _, err := validateIdempotencyStorePath(shortFile); !errors.Is(err, ErrStoragePathRejected) {
		t.Fatalf("short alias must remain rejected, got %v", err)
	}
	// The same directory permits file creation and locking: rejection happens
	// before either operation, at the parent-versus-resolved path comparison.
	lock, err := acquireIdempotencyFileLock(shortFile + ".probe")
	if err != nil {
		t.Fatalf("short-path OS create/lock: %v", err)
	}
	if err := lock.Close(); err != nil {
		t.Fatal(err)
	}
	store, err := NewFileIdempotencyStore(testFileIdempotencyStoreConfig(filepath.Join(root, "idempotency.cbor"), 8, 2<<20))
	if err != nil {
		t.Fatalf("canonical path constructor: %v", err)
	}
	if err := store.Close(); err != nil {
		t.Fatal(err)
	}
	t.Run("fixture_under_short_temp", func(t *testing.T) {
		t.Setenv("TMP", short)
		t.Setenv("TEMP", short)
		fixture := idempotencyTestRoot(t)
		store := newTestFileIdempotencyStore(t, filepath.Join(fixture, "fixture.cbor"), 8, 2<<20)
		if err := store.Close(); err != nil {
			t.Fatal(err)
		}
	})
}
