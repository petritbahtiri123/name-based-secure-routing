package client

import (
	"context"
	"errors"
	"io"
	"strings"
	"testing"
	"time"
)

type eofStream struct{ closes int }

func (s *eofStream) Read([]byte) (int, error)    { return 0, io.EOF }
func (s *eofStream) Write(p []byte) (int, error) { return len(p), nil }
func (s *eofStream) Close() error                { s.closes++; return nil }

type signaledHalfClose struct {
	*blockingStream
	half chan struct{}
}

func (s *signaledHalfClose) CloseWrite() error { close(s.half); return nil }
func TestCancellationAfterFirstDirectionEOF(t *testing.T) {
	app := &eofStream{}
	secure := &signaledHalfClose{newBlockingStream(), make(chan struct{})}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	done := make(chan error, 1)
	go func() { done <- forwardBounded(ctx, app, secure) }()
	select {
	case <-secure.half:
	case <-time.After(time.Second):
		cancel()
		_ = secure.Close()
		awaitForward(t, done)
		t.Fatal("half close not reached")
	}
	// Allow the completed direction to be consumed before cancellation.
	time.Sleep(30 * time.Millisecond)
	cancel()
	select {
	case err := <-done:
		if !errors.Is(err, context.Canceled) {
			t.Fatalf("error=%v", err)
		}
		if app.closes != 1 || secure.closes.Load() != 1 {
			t.Fatalf("close counts %d %d", app.closes, secure.closes.Load())
		}
	case <-time.After(150 * time.Millisecond):
		_ = secure.Close()
		awaitForward(t, done)
		t.Fatal("forwarding ignored cancellation after first direction EOF")
	}
}

func TestForwardNormalEOF(t *testing.T) {
	if err := forwardBounded(context.Background(), &eofStream{}, &eofStream{}); err != nil {
		t.Fatal(err)
	}
}

type failingReader struct{ eofStream }

func (*failingReader) Read([]byte) (int, error) { return 0, io.ErrUnexpectedEOF }
func TestForwardReadFailureClosesBlockedPeer(t *testing.T) {
	peer := newBlockingStream()
	done := make(chan error, 1)
	go func() { done <- forwardBounded(context.Background(), &failingReader{}, peer) }()
	select {
	case err := <-done:
		if !errors.Is(err, io.ErrUnexpectedEOF) {
			t.Fatalf("error=%v", err)
		}
	case <-time.After(time.Second):
		_ = peer.Close()
		awaitForward(t, done)
		t.Fatal("failed copy did not stop peer")
	}
	if peer.closes.Load() != 1 {
		t.Fatalf("peer closes=%d", peer.closes.Load())
	}
}

func awaitForward(t *testing.T, done <-chan error) error {
	t.Helper()
	select {
	case err := <-done:
		return err
	case <-time.After(time.Second):
		t.Fatal("worker cleanup exceeded deadline")
		return nil
	}
}

type gatedReader struct {
	*blockingStream
	release chan struct{}
}

func (s *gatedReader) Read([]byte) (int, error) { <-s.closed; <-s.release; return 0, io.EOF }
func TestCancellationDrainsBothWorkers(t *testing.T) {
	app := newBlockingStream()
	secure := &gatedReader{newBlockingStream(), make(chan struct{})}
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() { done <- forwardBounded(ctx, app, secure) }()
	cancel()
	select {
	case <-secure.closed:
	case <-time.After(time.Second):
		close(secure.release)
		_ = secure.Close()
		_ = app.Close()
		awaitForward(t, done)
		t.Fatal("close not reached")
	}
	select {
	case <-done:
		close(secure.release)
		t.Fatal("returned before second worker finished")
	case <-time.After(30 * time.Millisecond):
	}
	close(secure.release)
	if err := awaitForward(t, done); !errors.Is(err, context.Canceled) {
		t.Fatal(err)
	}
}

type responseStream struct {
	half     chan struct{}
	response io.Reader
}

func (s *responseStream) Read(p []byte) (int, error)  { <-s.half; return s.response.Read(p) }
func (s *responseStream) Write(p []byte) (int, error) { return len(p), nil }
func (s *responseStream) CloseWrite() error           { close(s.half); return nil }
func (s *responseStream) Close() error                { return nil }

type responseSink struct {
	eofStream
	received []byte
}

func (s *responseSink) Write(p []byte) (int, error) {
	s.received = append(s.received, p...)
	return len(p), nil
}
func TestHalfCloseAllowsReverseResponse(t *testing.T) {
	app := &responseSink{}
	secure := &responseStream{make(chan struct{}), strings.NewReader("response")}
	done := make(chan error, 1)
	go func() { done <- forwardBounded(context.Background(), app, secure) }()
	if err := awaitForward(t, done); err != nil {
		t.Fatal(err)
	}
	if string(app.received) != "response" {
		t.Fatalf("response=%q", app.received)
	}
	if app.closes != 0 {
		t.Fatal("normal half-close prematurely closed application")
	}
}
