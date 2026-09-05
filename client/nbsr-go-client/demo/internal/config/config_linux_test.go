//go:build linux

package config

import (
	"os"
	"path/filepath"
	"testing"
)

// These tests execute only on Linux. Windows compilation is not Linux evidence.
func TestLinuxDemoBuildRootRetainsExactRunContainment(t *testing.T) {
	const runID = "linux-proof"
	if err := ValidateTask5Roots("test-results/nbsr-demo/runtime/"+runID, "/opt/nbsr-build/nbsr-demo/"+runID); err != nil {
		t.Fatalf("fixed Linux run root rejected: %v", err)
	}
	for _, root := range []string{
		"opt/nbsr-build/nbsr-demo/linux-proof", "/opt/nbsr-build/nbsr-demo",
		"/opt/nbsr-build/nbsr-demo/other-run", "/opt/nbsr-build/nbsr-demo/linux-proof/nested",
		"/opt/nbsr-build/elsewhere/linux-proof", "/tmp/linux-proof", `C:\NBSR-build\nbsr-demo\linux-proof`,
	} {
		if err := ValidateTask5Roots("test-results/nbsr-demo/runtime/"+runID, root); err == nil {
			t.Fatalf("non-contained Linux build root accepted: %q", root)
		}
	}
}

func TestLinuxDemoContainedPathRejectsSymlinkEscape(t *testing.T) {
	root, outside := t.TempDir(), t.TempDir()
	if err := os.Symlink(outside, filepath.Join(root, "escape")); err != nil {
		t.Fatal(err)
	}
	if err := ValidateTask5ContainedPath(root, filepath.Join(root, "escape", "binary")); err == nil {
		t.Fatal("Linux symlink escaped the selected run")
	}
	if err := os.Mkdir(filepath.Join(root, "inside"), 0700); err != nil {
		t.Fatal(err)
	}
	if err := ValidateTask5ContainedPath(root, filepath.Join(root, "inside", "binary")); err != nil {
		t.Fatalf("contained Linux child rejected: %v", err)
	}
}
