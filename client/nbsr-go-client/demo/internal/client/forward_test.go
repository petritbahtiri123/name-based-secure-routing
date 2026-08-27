package client

import (
	"context"
	"errors"
	"io"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

type blockingStream struct {
	closed chan struct{}
	once   sync.Once
	closes atomic.Int32
}

func newBlockingStream() *blockingStream { return &blockingStream{closed: make(chan struct{})} }
func (stream *blockingStream) Read([]byte) (int, error) {
	<-stream.closed
	return 0, io.EOF
}
func (stream *blockingStream) Write(buffer []byte) (int, error) {
	select {
	case <-stream.closed:
		return 0, io.ErrClosedPipe
	default:
		return len(buffer), nil
	}
}
func (stream *blockingStream) Close() error {
	stream.closes.Add(1)
	stream.once.Do(func() { close(stream.closed) })
	return nil
}

func TestForwardBoundedCancellationClosesEachOwnerExactlyOnce(t *testing.T) {
	application := newBlockingStream()
	secure := newBlockingStream()
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() { done <- forwardBounded(ctx, application, secure) }()
	cancel()
	select {
	case err := <-done:
		if !errors.Is(err, context.Canceled) {
			t.Fatalf("forward error = %v", err)
		}
	case <-time.After(time.Second):
		t.Fatal("cancelled forwarding did not stop")
	}
	if application.closes.Load() != 1 || secure.closes.Load() != 1 {
		t.Fatalf("close counts application=%d secure=%d", application.closes.Load(), secure.closes.Load())
	}
}
