package packageverify

import (
	"path/filepath"
	"testing"
)

func TestCheckedInPackage(t *testing.T) {
	root := filepath.Clean(filepath.Join("..", "..", "..", ".."))
	m, files, err := Verify(filepath.Join(root, "vectors", "federation-v0.1"), root)
	if err != nil {
		t.Fatal(err)
	}
	if len(m.Artifacts) != 8 || len(files) != 9 {
		t.Fatalf("inventory %d/%d", len(m.Artifacts), len(files))
	}
}
