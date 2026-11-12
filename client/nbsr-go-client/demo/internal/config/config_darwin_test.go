//go:build darwin

package config

import (
	"os"
	"path/filepath"
	"testing"
)

// Native-only coverage; simulated platform selection is separate evidence.
func TestDarwinDemoBuildRootRetainsExactRunContainment(t *testing.T) {
	home, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	t.Setenv("HOME", home)
	const runID = "darwin-proof"
	parent := filepath.Join(home, "Library", "Caches", "NBSR", "demo-build")
	runtimeRoot := "test-results/nbsr-demo/runtime/" + runID
	if err := ValidateTask5Roots(runtimeRoot, filepath.Join(parent, runID)); err != nil {
		t.Fatal(err)
	}
	for _, root := range []string{parent, filepath.Join(parent, "other"), filepath.Join(parent, runID, "nested"), filepath.Join(home, runID), "/opt/nbsr-build/nbsr-demo/" + runID} {
		if ValidateTask5Roots(runtimeRoot, root) == nil {
			t.Fatalf("accepted %q", root)
		}
	}
	root := filepath.Join(home, "run")
	if err := os.Mkdir(root, 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(t.TempDir(), filepath.Join(root, "escape")); err != nil {
		t.Fatal(err)
	}
	if ValidateTask5ContainedPath(root, filepath.Join(root, "escape", "binary")) == nil {
		t.Fatal("symlink escape accepted")
	}
}
