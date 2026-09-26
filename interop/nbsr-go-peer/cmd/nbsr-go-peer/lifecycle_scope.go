package main

import (
	"context"
	"sync"
	"sync/atomic"
)

type lifecycleCleanup struct {
	Ordinal        int   `json:"ordinal"`
	WorkersStarted int64 `json:"workers_started"`
	WorkersLive    int64 `json:"workers_live"`
	PeerCloseCalls int64 `json:"peer_close_calls"`
}

// lifecycleScope owns only benchmark workers and the peer close call, not QUIC internals.
type lifecycleScope struct {
	ctx        context.Context
	cancel     context.CancelFunc
	closeFn    func() error
	once       sync.Once
	closeErr   error
	workers    sync.WaitGroup
	live       atomic.Int64
	started    atomic.Int64
	closeCalls atomic.Int64
}

func newLifecycleScope(ctx context.Context, closeFn func() error) *lifecycleScope {
	child, cancel := context.WithCancel(ctx)
	return &lifecycleScope{ctx: child, cancel: cancel, closeFn: closeFn}
}

func (s *lifecycleScope) start(release <-chan struct{}, work func()) {
	s.workers.Add(1)
	s.live.Add(1)
	s.started.Add(1)
	go func() {
		defer s.workers.Done()
		defer s.live.Add(-1)
		select {
		case <-s.ctx.Done():
			return
		case <-release:
		}
		if s.ctx.Err() != nil {
			return
		}
		work()
	}()
}

func (s *lifecycleScope) closeTransport() error {
	s.once.Do(func() { s.closeCalls.Add(1); s.closeErr = s.closeFn() })
	return s.closeErr
}

func (s *lifecycleScope) close() error {
	s.cancel()
	err := s.closeTransport()
	s.workers.Wait()
	return err
}
