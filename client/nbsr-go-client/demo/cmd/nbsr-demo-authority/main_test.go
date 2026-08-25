package main

import "testing"

func TestAuthorityCommandRequiresLoopbackRuntimeConfiguration(t *testing.T) {
	if err := validateArgs([]string{"--listen", "0.0.0.0:8443"}); err == nil {
		t.Fatal("externally exposed ACP listener accepted")
	}
	if err := validateArgs([]string{"--listen", "127.0.0.1:8443", "--runtime", "test-results/nbsr-demo/runtime"}); err != nil {
		t.Fatal(err)
	}
}
