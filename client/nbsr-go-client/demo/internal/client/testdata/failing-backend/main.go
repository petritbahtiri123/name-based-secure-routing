// Test-only admitted backend failure helper. It has no listener and is never
// part of the production demo command surface.
package main

import "os"

var countPath string

func main() {
	if countPath == "" {
		os.Exit(24)
	}
	if err := os.WriteFile(countPath, []byte("1"), 0o600); err != nil {
		os.Exit(25)
	}
	os.Exit(23)
}
