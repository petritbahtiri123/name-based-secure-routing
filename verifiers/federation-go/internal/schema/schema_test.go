package schema

import (
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"

	"nbsr.example/federation-verifier/internal/cbor"
)

func TestEveryAcceptedStaticFieldSatisfiesRegistrySchema(t *testing.T) {
	repo := filepath.Clean(filepath.Join("..", "..", "..", ".."))
	sr, _ := os.ReadFile(filepath.Join(repo, "docs/protocol/registries/federation-v0.1-schema-proposal.json"))
	dr, _ := os.ReadFile(filepath.Join(repo, "docs/protocol/registries/federation-v0.1-development.json"))
	r, err := Load(sr, dr)
	if err != nil {
		t.Fatal(err)
	}
	var doc struct {
		Vectors []struct{ Canonical, Expected, Class string } `json:"vectors"`
	}
	var raw map[string]any
	b, _ := os.ReadFile(filepath.Join(repo, "vectors/federation-v0.1/static-vectors.json"))
	_ = json.Unmarshal(b, &raw)
	for _, item := range raw["vectors"].([]any) {
		m := item.(map[string]any)
		if m["expected"] != "ACCEPT" {
			continue
		}
		class := m["object_class"].(string)
		data, _ := hex.DecodeString(m["canonical_cbor_hex"].(string))
		v, e := cbor.Decode(data)
		if e != nil {
			t.Fatal(e)
		}
		for _, f := range r.Objects[class].Fields {
			q, ok := cbor.Get(v, f.Key)
			if !ok {
				continue
			}
			if !r.validateWire(q, f.WireType) {
				t.Errorf("%s field %s wire %s", m["id"], f.Name, f.WireType)
				if c, ok := r.Composites[f.WireType]; ok && q.Kind == cbor.Map {
					for key, spec := range c.Fields {
						k, _ := strconv.ParseUint(key, 10, 64)
						x, _ := cbor.Get(q, k)
						if !r.validateSpec(x, spec) {
							t.Logf("nested %s=%s kind=%d", key, spec, x.Kind)
						}
					}
				}
			}
			if !r.validateBounds(q, f) {
				t.Errorf("%s field %s bounds %s", m["id"], f.Name, f.Bounds)
			}
		}
	}
	_ = doc
}

func TestAll18ClassesHaveClosedRecursiveFieldValidation(t *testing.T) {
	r := loadRegistry(t)
	if len(r.Objects) != 18 {
		t.Fatalf("got %d classes", len(r.Objects))
	}
	badCandidates := []cbor.Value{{Kind: cbor.Bool, Bool: true}, {Kind: cbor.Text, Text: "x"}, {Kind: cbor.Bytes, Bytes: []byte{1}}, {Kind: cbor.Array}, {Kind: cbor.Map}, {Kind: cbor.Null}}
	for class, obj := range r.Objects {
		t.Run(class, func(t *testing.T) {
			if obj.MaximumCanonicalPayloadBytes <= 0 || len(obj.Fields) == 0 {
				t.Fatal("missing closed schema limits")
			}
			for _, f := range obj.Fields {
				rejected := false
				for _, bad := range badCandidates {
					if !r.validateWire(bad, f.WireType) || !r.validateBounds(bad, f) {
						rejected = true
						break
					}
				}
				if !rejected {
					t.Fatalf("field %s has no rejected malformed representation", f.Name)
				}
			}
		})
	}
}

func TestNamedCompositesRejectUnknownAndMalformedMembers(t *testing.T) {
	r := loadRegistry(t)
	for name, c := range r.Composites {
		t.Run(name, func(t *testing.T) {
			if !c.Closed || c.MaximumEncodedBytes <= 0 {
				t.Fatal("composite is not closed and bounded")
			}
			if c.WireType == "map" {
				malformed := cbor.Value{Kind: cbor.Map, Map: []cbor.Pair{{Key: cbor.Value{Kind: cbor.Uint, Uint: 999}, Value: cbor.Value{Kind: cbor.Null}}}}
				if r.validateComposite(malformed, name) {
					t.Fatal("accepted unknown composite key")
				}
			} else if r.validateComposite(cbor.Value{Kind: cbor.Array}, name) && !strings.Contains(c.Cardinality, "0..") {
				t.Fatal("accepted empty required composite")
			}
		})
	}
}

func loadRegistry(t *testing.T) Registry {
	t.Helper()
	repo := filepath.Clean(filepath.Join("..", "..", "..", ".."))
	sr, e := os.ReadFile(filepath.Join(repo, "docs/protocol/registries/federation-v0.1-schema-proposal.json"))
	if e != nil {
		t.Fatal(e)
	}
	dr, e := os.ReadFile(filepath.Join(repo, "docs/protocol/registries/federation-v0.1-development.json"))
	if e != nil {
		t.Fatal(e)
	}
	r, e := Load(sr, dr)
	if e != nil {
		t.Fatal(e)
	}
	return r
}
