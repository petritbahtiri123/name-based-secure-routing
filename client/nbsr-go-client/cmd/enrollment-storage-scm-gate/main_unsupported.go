//go:build !windows

package main

import "fmt"

func main() {
	fmt.Println("enrollment-storage-scm-gate is Windows-only")
}
