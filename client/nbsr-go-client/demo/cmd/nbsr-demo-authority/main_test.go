package main

import (
	"net"
	"os"
	"path/filepath"
	"testing"
)

func TestAuthorityCommandRequiresLoopbackRuntimeConfiguration(t *testing.T) {
	if err := validateArgs([]string{"--listen", "0.0.0.0:8443"}); err == nil {
		t.Fatal("externally exposed ACP listener accepted")
	}
	if err := validateArgs([]string{"--listen", "127.0.0.1:8443", "--runtime", "test-results/nbsr-demo/runtime"}); err != nil {
		t.Fatal(err)
	}
}

func TestStartPublishesStandaloneBootstrapAndAdmission(t *testing.T) {
	root := t.TempDir()
	previous, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	if err := os.Chdir(root); err != nil {
		t.Fatal(err)
	}
	defer os.Chdir(previous)
	if err := os.MkdirAll(filepath.FromSlash("test-results/nbsr-demo/runtime/client-bootstrap"), 0o700); err != nil {
		t.Fatal(err)
	}
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	address := listener.Addr().String()
	_ = listener.Close()
	server, err := start(commandOptions{listen: address, runtime: "test-results/nbsr-demo/runtime", bootstrap: "test-results/nbsr-demo/runtime/client-bootstrap", admission: "test-results/nbsr-demo/runtime/runtime-admission.conf"})
	if err != nil {
		t.Fatal(err)
	}
	server.Close()
	for _, path := range []string{"test-results/nbsr-demo/runtime/client-bootstrap/client-bootstrap.json", "test-results/nbsr-demo/runtime/runtime-admission.conf"} {
		if _, err := os.Stat(path); err != nil {
			t.Fatal(err)
		}
	}
}

func TestAuthorityCommandAcceptsOnlyBoundedClientBootstrapRuntimePath(t *testing.T) {
	valid := []string{"--listen", "127.0.0.1:8443", "--runtime", "test-results/nbsr-demo/runtime", "--client-bootstrap", "test-results/nbsr-demo/runtime/client-bootstrap", "--runtime-admission", "test-results/nbsr-demo/runtime/runtime-admission.conf"}
	if err := validateArgs(valid); err != nil {
		t.Fatal(err)
	}
	invalid := append([]string(nil), valid...)
	invalid[len(invalid)-1] = "../client-bootstrap"
	if err := validateArgs(invalid); err == nil {
		t.Fatal("bootstrap path traversal accepted")
	}
}
