package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestClientCommandRequiresExplicitBoundedInputs(t *testing.T) {
	valid := []string{"--config", "config.example.json", "--bootstrap", "test-results/nbsr-demo/runtime/client-bootstrap", "--ready", "test-results/nbsr-demo/runtime/client-ready.json"}
	if _, err := parseArgs(valid); err != nil {
		t.Fatal(err)
	}
	for _, invalid := range [][]string{{}, {"--config", "config.example.json", "--bootstrap", "../secret", "--ready", "ready.json"}, {"--config", "config.example.json", "--bootstrap", "test-results/nbsr-demo/runtime/client-bootstrap", "--ready", "../ready.json"}} {
		if _, err := parseArgs(invalid); err == nil {
			t.Fatalf("invalid arguments accepted: %v", invalid)
		}
	}
}

func TestReadinessArtifactContainsNoSecretsOrBackendState(t *testing.T) {
	path := filepath.Join(t.TempDir(), "client-ready.json")
	if err := writeReadiness(path, "127.0.0.1:18080"); err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	text := strings.ToLower(string(raw))
	for _, forbidden := range []string{"private", "secret", "route_grant", "backend", "origin"} {
		if strings.Contains(text, forbidden) {
			t.Fatalf("readiness leaked %q: %s", forbidden, raw)
		}
	}
}
