package capability

import (
	"crypto/ed25519"
	"encoding/hex"
	"os"
	"path/filepath"
	"testing"

	"nbsr.example/federation-verifier/internal/strictjson"
)

func load(t *testing.T) (Document, ed25519.PublicKey) {
	t.Helper()
	repo := filepath.Clean(filepath.Join("..", "..", "..", ".."))
	raw, e := os.ReadFile(filepath.Join(repo, "vectors/federation-v0.1/capability-vectors.json"))
	if e != nil {
		t.Fatal(e)
	}
	var d Document
	if e = strictjson.Decode(raw, &d); e != nil {
		t.Fatal(e)
	}
	seed, e := hex.DecodeString(d.FixedPrivateKey)
	if e != nil || len(seed) != ed25519.SeedSize {
		t.Fatal("seed")
	}
	return d, ed25519.NewKeyFromSeed(seed).Public().(ed25519.PublicKey)
}

func TestDecisionIgnoresDuplicatedDescriptiveAndExpectedMetadata(t *testing.T) {
	d, pub := load(t)
	v := d.Vectors[0]
	v.Core = "bogus"
	v.Federation = "bogus"
	v.Profile = "bogus"
	v.Agreed = []uint64{99}
	v.Offered = []uint64{99}
	v.Session = "bogus"
	v.ThresholdDigest = "bogus"
	v.Case = "bogus"
	v.Expected = "REJECT"
	v.Reason = "ERR_SCHEMA"
	got := evaluate(v, pub)
	if got != (Decision{"ACCEPT", "NONE"}) {
		t.Fatalf("metadata influenced decision: %#v", got)
	}
}

func TestAuthenticatedDigestInputsFailClosed(t *testing.T) {
	d, pub := load(t)
	tests := []struct {
		name   string
		mut    func(*Vector)
		reason string
	}{{"capability set", func(v *Vector) { v.SetDigest = "00" + v.SetDigest[2:] }, "ERR_DOWNGRADE"}, {"transcript", func(v *Vector) { v.Transcript = "00" + v.Transcript[2:] }, "ERR_REPLAY"}, {"threshold context", func(v *Vector) { v.SignedThreshold = "00" + v.SignedThreshold[2:] }, "ERR_REPLAY"}}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			v := d.Vectors[0]
			tc.mut(&v)
			if got := evaluate(v, pub); got.Reason != tc.reason {
				t.Fatalf("got %#v", got)
			}
		})
	}
}
