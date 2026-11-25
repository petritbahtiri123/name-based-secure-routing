//go:build connector_development

package connector

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"testing"
	"time"
)

// This is parent-only fixture IPC, not authenticated wire authority.
func reconnectAllowed(previous, next [16]byte, receipt []byte, locallyClean bool) bool {
	return locallyClean && previous != [16]byte{} && next != [16]byte{} && next != previous && bytes.Equal(receipt, previous[:])
}

func TestDevelopmentDockerReconnectProcess(t *testing.T) {
	if os.Getenv("NBSR_CONNECTOR_DOCKER_AUTO") != "1" || os.Getenv("NBSR_CONNECTOR_LOOPBACK") != "1" {
		t.Skip("explicit parent-only Docker reconnect worker")
	}
	if os.Getenv("NBSR_CONNECTOR_DOCKER_ENDPOINT") == "" {
		t.Fatal("explicit private endpoint required")
	}
	rawCycles := os.Getenv("NBSR_CONNECTOR_DOCKER_CYCLES")
	if rawCycles == "" {
		rawCycles = "1"
	}
	cycles, err := strconv.Atoi(rawCycles)
	if err != nil || cycles < 1 || cycles > 5 {
		t.Fatal("cycle count must be 1 through 5")
	}
	sessions := cycles + 1
	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGTERM, os.Interrupt)
	defer cancel()
	decoder := json.NewDecoder(io.LimitReader(os.Stdin, 256*1024))
	var previous [16]byte
	locallyClean := false
	for attempt := 1; attempt <= sessions; attempt++ {
		var cfg struct {
			loopConfig
			PreviousCleanupSession []byte
		}
		if decoder.Decode(&cfg) != nil || cfg.Case != "docker_hold" {
			t.Fatal("invalid private reconnect fixture")
		}
		env, err := Decode(ALPN, cfg.Request)
		if err != nil {
			t.Fatal("invalid request fixture")
		}
		if attempt > 1 {
			if !reconnectAllowed(previous, env.SessionID, cfg.PreviousCleanupSession, locallyClean) {
				t.Fatal("prior cleanup not confirmed or session not fresh")
			}
			fmt.Printf("NBSR_CONNECTOR_RECONNECT_GATE attempt=%d prior_cleanup_confirmed=true\n", attempt)
		}
		locallyClean = false
		// No new socket/coordinator is created until the prior cleanup gate passes.
		p, err := loopDial(cfg.loopConfig)
		if err != nil {
			t.Fatal("reconnect dial failed")
		}
		defer func() {
			if p.Close() != nil {
				t.Error("deferred reconnect socket cleanup failed")
			}
		}()
		expected := sha256.Sum256(cfg.ServerKey)
		c, err := NewCoordinator(&fixtureClock{now: 100}, loopAuthority{expected, env.Body}, expected, env.SessionID, env.Body)
		if err != nil || c.Connect(loopDialer{p}) != nil || c.Begin(env.Body) != nil || c.Owner() == nil {
			t.Fatal("reconnect registration failed")
		}
		fmt.Printf("NBSR_CONNECTOR_ACCEPTED attempt=%d synthetic_authority=true\n", attempt)
		if attempt < sessions {
			select {
			case <-p.conn.Context().Done():
			case <-ctx.Done():
				t.Fatal("unexpected process stop before reconnect")
			case <-time.After(30 * time.Second):
				t.Fatal("network failure not observed")
			}
		} else {
			select {
			case <-ctx.Done():
			case <-time.After(30 * time.Second):
				t.Fatal("final stop not observed")
			}
		}
		if c.Close() != nil || c.Owner() != nil || !p.closed {
			t.Fatal("local cleanup unconfirmed; replacement forbidden")
		}
		previous = env.SessionID
		locallyClean = true
		fmt.Printf("NBSR_CONNECTOR_SESSION_CLEANED attempt=%d owner_count=0\n", attempt)
	}
	fmt.Println("NBSR_CONNECTOR_CLOSED owner_count=0")
}

func TestDockerReconnectGate(t *testing.T) {
	old, next := [16]byte{1}, [16]byte{2}
	if !reconnectAllowed(old, next, old[:], true) {
		t.Fatal("confirmed fresh session rejected")
	}
	for _, test := range []struct {
		previous, next [16]byte
		receipt        []byte
		clean          bool
	}{
		{old, next, old[:], false},
		{old, next, nil, true},
		{old, next, next[:], true},
		{old, old, old[:], true},
		{old, [16]byte{}, old[:], true},
		{[16]byte{}, next, make([]byte, 16), true},
	} {
		if reconnectAllowed(test.previous, test.next, test.receipt, test.clean) {
			t.Fatal("unconfirmed, stale or reused session accepted")
		}
	}
}
