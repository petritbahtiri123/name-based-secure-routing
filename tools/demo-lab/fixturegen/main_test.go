package main

import (
	"crypto/ecdsa"
	"crypto/x509"
	"os"
	"path/filepath"
	"runtime"
	"testing"
	"time"
)

func TestGenerate(t *testing.T) {
	base, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	output := filepath.Join(base, "fixtures")
	now := time.Now().UTC().Truncate(time.Second)
	if err := generate(output, now); err != nil {
		t.Fatal(err)
	}
	entries, err := os.ReadDir(output)
	if err != nil || len(entries) != 5 {
		t.Fatalf("inventory %v %v", entries, err)
	}
	read := func(name string) []byte {
		b, e := os.ReadFile(filepath.Join(output, name))
		if e != nil {
			t.Fatal(e)
		}
		return b
	}
	ca, err := x509.ParseCertificate(read("ca.der"))
	if err != nil {
		t.Fatal(err)
	}
	if !ca.IsCA || !ca.BasicConstraintsValid || ca.Subject.CommonName != "NBSR Demo CA" || !ca.NotBefore.Equal(now.Add(-time.Minute)) || !ca.NotAfter.Equal(now.Add(2*time.Hour)) {
		t.Fatal("CA semantics")
	}
	if err := ca.CheckSignatureFrom(ca); err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"source", "destination"} {
		leaf, err := x509.ParseCertificate(read(name + ".der"))
		if err != nil {
			t.Fatal(err)
		}
		if err := leaf.CheckSignatureFrom(ca); err != nil {
			t.Fatal(err)
		}
		if len(leaf.DNSNames) != 1 || leaf.DNSNames[0] != name+".edge" || len(leaf.ExtKeyUsage) != 2 || leaf.ExtKeyUsage[0] != x509.ExtKeyUsageServerAuth || leaf.ExtKeyUsage[1] != x509.ExtKeyUsageClientAuth || !leaf.NotBefore.Equal(now.Add(-time.Minute)) || !leaf.NotAfter.Equal(now.Add(time.Hour)) {
			t.Fatal("leaf semantics")
		}
		key, err := x509.ParsePKCS8PrivateKey(read(name + "-key.der"))
		if err != nil {
			t.Fatal(err)
		}
		ec, ok := key.(*ecdsa.PrivateKey)
		if !ok || ec.Curve.Params().Name != "P-256" || !ec.PublicKey.Equal(leaf.PublicKey) {
			t.Fatal("key mismatch")
		}
		if runtime.GOOS != "windows" {
			info, _ := os.Stat(filepath.Join(output, name+"-key.der"))
			if info.Mode().Perm() != 0600 {
				t.Fatal("key not private")
			}
		}
	}
	if runtime.GOOS != "windows" {
		info, _ := os.Stat(output)
		if info.Mode().Perm() != 0700 {
			t.Fatal("directory not private")
		}
	}
	before := string(read("ca.der"))
	if err := generate(output, now); err == nil {
		t.Fatal("existing directory accepted")
	}
	if string(read("ca.der")) != before {
		t.Fatal("overwrote existing output")
	}
}
func TestRejectUnsafeOutput(t *testing.T) {
	base, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	for _, path := range []string{"", "relative", filepath.Join(base, "missing", "child")} {
		if generate(path, time.Now()) == nil {
			t.Fatalf("accepted %q", path)
		}
	}
	target := filepath.Join(base, "target")
	if err := os.Mkdir(target, 0700); err != nil {
		t.Fatal(err)
	}
	alias := filepath.Join(base, "alias")
	if err := os.Symlink(target, alias); err != nil {
		t.Skipf("symlink unavailable: %v", err)
	}
	if generate(filepath.Join(alias, "child"), time.Now()) == nil {
		t.Fatal("alias ancestor accepted")
	}
	if generate(alias, time.Now()) == nil {
		t.Fatal("alias output accepted")
	}
}
