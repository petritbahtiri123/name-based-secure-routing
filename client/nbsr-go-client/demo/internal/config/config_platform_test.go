package config

import "testing"

func TestDemoBuildParentIsFixedPerSupportedPlatform(t *testing.T) {
	for platform, expected := range map[string]string{
		"windows": `C:\NBSR-build\nbsr-demo`,
		"linux":   "/opt/nbsr-build/nbsr-demo",
	} {
		actual, err := demoBuildParent(platform)
		if err != nil || actual != expected {
			t.Fatalf("fixed build parent for %s = %q, %v", platform, actual, err)
		}
	}
	for _, platform := range []string{"", "darwin", "freebsd", "windows/../linux"} {
		if _, err := demoBuildParent(platform); err == nil {
			t.Fatalf("unsupported platform accepted: %q", platform)
		}
	}
}
