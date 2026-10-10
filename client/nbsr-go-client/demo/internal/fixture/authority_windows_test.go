//go:build windows

package fixture

import (
	"errors"
	"path/filepath"
	"strings"
	"syscall"
	"testing"

	"nbsr.local/client/nbsr-go-client/demo/internal/testfixture"
	"nbsr.local/client/nbsr-go-client/internal/authority"
)

func TestDemoOwnedFixtureUnderShortTempRetainsAliasRejection(t *testing.T) {
	root := testfixture.TempDir(t)
	ptr, err := syscall.UTF16PtrFromString(root)
	if err != nil {
		t.Fatal(err)
	}
	buffer := make([]uint16, 32768)
	n, err := syscall.GetShortPathName(ptr, &buffer[0], uint32(len(buffer)))
	if err != nil {
		t.Fatal(err)
	}
	if n >= uint32(len(buffer)) {
		t.Fatal("short path exceeds buffer")
	}
	short := syscall.UTF16ToString(buffer[:n])
	if strings.EqualFold(short, root) {
		t.Skip("filesystem does not provide distinct short names")
	}
	resolved, err := filepath.EvalSymlinks(short)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.EqualFold(resolved, root) {
		t.Fatalf("short alias resolves outside owned root: %q", resolved)
	}
	t.Logf("owned=%q short=%q resolved=%q", root, short, resolved)
	server, err := Start(short)
	if server != nil {
		server.Close()
	}
	if !errors.Is(err, authority.ErrStoragePathRejected) {
		t.Fatalf("caller alias must remain rejected: %v", err)
	}
	t.Setenv("TEMP", short)
	t.Setenv("TMP", short)
	t.Run("short_temp", func(t *testing.T) {
		server, err := Start(testfixture.TempDir(t))
		if err != nil {
			t.Fatalf("owned canonical fixture: %v", err)
		}
		t.Cleanup(server.Close)
	})
}
