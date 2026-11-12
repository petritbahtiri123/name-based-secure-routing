package config

import (
	"os"
	"path/filepath"
	"testing"
)

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
	for _, platform := range []string{"", "freebsd", "windows/../linux"} {
		if _, err := demoBuildParent(platform); err == nil {
			t.Fatalf("unsupported platform accepted: %q", platform)
		}
	}
}
func TestDarwinBuildParent(t *testing.T) {
	home, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	actual, err := darwinBuildParent(home)
	if err != nil || actual != filepath.Join(home, "Library", "Caches", "NBSR", "demo-build") {
		t.Fatalf("%q %v", actual, err)
	}
	if _, err := darwinBuildParent("relative"); err == nil {
		t.Fatal("relative home accepted")
	}
	t.Setenv("HOME", home)
	t.Setenv("USERPROFILE", home)
	actual, err = demoBuildParent("darwin")
	if err != nil || actual != filepath.Join(home, "Library", "Caches", "NBSR", "demo-build") {
		t.Fatalf("%q %v", actual, err)
	}
	if err := os.Symlink(t.TempDir(), filepath.Join(home, "Library")); err != nil {
		t.Skipf("symlink unavailable: %v", err)
	}
	if _, err := darwinBuildParent(home); err == nil {
		t.Fatal("cache symlink escape accepted")
	}
}
