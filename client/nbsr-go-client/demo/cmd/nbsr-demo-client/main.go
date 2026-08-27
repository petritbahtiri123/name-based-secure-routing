package main

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"

	"nbsr.local/client/nbsr-go-client/demo/internal/bootstrap"
	"nbsr.local/client/nbsr-go-client/demo/internal/client"
	democonfig "nbsr.local/client/nbsr-go-client/demo/internal/config"
	"nbsr.local/interop/nbsr-go-peer/wirepeer"
)

type commandOptions struct{ config, bootstrap, ready string }

func main() {
	options, err := parseArgs(os.Args[1:])
	if err != nil {
		os.Exit(2)
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	if err := run(ctx, options); err != nil && !errors.Is(err, context.Canceled) {
		os.Exit(1)
	}
}

func run(ctx context.Context, options commandOptions) error {
	configuration, err := democonfig.Load(options.config)
	if err != nil {
		return err
	}
	enrolled, err := bootstrap.Load(options.bootstrap)
	if err != nil {
		return err
	}
	service, err := democonfig.LoadServiceFixture(configuration.Client.ServiceFixture)
	if err != nil {
		return err
	}
	readiness, err := wirepeer.LoadReadiness(configuration.Client.DestinationReadiness)
	if err != nil {
		return err
	}
	assembly, err := client.NewStandaloneAssembly(configuration, enrolled, service, readiness)
	if err != nil {
		return err
	}
	defer assembly.Close()
	if err := writeReadiness(options.ready, assembly.Runtime.ProxyAddress()); err != nil {
		return err
	}
	defer os.Remove(options.ready)
	return assembly.Runtime.Serve(ctx)
}

func parseArgs(args []string) (commandOptions, error) {
	if len(args) != 6 {
		return commandOptions{}, errors.New("config, bootstrap and readiness are required")
	}
	var options commandOptions
	for index := 0; index < len(args); index += 2 {
		switch args[index] {
		case "--config":
			options.config = args[index+1]
		case "--bootstrap":
			options.bootstrap = args[index+1]
		case "--ready":
			options.ready = args[index+1]
		default:
			return commandOptions{}, errors.New("unknown argument")
		}
	}
	if options.config != "config.example.json" || !safeRuntimePath(options.bootstrap, "test-results/nbsr-demo/runtime/client-bootstrap") || !safeRuntimePath(options.ready, "test-results/nbsr-demo/runtime/client-ready.json") {
		return commandOptions{}, errors.New("invalid standalone client path")
	}
	return options, nil
}

func safeRuntimePath(value, exact string) bool {
	return !filepath.IsAbs(value) && filepath.ToSlash(filepath.Clean(value)) == exact
}

func writeReadiness(path, proxy string) error {
	if proxy == "" {
		return errors.New("empty proxy readiness")
	}
	raw, err := json.Marshal(struct{ Schema, Proxy, SyntheticIP, State string }{Schema: "nbsr-demo-client-ready-v1", Proxy: proxy, SyntheticIP: democonfig.SharedSyntheticIP, State: "ready"})
	if err != nil || len(raw) > 1024 {
		return errors.New("invalid client readiness")
	}
	raw = append(raw, '\n')
	directory := filepath.Dir(path)
	if err := os.MkdirAll(directory, 0o700); err != nil {
		return err
	}
	temporary, err := os.CreateTemp(directory, ".client-ready-*.tmp")
	if err != nil {
		return err
	}
	temporaryName := temporary.Name()
	defer os.Remove(temporaryName)
	if err = temporary.Chmod(0o600); err == nil {
		_, err = temporary.Write(raw)
	}
	if closeErr := temporary.Close(); err == nil {
		err = closeErr
	}
	if err != nil {
		return err
	}
	return os.Rename(temporaryName, path)
}
