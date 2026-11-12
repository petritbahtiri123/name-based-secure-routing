//go:build !windows

package main

import "os"

func privateDirectory(path string) error { return os.Mkdir(path, 0700) }
