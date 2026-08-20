//go:build !windows

package authority

import "testing"

func trustedEnrollmentTestRoot(t *testing.T) string {
	t.Helper()
	t.Skip("secure enrollment file storage is Windows-only")
	return ""
}
