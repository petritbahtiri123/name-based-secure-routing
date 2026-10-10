//go:build windows

package authority

import (
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	"golang.org/x/sys/windows"
)

func trustedEnrollmentTestRoot(t *testing.T) string {
	t.Helper()
	root := filepath.Join(t.TempDir(), enrollmentStateDirectorySuffix)
	if err := os.MkdirAll(root, 0o700); err != nil {
		t.Fatalf("MkdirAll(%s): %v", root, err)
	}
	provisionTrustedEnrollmentTestACL(t, root)
	return root
}

func provisionTrustedEnrollmentTestACL(t *testing.T, root string) {
	t.Helper()
	processSID, err := getCurrentProcessSID()
	if err != nil {
		t.Fatalf("getCurrentProcessSID: %v", err)
	}
	// Replace the complete test-owned DACL. icacls /grant:r only replaces grants
	// for named SIDs and leaves unrelated explicit writers from the host behind.
	sd, err := windows.SecurityDescriptorFromString(
		"O:" + processSID + "D:P(A;OICI;FA;;;" + processSID + ")(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)",
	)
	if err != nil {
		t.Fatalf("build trusted test security descriptor: %v", err)
	}
	owner, _, err := sd.Owner()
	if err != nil {
		t.Fatal(err)
	}
	dacl, _, err := sd.DACL()
	if err != nil {
		t.Fatal(err)
	}
	if err := windows.SetNamedSecurityInfo(root, windows.SE_FILE_OBJECT,
		windows.OWNER_SECURITY_INFORMATION|windows.DACL_SECURITY_INFORMATION|windows.PROTECTED_DACL_SECURITY_INFORMATION,
		owner, nil, dacl, nil); err != nil {
		t.Fatalf("provision exact trusted test ACL: %v", err)
	}
}

func TestTrustedEnrollmentFixtureReplacesUnapprovedExplicitWriter(t *testing.T) {
	root := trustedEnrollmentTestRoot(t)
	// LocalService is a resolvable well-known SID, not an approved storage writer.
	const unrelatedSID = "S-1-5-19"
	if err := grantSIDFullAccess(t, root, unrelatedSID, false); err != nil {
		t.Fatal(err)
	}
	if err := validateOwnershipAndACL(root); !errors.Is(err, ErrStoragePathRejected) {
		t.Fatalf("unapproved writer must be rejected: %v", err)
	}
	provisionTrustedEnrollmentTestACL(t, root)
	if err := validateOwnershipAndACL(root); err != nil {
		t.Fatalf("provisioned fixture must contain only approved writers: %v", err)
	}
	if _, err := newFileEnrollmentStateStoreForTest(root); err != nil {
		t.Fatalf("store must accept the corrected fixture: %v", err)
	}
	if err := grantSIDFullAccess(t, root, unrelatedSID, false); err != nil {
		t.Fatal(err)
	}
	if _, err := newFileEnrollmentStateStoreForTest(root); !errors.Is(err, ErrStoragePathRejected) {
		t.Fatalf("store must still reject a newly added unapproved writer: %v", err)
	}
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
