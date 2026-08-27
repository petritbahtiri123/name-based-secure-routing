package bootstrap_test

import (
	"bytes"
	"crypto/ed25519"
	"os"
	"path/filepath"
	"testing"

	"nbsr.local/client/nbsr-go-client/demo/internal/bootstrap"
	"nbsr.local/client/nbsr-go-client/demo/internal/fixture"
)

func TestExportLoadProducesOwnedStrictEnrolledClientState(t *testing.T) {
	server, err := fixture.Start(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	defer server.Close()
	_, proofPrivate, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatal(err)
	}
	root := t.TempDir()
	if err := server.ExportClientBootstrap(root, proofPrivate); err != nil {
		t.Fatal(err)
	}
	state, err := bootstrap.Load(root)
	if err != nil {
		t.Fatal(err)
	}
	if state.Classification != bootstrap.Classification || state.Endpoint != server.Endpoint() || state.AcquireTemplate.Key != server.AcquireRequest().Key {
		t.Fatalf("loaded bootstrap mismatch: %+v", state)
	}
	if state.DeviceSigner.KeyRef() != server.DeviceSigner().KeyRef() || !bytes.Equal(state.TSProofPrivate, proofPrivate) {
		t.Fatal("private client ownership was not preserved")
	}
	state.TSProofPrivate[0] ^= 0xff
	reloaded, err := bootstrap.Load(root)
	if err != nil || bytes.Equal(reloaded.TSProofPrivate, state.TSProofPrivate) {
		t.Fatal("bootstrap loader did not return immutable owned state")
	}
}

func TestLoadRejectsUnknownFieldsTraversalAndSignerSubstitution(t *testing.T) {
	server, err := fixture.Start(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	defer server.Close()
	_, proofPrivate, _ := ed25519.GenerateKey(nil)
	root := t.TempDir()
	if err := server.ExportClientBootstrap(root, proofPrivate); err != nil {
		t.Fatal(err)
	}
	manifest := filepath.Join(root, bootstrap.ManifestName)
	raw, err := os.ReadFile(manifest)
	if err != nil {
		t.Fatal(err)
	}
	for name, mutation := range map[string][]byte{
		"unknown":   bytes.Replace(raw, []byte("}"), []byte(",\"unknown\":1}"), 1),
		"duplicate": bytes.Replace(raw, []byte("{"), []byte("{\"schema\":\"duplicate\","), 1),
		"traversal": bytes.Replace(raw, []byte("client-secret.json"), []byte("../client-secret.json"), 1),
	} {
		t.Run(name, func(t *testing.T) {
			copyRoot := t.TempDir()
			if err := os.WriteFile(filepath.Join(copyRoot, bootstrap.ManifestName), mutation, 0o600); err != nil {
				t.Fatal(err)
			}
			if _, err := bootstrap.Load(copyRoot); err == nil {
				t.Fatal("malformed bootstrap accepted")
			}
		})
	}
	secret := filepath.Join(root, "client-secret.json")
	secretRaw, err := os.ReadFile(secret)
	if err != nil {
		t.Fatal(err)
	}
	secretRaw[len(secretRaw)/2] ^= 1
	if err := os.WriteFile(secret, secretRaw, 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := bootstrap.Load(root); err == nil {
		t.Fatal("substituted signer material accepted")
	}
}
