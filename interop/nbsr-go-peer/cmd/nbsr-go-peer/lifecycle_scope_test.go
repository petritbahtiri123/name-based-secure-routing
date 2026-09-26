package main

import (
	"context"
	"errors"
	"sync/atomic"
	"testing"
	"time"
)

func TestLifecycleScopeCancelsUnreleasedWorkers(t *testing.T) {
	var closes, ran atomic.Int32
	s := newLifecycleScope(context.Background(), func() error { closes.Add(1); return nil })
	gate := make(chan struct{})
	for range 64 {
		s.start(gate, func() { ran.Add(1) })
	}
	done := make(chan error, 1)
	go func() { done <- s.close() }()
	select {
	case err := <-done:
		if err != nil {
			t.Fatal(err)
		}
	case <-time.After(time.Second):
		t.Fatal("unreleased workers leaked")
	}
	if ran.Load() != 0 || closes.Load() != 1 || s.live.Load() != 0 {
		t.Fatal("cleanup ownership mismatch")
	}
	if err := s.close(); err != nil || closes.Load() != 1 {
		t.Fatal("duplicate close")
	}
}

func TestLifecycleScopeClosesPeerBeforeJoiningBlockedWorker(t *testing.T) {
	unblocked := make(chan struct{})
	started := make(chan struct{})
	expected := errors.New("close failure")
	s := newLifecycleScope(context.Background(), func() error { close(unblocked); return expected })
	gate := make(chan struct{})
	close(gate)
	s.start(gate, func() { close(started); <-unblocked })
	<-started
	if err := s.close(); !errors.Is(err, expected) {
		t.Fatal("close error suppressed")
	}
	if s.live.Load() != 0 {
		t.Fatal("worker not joined")
	}
}

func TestLifecycleScopeReleasedWorkersCompleteAndCount(t *testing.T) {
	var ran atomic.Int32
	s := newLifecycleScope(context.Background(), func() error { return nil })
	gate := make(chan struct{})
	for range 64 {
		s.start(gate, func() { ran.Add(1) })
	}
	close(gate)
	s.workers.Wait()
	if err := s.close(); err != nil {
		t.Fatal(err)
	}
	if ran.Load() != 64 || s.started.Load() != 64 || s.live.Load() != 0 || s.closeCalls.Load() != 1 {
		t.Fatal("incorrect successful ownership")
	}
}

func TestLifecycleScopeCanceledParentDoesNotSendPayload(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	s := newLifecycleScope(ctx, func() error { return nil })
	gate := make(chan struct{})
	close(gate)
	var ran atomic.Int32
	s.start(gate, func() { ran.Add(1) })
	if err := s.close(); err != nil {
		t.Fatal(err)
	}
	if ran.Load() != 0 {
		t.Fatal("payload after cancellation")
	}
}
