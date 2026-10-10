// Package testfixture provides owned paths for demo tests, never caller-path repair.
package testfixture

import (
	"path/filepath"
	"testing"
)

// TempDir resolves only a newly created testing-owned directory. Production
// storage validation still rejects aliases supplied by callers.
func TempDir(t testing.TB) string {
	t.Helper()
	root := t.TempDir()
	resolved, err := filepath.EvalSymlinks(root)
	if err != nil {
		t.Fatalf("resolve owned demo fixture %q: %v", root, err)
	}
	t.Logf("owned demo fixture: supplied=%q resolved=%q", root, resolved)
	return resolved
}
