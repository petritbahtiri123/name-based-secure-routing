package main

import (
	"context"
	"errors"
	"net"
	"net/netip"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"

	"nbsr.local/client/nbsr-go-client/demo/internal/fixture"
)

func main() {
	listen, runtime, err := parseArgs(os.Args[1:])
	if err != nil {
		os.Exit(2)
	}
	server, err := fixture.StartAt(runtime, listen)
	if err != nil {
		os.Exit(1)
	}
	defer server.Close()
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	<-ctx.Done()
}

func validateArgs(args []string) error {
	_, _, err := parseArgs(args)
	return err
}

func parseArgs(args []string) (string, string, error) {
	var listen, runtime string
	for index := 0; index < len(args); index += 2 {
		if index+1 >= len(args) {
			return "", "", errors.New("missing argument value")
		}
		switch args[index] {
		case "--listen":
			listen = args[index+1]
		case "--runtime":
			runtime = args[index+1]
		default:
			return "", "", errors.New("unknown argument")
		}
	}
	host, port, err := net.SplitHostPort(listen)
	if err != nil || port == "" {
		return "", "", errors.New("invalid listen address")
	}
	address, err := netip.ParseAddr(host)
	if err != nil || !address.IsLoopback() {
		return "", "", errors.New("ACP must bind to loopback")
	}
	clean := filepath.ToSlash(filepath.Clean(runtime))
	if clean != "test-results/nbsr-demo/runtime" {
		return "", "", errors.New("invalid demo runtime directory")
	}
	return listen, runtime, nil
}
