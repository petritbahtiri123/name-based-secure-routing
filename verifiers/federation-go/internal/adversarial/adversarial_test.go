package adversarial

import (
	"crypto/ed25519"
	"encoding/hex"
	"encoding/json"
	"nbsr.example/federation-verifier/internal/cbor"
	"nbsr.example/federation-verifier/internal/cose"
	"nbsr.example/federation-verifier/internal/packageverify"
	"nbsr.example/federation-verifier/internal/strictjson"
	"nbsr.example/federation-verifier/internal/threshold"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func root() string { return filepath.Clean(filepath.Join("..", "..", "..", "..")) }
func TestCBORNativeMutations(t *testing.T) {
	bad := []string{"1800", "a201020103", "a202030102", "d18340", "00ff"}
	for _, h := range bad {
		b, _ := hex.DecodeString(h)
		if _, e := cbor.Decode(b); e == nil {
			t.Fatalf("accepted CBOR mutation %s", h)
		}
	}
}
func TestCOSENativeMutations(t *testing.T) {
	raw, _ := os.ReadFile(filepath.Join(root(), "vectors/federation-v0.1/signed-vectors.json"))
	var d struct {
		Vectors []struct {
			COSE     string `json:"cose_sign1_hex"`
			SignerID string `json:"signer_record_id"`
		} `json:"vectors"`
		Signers []struct {
			RecordID string `json:"record_id"`
			Public   string `json:"signing_public_key"`
			Kid      string `json:"kid"`
		} `json:"trusted_signers"`
		Authority      string `json:"authority"`
		FormatVersion  int    `json:"format_version"`
		ObjectCoverage any    `json:"object_coverage"`
	}
	if e := strictjson.Validate(raw); e != nil {
		t.Fatal(e)
	}
	if e := json.Unmarshal(raw, &d); e != nil {
		t.Fatal(e)
	}
	b, _ := hex.DecodeString(d.Vectors[0].COSE)
	s, e := cose.Parse(b)
	if e != nil {
		t.Fatal(e)
	}
	var publicHex, kidHex string
	for _, record := range d.Signers {
		if record.RecordID == d.Vectors[0].SignerID {
			publicHex, kidHex = record.Public, record.Kid
		}
	}
	publicRaw, _ := hex.DecodeString(publicHex)
	pub := ed25519.PublicKey(publicRaw)
	kid, _ := hex.DecodeString(kidHex)
	payload := append([]byte(nil), s.Payload...)
	payload[0] ^= 1
	if e = s.Verify(pub, payload, kid); e == nil {
		t.Fatal("accepted payload flip")
	}
	s.Signature[0] ^= 1
	if e = s.Verify(pub, s.Payload, kid); e == nil {
		t.Fatal("accepted signature flip")
	}
	if e = s.Verify(pub, s.Payload, []byte("mutated-kid")); e == nil {
		t.Fatal("accepted kid mutation")
	}
	malformed := append([]byte(nil), b...)
	malformed[0] = 0xd1
	if _, e := cose.Parse(malformed); e == nil {
		t.Fatal("accepted malformed COSE tag")
	}
}
func TestThresholdNativeMutations(t *testing.T) {
	raw, _ := os.ReadFile(filepath.Join(root(), "vectors/federation-v0.1/threshold-vectors.json"))
	var d threshold.Document
	if e := strictjson.Decode(raw, &d); e != nil {
		t.Fatal(e)
	}
	base := d.Vectors[1]
	decode := func() cbor.Value {
		b, _ := hex.DecodeString(base.Canonical)
		v, e := cbor.Decode(b)
		if e != nil {
			t.Fatal(e)
		}
		return v
	}
	run := func(name string, v cbor.Value, ctx threshold.Context, want string) {
		t.Helper()
		b, _ := cbor.Encode(v)
		g := threshold.Evaluate(b, ctx)
		if g.Reason != want {
			t.Fatalf("%s got %s want %s", name, g.Reason, want)
		}
	}
	v := decode()
	groups, _ := cbor.Get(v, 9)
	signers, _ := cbor.Get(groups.Array[0], 2)
	signers.Array[0], signers.Array[1] = signers.Array[1], signers.Array[0]
	set(&groups.Array[0], 2, signers)
	set(&v, 9, groups)
	run("signer reorder", v, base.Context, "ERR_AUTHORITY")
	v = decode()
	groups, _ = cbor.Get(v, 9)
	signers, _ = cbor.Get(groups.Array[0], 2)
	signers.Array = append(signers.Array, signers.Array[0])
	set(&groups.Array[0], 2, signers)
	set(&v, 9, groups)
	run("duplicated signer", v, base.Context, "ERR_AUTHORITY")
	// The signed same-organization regression must preserve valid signatures;
	// use the specification-authored independently signed construction rather
	// than mutating signature-bound organization bytes after signing.
	sameOrg := d.Vectors[14]
	b, _ := hex.DecodeString(sameOrg.Canonical)
	got := threshold.Evaluate(b, sameOrg.Context)
	if got.Reason != "ERR_WITNESS_THRESHOLD" {
		t.Fatalf("same organization multiple keys got %s", got.Reason)
	}
	v = decode()
	set(&v, 2, cbor.Value{Kind: cbor.Text, Text: "wrong-profile"})
	run("wrong profile", v, base.Context, "ERR_VERSION")
	v = decode()
	line, _ := cbor.Get(v, 7)
	set(&line, 1, cbor.Value{Kind: cbor.Uint, Uint: 99})
	set(&v, 7, line)
	run("wrong generation", v, base.Context, "ERR_REPLAY")
	ctx := base.Context
	ctx.AuthenticatedCapabilities = []any{}
	run("capability stripping", decode(), ctx, "ERR_DOWNGRADE")
	ctx = base.Context
	ctx.SessionDigest = strings.Repeat("00", 32)
	run("transcript mutation", decode(), ctx, "ERR_REPLAY")
}
func TestPackageNativeMutations(t *testing.T) {
	src := filepath.Join(root(), "vectors/federation-v0.1")
	cases := []struct {
		name string
		mut  func(string)
	}{{"manifest hash", func(d string) {
		p := filepath.Join(d, "manifest.json")
		b, _ := os.ReadFile(p)
		s := string(b)
		i := strings.Index(s, `"sha256":"`)
		if i < 0 {
			panic("manifest has no sha256 field")
		}
		i += len(`"sha256":"`)
		replacement := byte('0')
		if s[i] == '0' {
			replacement = '1'
		}
		b[i] = replacement
		os.WriteFile(p, b, 0600)
	}}, {"extra unlisted", func(d string) { os.WriteFile(filepath.Join(d, "extra.json"), []byte("{}"), 0600) }}, {"truncated", func(d string) {
		p := filepath.Join(d, "static-vectors.json")
		b, _ := os.ReadFile(p)
		os.WriteFile(p, b[:len(b)-1], 0600)
	}}, {"oversized", func(d string) {
		p := filepath.Join(d, "threshold-vectors.json")
		os.WriteFile(p, make([]byte, (1<<20)+1), 0600)
	}}}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			d := t.TempDir()
			copyPackage(t, src, d)
			tc.mut(d)
			if _, _, e := packageverify.Verify(d, root()); e == nil {
				t.Fatal("accepted package mutation")
			}
		})
	}
}
func set(m *cbor.Value, k uint64, v cbor.Value) {
	for i := range m.Map {
		if m.Map[i].Key.Kind == cbor.Uint && m.Map[i].Key.Uint == k {
			m.Map[i].Value = v
			return
		}
	}
	m.Map = append(m.Map, cbor.Pair{Key: cbor.Value{Kind: cbor.Uint, Uint: k}, Value: v})
}
func copyPackage(t *testing.T, src, dst string) {
	t.Helper()
	xs, _ := os.ReadDir(src)
	for _, x := range xs {
		b, e := os.ReadFile(filepath.Join(src, x.Name()))
		if e != nil {
			t.Fatal(e)
		}
		if e = os.WriteFile(filepath.Join(dst, x.Name()), b, 0600); e != nil {
			t.Fatal(e)
		}
	}
}
