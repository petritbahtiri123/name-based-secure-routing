package main

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestLifecycleCompletionWaitsBeforeCloseAndControllerAck(t *testing.T) {
	root := t.TempDir()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	if err := os.WriteFile(filepath.Join(root, "destination-1.complete"), []byte("complete\n"), 0600); err != nil {
		t.Fatal(err)
	}
	closed := make(chan struct{})
	done := make(chan error, 1)
	go func() {
		done <- finishLifecycleConnection(ctx, root, 0, true, func() error { close(closed); return nil })
	}()
	select {
	case <-closed:
		t.Fatal("closed before destination send completion")
	case <-time.After(30 * time.Millisecond):
	}
	if _, err := os.Stat(filepath.Join(root, "connection-0.ack")); !os.IsNotExist(err) {
		t.Fatal("early controller ack")
	}
	if err := os.WriteFile(filepath.Join(root, "destination-0.complete"), []byte("complete\n"), 0600); err != nil {
		t.Fatal(err)
	}
	select {
	case err := <-done:
		if err != nil {
			t.Fatal(err)
		}
	case <-time.After(time.Second):
		t.Fatal("completion blocked")
	}
	<-closed
	if data, err := os.ReadFile(filepath.Join(root, "connection-0.ack")); err != nil || string(data) != "complete\n" {
		t.Fatal("missing controller ack")
	}
}

func TestLifecycleCompletionRejectsCancellationAndMalformedMarker(t *testing.T) {
	for _, mode := range []string{"canceled", "malformed", "wrong-ordinal"} {
		t.Run(mode, func(t *testing.T) {
			root := t.TempDir()
			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()
			closes := 0
			if mode == "malformed" {
				if err := os.WriteFile(filepath.Join(root, "destination-0.complete"), []byte("wrong\n"), 0600); err != nil {
					t.Fatal(err)
				}
			} else {
				if mode == "wrong-ordinal" {
					_ = os.WriteFile(filepath.Join(root, "destination-1.complete"), []byte("complete\n"), 0600)
				}
				cancel()
			}
			err := finishLifecycleConnection(ctx, root, 0, true, func() error { closes++; return nil })
			if err == nil || closes != 1 {
				t.Fatalf("err=%v closes=%d", err, closes)
			}
			if _, err := os.Stat(filepath.Join(root, "connection-0.ack")); !os.IsNotExist(err) {
				t.Fatal("failed wait published success ack")
			}
		})
	}
}

func TestLifecycleCompletionDefaultAndCloseError(t *testing.T) {
	root := t.TempDir()
	want := errors.New("close failure")
	closes := 0
	err := finishLifecycleConnection(context.Background(), root, 3, false, func() error { closes++; return want })
	if !errors.Is(err, want) || closes != 1 {
		t.Fatalf("err=%v closes=%d", err, closes)
	}
	if _, err := os.Stat(filepath.Join(root, "connection-3.ack")); err != nil {
		t.Fatal(err)
	}
}

func TestLifecycleCompletionRejectsStaleMarker(t *testing.T) {
	root := t.TempDir()
	if err := os.WriteFile(filepath.Join(root, "destination-0.complete"), []byte("complete\n"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := requireFreshLifecycleCompletion(root, 0); err == nil {
		t.Fatal("stale marker accepted")
	}
	if err := requireFreshLifecycleCompletion(root, 1); err != nil {
		t.Fatal(err)
	}
}

func TestLifecycleCompletionConfigurationIsExplicitAndSequential(t *testing.T) {
	base := config{ReadinessPath: "ready", F75Package: "f75", LocalAttestationPackage: "local", SafePayload: "Z", BenchmarkSamples: 1, LifecycleAuthorityDir: "authority", LifecycleConnections: 50, LifecycleServices: 2, LifecycleStreamsPerService: 4, LifecycleConcurrent: true, LifecycleHoldForRelease: true, RuntimeSeriesPath: "runtime", RuntimeSamplingCadenceMS: 1000, LifecycleWaitDestinationComplete: true}
	if err := base.validate(); err != nil {
		t.Fatal(err)
	}
	for _, change := range []func(*config){
		func(c *config) { c.LifecycleAuthorityDir = "" },
		func(c *config) { c.LifecycleHoldForRelease = false },
		func(c *config) { c.LifecycleConnectionOffset = 1 },
		func(c *config) { c.BenchmarkSamples = 0 },
	} {
		invalid := base
		change(&invalid)
		if err := invalid.validate(); err == nil {
			t.Fatal("unsupported completion mode accepted")
		}
	}
}
