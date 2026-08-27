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

	democonfig "nbsr.local/client/nbsr-go-client/demo/internal/config"
	"nbsr.local/client/nbsr-go-client/demo/internal/fixture"
)

func main() {
	options, err := parseArgs(os.Args[1:])
	if err != nil {
		os.Exit(2)
	}
	if err := run(options); err != nil {
		os.Exit(1)
	}
}

func run(options commandOptions) error {
	server, err := start(options)
	if err != nil {
		return err
	}
	defer server.Close()
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	<-ctx.Done()
	return nil
}

func start(options commandOptions) (*fixture.Server, error) {
	runtimeRoot, err := filepath.Abs(options.runtime)
	if err != nil {
		return nil, err
	}
	bootstrapRoot := ""
	if options.bootstrap != "" {
		bootstrapRoot, err = filepath.Abs(options.bootstrap)
		if err != nil {
			return nil, err
		}
	}
	admissionPath := ""
	if options.admission != "" {
		admissionPath, err = filepath.Abs(options.admission)
		if err != nil {
			return nil, err
		}
	}
	var server *fixture.Server
	if options.bootstrap == "" {
		server, err = fixture.StartAt(runtimeRoot, options.listen)
	} else {
		server, err = fixture.StartStandaloneAt(runtimeRoot, options.listen, bootstrapRoot)
	}
	if err != nil {
		return nil, err
	}
	if options.admission != "" {
		var nonce [32]byte
		for index := range nonce {
			nonce[index] = 0x80 + byte(index)
		}
		raw, exportErr := server.PublicRuntimeAdmissionConfig(nonce)
		if exportErr != nil {
			server.Close()
			return nil, exportErr
		}
		if err := os.WriteFile(admissionPath, raw, 0o600); err != nil {
			server.Close()
			return nil, err
		}
	}
	return server, nil
}

func validateArgs(args []string) error {
	_, err := parseArgs(args)
	return err
}

type commandOptions struct{ listen, runtime, bootstrap, admission string }

func parseArgs(args []string) (commandOptions, error) {
	var options commandOptions
	for index := 0; index < len(args); index += 2 {
		if index+1 >= len(args) {
			return commandOptions{}, errors.New("missing argument value")
		}
		switch args[index] {
		case "--listen":
			options.listen = args[index+1]
		case "--runtime":
			options.runtime = args[index+1]
		case "--client-bootstrap":
			options.bootstrap = args[index+1]
		case "--runtime-admission":
			options.admission = args[index+1]
		default:
			return commandOptions{}, errors.New("unknown argument")
		}
	}
	host, port, err := net.SplitHostPort(options.listen)
	if err != nil || port == "" {
		return commandOptions{}, errors.New("invalid listen address")
	}
	address, err := netip.ParseAddr(host)
	if err != nil || !address.IsLoopback() {
		return commandOptions{}, errors.New("ACP must bind to loopback")
	}
	clean := filepath.ToSlash(filepath.Clean(options.runtime))
	legacy := clean == "test-results/nbsr-demo/runtime"
	if !legacy {
		if err := democonfig.ValidateTask5RuntimeRoot(options.runtime); err != nil {
			return commandOptions{}, errors.New("invalid demo runtime directory")
		}
	}
	if options.bootstrap != "" {
		if legacy && filepath.ToSlash(filepath.Clean(options.bootstrap)) != "test-results/nbsr-demo/runtime/client-bootstrap" {
			return commandOptions{}, errors.New("invalid demo client bootstrap directory")
		}
		if !legacy && democonfig.ValidateTask5ContainedPath(options.runtime, options.bootstrap) != nil {
			return commandOptions{}, errors.New("invalid demo client bootstrap directory")
		}
	}
	if options.admission != "" {
		if legacy && filepath.ToSlash(filepath.Clean(options.admission)) != "test-results/nbsr-demo/runtime/runtime-admission.conf" {
			return commandOptions{}, errors.New("invalid runtime admission path")
		}
		if !legacy && democonfig.ValidateTask5ContainedPath(options.runtime, options.admission) != nil {
			return commandOptions{}, errors.New("invalid runtime admission path")
		}
	}
	if options.admission != "" && options.bootstrap == "" {
		return commandOptions{}, errors.New("runtime admission requires standalone bootstrap")
	}
	return options, nil
}
