//go:build connector_development

package connector

import (
	"context"
	"errors"
	"sync"
)

var ErrCleanupPending = errors.New("connector fixture cleanup awaiting confirmation")

type cleanupAttempt struct {
	done     chan struct{}
	finished bool
	result   error
}

// CleanupPeer adapts an explicit asynchronous fixture backend to Peer.Close.
// begin must return promptly and invoke done only when the exact peer's close
// has completed (nil) or failed (error). This is not an authenticated receipt.
// It creates no worker, timer, socket or retry loop. Coordinator methods remain
// serialized by their caller; only completion callbacks and WaitCleanup may run
// concurrently. Callbacks never mutate Coordinator or its owned registration.
type CleanupPeer struct {
	Peer
	begin   func(done func(error))
	mu      sync.Mutex
	attempt *cleanupAttempt
}

func NewCleanupPeer(peer Peer, begin func(done func(error))) (*CleanupPeer, error) {
	if peer == nil || begin == nil {
		return nil, ErrInvalid
	}
	return &CleanupPeer{Peer: peer, begin: begin}, nil
}

// Close starts at most one attempt and reports its retained result. Pending or
// failed cleanup is an error so the existing owner retains its quota/handle.
func (p *CleanupPeer) Close() error { return p.start(false) }

// RetryCleanup is an explicit retry after a completed failure, never a timeout
// or cancelled wait. Old callbacks are bound to their private attempt identity.
func (p *CleanupPeer) RetryCleanup() error { return p.start(true) }

func (p *CleanupPeer) start(retry bool) error {
	p.mu.Lock()
	old := p.attempt
	if retry {
		if old == nil || !old.finished || old.result == nil {
			p.mu.Unlock()
			return ErrInvalid
		}
	} else if old != nil {
		result := p.resultLocked(old)
		p.mu.Unlock()
		return result
	}
	a := &cleanupAttempt{done: make(chan struct{})}
	p.attempt = a
	p.mu.Unlock()
	// The callback may complete synchronously; never hold the mutex over begin.
	p.begin(func(err error) {
		p.mu.Lock()
		defer p.mu.Unlock()
		if p.attempt != a || a.finished {
			return
		}
		a.result = err
		a.finished = true
		close(a.done)
	})
	p.mu.Lock()
	defer p.mu.Unlock()
	return p.resultLocked(a)
}

func (p *CleanupPeer) resultLocked(a *cleanupAttempt) error {
	if !a.finished {
		return ErrCleanupPending
	}
	return a.result
}

// WaitCleanup waits for notification on the current attempt. Cancelling or
// timing out this wait neither cancels the backend nor releases ownership.
// After completion the serialized owner calls Close again to apply the result.
func (p *CleanupPeer) WaitCleanup(ctx context.Context) error {
	if ctx == nil {
		return ErrInvalid
	}
	if err := ctx.Err(); err != nil {
		return err
	}
	p.mu.Lock()
	a := p.attempt
	p.mu.Unlock()
	if a == nil {
		return ErrInvalid
	}
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-a.done:
		p.mu.Lock()
		defer p.mu.Unlock()
		return p.resultLocked(a)
	}
}
