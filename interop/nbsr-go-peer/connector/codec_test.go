//go:build connector_development

package connector

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestRetainedDevelopmentVectors(t *testing.T) {
	root := "../../../vectors/connector-registration-development-v1"
	raw, err := os.ReadFile(filepath.Join(root, "manifest.json"))
	if err != nil {
		t.Fatal(err)
	}
	var manifest struct {
		Cases []struct {
			File     string
			Accepted bool
			ALPN     string
		}
		Artifacts map[string]struct {
			SHA256 string
			Bytes  int
		}
	}
	if err = json.Unmarshal(raw, &manifest); err != nil {
		t.Fatal(err)
	}
	for _, c := range manifest.Cases {
		t.Run(c.File, func(t *testing.T) {
			raw, err := os.ReadFile(filepath.Join(root, c.File))
			if err != nil {
				t.Fatal(err)
			}
			hash := sha256.Sum256(raw)
			want := manifest.Artifacts[c.File]
			if hex.EncodeToString(hash[:]) != want.SHA256 || len(raw) != want.Bytes {
				t.Fatal("fixture hash mismatch")
			}
			e, err := Decode(c.ALPN, raw)
			if (err == nil) != c.Accepted {
				t.Fatalf("accepted=%v err=%v", c.Accepted, err)
			}
			if err == nil {
				encoded, err := Encode(e)
				if err != nil || !bytes.Equal(encoded, raw) {
					t.Fatal("round-trip differs")
				}
			}
		})
	}
}
