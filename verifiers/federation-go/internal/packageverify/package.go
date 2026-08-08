package packageverify

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"nbsr.example/federation-verifier/internal/strictjson"
)

const MaxPackageFile = 1 << 20
const manifestSHA256 = "1ff9591b925e926e757bb57ab8f3cd1620b6ff9d41149df92ad5672ff810ab35"

var authorityPaths = []string{"docs/protocol/core-v0.1-wire.md", "docs/protocol/registries/core-v0.2-baseline-lock.json", "docs/protocol/registries/federation-v0.1-development.json", "docs/protocol/registries/federation-v0.1-schema-proposal.json", "vectors/federation-v0.1-schema-proposal/literal-fixtures.json", "tests/federation/fixtures/task6-state-scenarios.json", "docs/protocol/registries/federation-v0.1-threshold-container-proposal.json", "vectors/federation-v0.1-threshold-container/literal-fixtures.json"}

type Artifact struct {
	Class               string   `json:"class"`
	Dependencies        []string `json:"dependencies"`
	Enforcement         *string  `json:"enforcement"`
	ExpectedOutcome     *string  `json:"expected_outcome"`
	ExpectedReason      *string  `json:"expected_reason"`
	ExpectedStateDigest *string  `json:"expected_state_digest"`
	FederationVersion   string   `json:"federation_version"`
	FixedTime           uint64   `json:"fixed_time"`
	ID                  string   `json:"id"`
	Length              int64    `json:"length"`
	Mutation            bool     `json:"mutation"`
	Path                string   `json:"path"`
	Profile             string   `json:"profile"`
	SHA256              string   `json:"sha256"`
}
type Manifest struct {
	Artifacts      []Artifact `json:"artifacts"`
	Authority      string     `json:"authority"`
	FormatVersion  uint64     `json:"format_version"`
	Package        string     `json:"package"`
	PackageVersion string     `json:"package_version"`
}
type Authority struct {
	Length int64  `json:"length"`
	Path   string `json:"path"`
	SHA256 string `json:"sha256"`
}
type Locks struct {
	AcceptedBaselineCommit      string      `json:"accepted_baseline_commit"`
	Authorities                 []Authority `json:"authorities"`
	Authority                   string      `json:"authority"`
	CoreV02ArtifactCount        int         `json:"core_v02_artifact_count"`
	FederationObjectCount       int         `json:"federation_object_count"`
	FormatVersion               int         `json:"format_version"`
	SchemaLiteralCount          int         `json:"schema_literal_count"`
	Task6ScenarioCount          int         `json:"task6_scenario_count"`
	ThresholdEvidenceCapability int         `json:"threshold_evidence_capability"`
	ThresholdLiteralCount       int         `json:"threshold_literal_count"`
}

func safeRel(p string) bool {
	if p == "" || filepath.IsAbs(p) || strings.Contains(p, "\\") {
		return false
	}
	c := filepath.Clean(filepath.FromSlash(p))
	return c != fmt.Sprintf("..%c", filepath.Separator) && !strings.HasPrefix(c, fmt.Sprintf("..%c", filepath.Separator)) && filepath.ToSlash(c) == p
}
func ReadRegular(path string, max int64) ([]byte, error) {
	abs, e := filepath.Abs(path)
	if e != nil {
		return nil, e
	}
	resolved, e := filepath.EvalSymlinks(abs)
	if e != nil {
		return nil, e
	}
	if !strings.EqualFold(filepath.Clean(abs), filepath.Clean(resolved)) {
		return nil, fmt.Errorf("symlinked path %s", path)
	}
	before, e := os.Lstat(path)
	if e != nil {
		return nil, e
	}
	if before.Mode()&os.ModeSymlink != 0 || !before.Mode().IsRegular() {
		return nil, fmt.Errorf("unsafe file %s", path)
	}
	f, e := os.Open(path)
	if e != nil {
		return nil, e
	}
	defer f.Close()
	st, e := f.Stat()
	if e != nil {
		return nil, e
	}
	if !st.Mode().IsRegular() || !os.SameFile(before, st) || st.Size() > max {
		return nil, fmt.Errorf("unsafe or oversized file %s", path)
	}
	b, e := io.ReadAll(io.LimitReader(f, max+1))
	if e != nil {
		return nil, e
	}
	if int64(len(b)) != st.Size() {
		return nil, fmt.Errorf("file changed while reading")
	}
	return b, nil
}
func Verify(pkg, repo string) (Manifest, map[string][]byte, error) {
	raw, e := ReadRegular(filepath.Join(pkg, "manifest.json"), MaxPackageFile)
	if e != nil {
		return Manifest{}, nil, e
	}
	if sum(raw) != manifestSHA256 {
		return Manifest{}, nil, fmt.Errorf("untrusted manifest digest")
	}
	var m Manifest
	if e = strictjson.Decode(raw, &m); e != nil {
		return m, nil, e
	}
	if m.FormatVersion != 1 || m.Package != "federation-v0.1" || m.PackageVersion != "federation-v0.1-development-v1" {
		return m, nil, fmt.Errorf("manifest version/profile")
	}
	if m.Authority != "WP8 Task 7 deterministic Federation v0.1 conformance package" || len(m.Artifacts) != 8 {
		return m, nil, fmt.Errorf("manifest authority/count")
	}
	want := map[string]Artifact{"manifest.json": {Path: "manifest.json", Length: int64(len(raw)), SHA256: sum(raw)}}
	ids := map[string]bool{}
	for _, a := range m.Artifacts {
		if !safeRel(a.Path) || a.Path == "manifest.json" || a.Length < 0 || a.Length > MaxPackageFile || a.FederationVersion != "federation-v0.1" || a.Profile != "federation-v0.1-development" || ids[a.ID] {
			return m, nil, fmt.Errorf("invalid manifest artifact %q", a.Path)
		}
		if _, dup := want[a.Path]; dup {
			return m, nil, fmt.Errorf("duplicate artifact path %q", a.Path)
		}
		ids[a.ID] = true
		want[a.Path] = a
	}
	for _, a := range m.Artifacts {
		for _, d := range a.Dependencies {
			if !ids[d] {
				return m, nil, fmt.Errorf("unknown dependency %q", d)
			}
		}
	}
	visiting, done := map[string]bool{}, map[string]bool{}
	byID := map[string]Artifact{}
	for _, a := range m.Artifacts {
		byID[a.ID] = a
	}
	var visit func(string) error
	visit = func(id string) error {
		if visiting[id] {
			return fmt.Errorf("dependency cycle")
		}
		if done[id] {
			return nil
		}
		visiting[id] = true
		for _, d := range byID[id].Dependencies {
			if d == id {
				return fmt.Errorf("self dependency")
			}
			if e := visit(d); e != nil {
				return e
			}
		}
		visiting[id] = false
		done[id] = true
		return nil
	}
	for id := range byID {
		if e := visit(id); e != nil {
			return m, nil, e
		}
	}
	got := []string{}
	e = filepath.WalkDir(pkg, func(p string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if p == pkg {
			return nil
		}
		rel, _ := filepath.Rel(pkg, p)
		rel = filepath.ToSlash(rel)
		if d.Type()&os.ModeSymlink != 0 {
			return fmt.Errorf("symlink %s", rel)
		}
		if d.IsDir() {
			return nil
		}
		if !d.Type().IsRegular() {
			return fmt.Errorf("nonregular %s", rel)
		}
		got = append(got, rel)
		return nil
	})
	if e != nil {
		return m, nil, e
	}
	sort.Strings(got)
	names := make([]string, 0, len(want))
	for n := range want {
		names = append(names, n)
	}
	sort.Strings(names)
	if strings.Join(got, "\n") != strings.Join(names, "\n") {
		return m, nil, fmt.Errorf("inventory mismatch")
	}
	files := map[string][]byte{"manifest.json": raw}
	for _, a := range m.Artifacts {
		b, e := ReadRegular(filepath.Join(pkg, filepath.FromSlash(a.Path)), MaxPackageFile)
		if e != nil {
			return m, nil, e
		}
		if int64(len(b)) != a.Length || sum(b) != a.SHA256 {
			return m, nil, fmt.Errorf("length/hash mismatch %s", a.Path)
		}
		files[a.Path] = b
	}
	var l Locks
	if e = strictjson.Decode(files["authority-locks.json"], &l); e != nil {
		return m, nil, e
	}
	if l.Authority != "WP8 Task 7 immutable upstream authority locks" || l.AcceptedBaselineCommit != "0849b986d065105441e116dce15294250a323926" || len(l.Authorities) != 8 || l.FormatVersion != 1 || l.CoreV02ArtifactCount != 110 || l.FederationObjectCount != 18 || l.SchemaLiteralCount != 28 || l.Task6ScenarioCount != 4 || l.ThresholdEvidenceCapability != 6 || l.ThresholdLiteralCount != 89 {
		return m, nil, fmt.Errorf("authority lock constants")
	}
	for i, a := range l.Authorities {
		if a.Path != authorityPaths[i] {
			return m, nil, fmt.Errorf("authority inventory/order")
		}
		if !safeRel(a.Path) || a.Length < 0 || a.Length > MaxPackageFile {
			return m, nil, fmt.Errorf("authority path")
		}
		b, e := ReadRegular(filepath.Join(repo, filepath.FromSlash(a.Path)), MaxPackageFile)
		if e != nil {
			return m, nil, e
		}
		if int64(len(b)) != a.Length || sum(b) != a.SHA256 {
			return m, nil, fmt.Errorf("authority drift %s", a.Path)
		}
	}
	return m, files, nil
}
func sum(b []byte) string { x := sha256.Sum256(b); return hex.EncodeToString(x[:]) }
