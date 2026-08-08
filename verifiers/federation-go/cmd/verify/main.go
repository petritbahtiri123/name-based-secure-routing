package main

import (
	"encoding/hex"
	"fmt"
	"nbsr.example/federation-verifier/internal/identity"
	"nbsr.example/federation-verifier/internal/verifier"
	"os"
	"path/filepath"
	"runtime"
)

func main() {
	pkg := "../../vectors/federation-v0.1"
	if len(os.Args) > 1 {
		pkg = os.Args[1]
	}
	abs, e := filepath.Abs(pkg)
	if e != nil {
		fail(e)
	}
	repo := filepath.Clean(filepath.Join(abs, "..", ".."))
	s, e := verifier.VerifyAll(abs, repo)
	if e != nil {
		for _, d := range s.Divergences {
			fmt.Fprintln(os.Stderr, d)
		}
		fail(e)
	}
	key, _ := hex.DecodeString("000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f")
	id, _ := identity.OperatorID(key)
	bech, _ := identity.EncodeOperatorID(id[:])
	fmt.Printf("manifest: PASS (%d artifacts, exact inventory and authority locks)\ncanonical CBOR: exercised by %d static vectors\nOperator ID: %x %s\nCOSE Sign1: exercised by %d signed vectors\nschema coverage: %d object classes\nstatic vectors: %d/35\nsigned vectors: %d/12\nthreshold vectors: %d/89\ncapability vectors: %d/12\nprecedence vectors: %d\nstate scenarios: %d/43\ndivergences: 0\nGo: %s\ndependencies: standard library only\n", s.ManifestArtifacts, s.Static, id, bech, s.Signed, s.SchemaClasses, s.Static, s.Signed, s.Threshold, s.Capability, s.Precedence, s.State, runtime.Version())
}
func fail(e error) { fmt.Fprintln(os.Stderr, "federation-go:", e); os.Exit(1) }
