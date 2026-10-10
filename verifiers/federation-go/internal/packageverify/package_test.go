package packageverify

import (
	"bytes"
	"os"
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

func TestExplicitVersionsAndAuthenticatedAuthorities(t *testing.T) {
	root := filepath.Clean(filepath.Join("..", "..", "..", ".."))
	v2 := filepath.Join(root, "vectors", "federation-v0.1-development-v2")
	if _, _, err := Verify(v2, root); err == nil {
		t.Fatal("default accepted v2")
	}
	for _, version := range []string{Version1, Version2} {
		dir := "federation-v0.1"
		if version == Version2 {
			dir = version
		}
		m, _, authorities, err := VerifyWithAuthorities(filepath.Join(root, "vectors", dir), root, version)
		if err != nil {
			t.Fatal(err)
		}
		wrong := Version1
		if version == Version1 {
			wrong = Version2
		}
		if _, _, _, err := VerifyWithAuthorities(filepath.Join(root, "vectors", dir), root, wrong); err == nil {
			t.Fatal("cross-version selection accepted")
		}
		if m.PackageVersion != version || len(authorities) != 8 {
			t.Fatal("wrong version/authority set")
		}
		if bytes.Contains(authorities[developmentPath], []byte("ACP_RESULT_SIGNING")) != (version == Version2) {
			t.Fatal("wrong registry selected")
		}
	}
	if _, _, _, err := VerifyWithAuthorities(v2, root, "unknown"); err == nil {
		t.Fatal("unknown version accepted")
	}
	for _, name := range []string{"manifest.json", "authority-locks.json", "README.md"} {
		t.Run(name, func(t *testing.T) {
			copyDir := t.TempDir()
			entries, err := os.ReadDir(v2)
			if err != nil {
				t.Fatal(err)
			}
			for _, entry := range entries {
				raw, err := os.ReadFile(filepath.Join(v2, entry.Name()))
				if err != nil {
					t.Fatal(err)
				}
				if entry.Name() == name {
					raw = append(raw, ' ')
				}
				if err := os.WriteFile(filepath.Join(copyDir, entry.Name()), raw, 0600); err != nil {
					t.Fatal(err)
				}
			}
			if _, _, _, err := VerifyWithAuthorities(copyDir, root, Version2); err == nil {
				t.Fatal("mutation accepted")
			}
		})
	}
}

func TestAuthoritySourcesFailClosed(t *testing.T) {
	root := filepath.Clean(filepath.Join("..", "..", "..", ".."))
	for _, version := range []string{Version1, Version2} {
		for _, mutation := range []string{"missing", "changed", "wrong-version"} {
			t.Run(version+"/"+mutation, func(t *testing.T) {
				repo, err := filepath.EvalSymlinks(t.TempDir())
				if err != nil {
					t.Fatal(err)
				}
				dir := "federation-v0.1"
				if version == Version2 {
					dir = version
				}
				pkg := filepath.Join(root, "vectors", dir)
				for _, name := range authorityPaths {
					source := name
					if version == Version1 && name == developmentPath {
						source = archivedDevelopmentPath
					}
					b, err := os.ReadFile(filepath.Join(root, source))
					if err != nil {
						t.Fatal(err)
					}
					dst := filepath.Join(repo, source)
					if err := os.MkdirAll(filepath.Dir(dst), 0700); err != nil {
						t.Fatal(err)
					}
					if err := os.WriteFile(dst, b, 0600); err != nil {
						t.Fatal(err)
					}
				}
				if _, _, _, err := VerifyWithAuthorities(pkg, repo, version); err != nil {
					t.Fatalf("positive control: %v", err)
				}
				source := developmentPath
				other := archivedDevelopmentPath
				if version == Version1 {
					source, other = other, source
				}
				dst := filepath.Join(repo, source)
				if mutation == "missing" {
					err = os.Remove(dst)
				} else {
					var b []byte
					b, err = os.ReadFile(filepath.Join(root, source))
					if mutation == "wrong-version" {
						b, err = os.ReadFile(filepath.Join(root, other))
					} else {
						b = append(b, ' ')
					}
					if err == nil {
						err = os.WriteFile(dst, b, 0600)
					}
				}
				if err != nil {
					t.Fatal(err)
				}
				if _, _, _, err := VerifyWithAuthorities(pkg, repo, version); err == nil {
					t.Fatal("authority mutation accepted")
				}
			})
		}
	}
}
