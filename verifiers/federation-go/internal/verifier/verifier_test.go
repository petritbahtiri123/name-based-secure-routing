package verifier

import (
	"nbsr.example/federation-verifier/internal/capability"
	"nbsr.example/federation-verifier/internal/precedence"
	"nbsr.example/federation-verifier/internal/schema"
	"nbsr.example/federation-verifier/internal/state"
	"nbsr.example/federation-verifier/internal/threshold"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestSignedRejectsUppercaseCOSEHex(t *testing.T) {
	root := filepath.Clean(filepath.Join("..", "..", "..", ".."))
	read := func(p string) []byte {
		b, e := os.ReadFile(filepath.Join(root, p))
		if e != nil {
			t.Fatal(e)
		}
		return b
	}
	regs, e := schema.Load(read("docs/protocol/registries/federation-v0.1-schema-proposal.json"), read("docs/protocol/registries/federation-v0.1-development.json"))
	if e != nil {
		t.Fatal(e)
	}
	raw := string(read("vectors/federation-v0.1/signed-vectors.json"))
	marker := `"cose_sign1_hex":"`
	start := strings.Index(raw, marker) + len(marker)
	end := start + strings.Index(raw[start:], `"`)
	raw = raw[:start] + strings.ToUpper(raw[start:end]) + raw[end:]
	_, divergences, e := VerifySigned([]byte(raw), regs)
	if e != nil {
		t.Fatal(e)
	}
	if len(divergences) == 0 {
		t.Fatal("uppercase COSE hex accepted")
	}
}

func TestStaticAndSignedVectors(t *testing.T) {
	root := filepath.Clean(filepath.Join("..", "..", "..", ".."))
	read := func(p string) []byte {
		b, e := os.ReadFile(filepath.Join(root, p))
		if e != nil {
			t.Fatal(e)
		}
		return b
	}
	r, e := schema.Load(read("docs/protocol/registries/federation-v0.1-schema-proposal.json"), read("docs/protocol/registries/federation-v0.1-development.json"))
	if e != nil {
		t.Fatal(e)
	}
	n, d, e := VerifyStatic(read("vectors/federation-v0.1/static-vectors.json"), r)
	if e != nil {
		t.Fatal(e)
	}
	if n != 35 || len(d) > 0 {
		t.Fatalf("static %d divergences: %v", n, d)
	}
	n, d, e = VerifySigned(read("vectors/federation-v0.1/signed-vectors.json"), r)
	if e != nil {
		t.Fatal(e)
	}
	if n != 12 || len(d) > 0 {
		t.Fatalf("signed %d divergences: %v", n, d)
	}
	n, d, e = threshold.VerifyDocument(read("vectors/federation-v0.1/threshold-vectors.json"))
	if e != nil {
		t.Fatal(e)
	}
	if n != 89 || len(d) > 0 {
		t.Fatalf("threshold %d divergences: %v", n, d)
	}
	n, d, e = capability.VerifyDocument(read("vectors/federation-v0.1/capability-vectors.json"))
	if e != nil {
		t.Fatal(e)
	}
	if n != 12 || len(d) > 0 {
		t.Fatalf("capability %d divergences: %v", n, d)
	}
	n, d, e = precedence.Verify(read("vectors/federation-v0.1/error-precedence.json"))
	if e != nil {
		t.Fatal(e)
	}
	if n != 11 || len(d) > 0 {
		t.Fatalf("precedence %d divergences: %v", n, d)
	}
	n, d, e = state.Verify(read("vectors/federation-v0.1/stateful-scenarios.json"))
	if e != nil {
		t.Fatal(e)
	}
	if n != 43 || len(d) > 0 {
		t.Fatalf("state %d divergences: %v", n, d)
	}
}
