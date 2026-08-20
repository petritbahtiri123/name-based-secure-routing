//go:build windows

package authority

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func trustedEnrollmentTestRoot(t *testing.T) string {
	t.Helper()
	root := filepath.Join(t.TempDir(), enrollmentStateDirectorySuffix)
	if err := os.MkdirAll(root, 0o700); err != nil {
		t.Fatalf("MkdirAll(%s): %v", root, err)
	}
	processSID, err := getCurrentProcessSID()
	if err != nil {
		t.Fatalf("getCurrentProcessSID: %v", err)
	}
	cmd := exec.Command(
		"icacls", root,
		"/inheritance:r",
		"/grant:r",
		"*"+processSID+":(OI)(CI)F",
		"*S-1-5-18:(OI)(CI)F",
		"*S-1-5-32-544:(OI)(CI)F",
	)
	if output, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("provision trusted test ACL: %v: %s", err, strings.TrimSpace(string(output)))
	}
	return root
}

func grantSIDFullAccess(t *testing.T, path, sid string, inherit bool) error {
	t.Helper()
	rights := "F"
	if inherit {
		rights = "(OI)(CI)F"
	}
	cmd := exec.Command("icacls", path, "/grant", "*"+sid+":"+rights)
	output, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("%w: %s", err, strings.TrimSpace(string(output)))
	}
	return nil
}
