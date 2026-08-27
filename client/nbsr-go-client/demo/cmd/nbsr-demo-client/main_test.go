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

func TestClientCommandAcceptsOnlyOneTask5Run(t *testing.T) {
	root := filepath.FromSlash("test-results/nbsr-demo/runtime/client-run")
	for _, directory := range []string{"client/bootstrap", "readiness"} {
		if err := os.MkdirAll(filepath.Join(root, filepath.FromSlash(directory)), 0o700); err != nil {
			t.Fatal(err)
		}
	}
	t.Cleanup(func() { _ = os.RemoveAll(root) })
	valid := []string{"--config", filepath.ToSlash(filepath.Join(root, "client", "config.json")), "--bootstrap", filepath.ToSlash(filepath.Join(root, "client", "bootstrap")), "--ready", filepath.ToSlash(filepath.Join(root, "readiness", "client.json")), "--runtime-root", filepath.ToSlash(root), "--build-root", `C:\NBSR-build\nbsr-demo\client-run`}
	options, err := parseArgs(valid)
	if err != nil {
		t.Fatal(err)
	}
	if options.runtimeRoot == "" || options.buildRoot == "" {
		t.Fatal("Task 5 roots were not retained")
	}
	invalid := append([]string(nil), valid...)
	invalid[3] = "test-results/nbsr-demo/runtime/run-b/client/bootstrap"
	if _, err := parseArgs(invalid); err == nil {
		t.Fatal("another run's bootstrap was accepted")
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
