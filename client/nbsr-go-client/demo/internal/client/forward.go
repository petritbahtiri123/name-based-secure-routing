package client

import (
	"context"
	"errors"
	"io"
	"sync"
)

const forwardBufferBytes = 32 * 1024

type closeWriter interface{ CloseWrite() error }

// forwardBounded relays one application flow without buffering the complete
// request or response. Each direction has exactly one close owner.
func forwardBounded(ctx context.Context, application, secure io.ReadWriteCloser) error {
	type result struct{ err error }
	results := make(chan result, 2)
	copyDirection := func(destination io.Writer, source io.Reader) {
		buffer := make([]byte, forwardBufferBytes)
		_, err := io.CopyBuffer(destination, source, buffer)
		if writer, ok := destination.(closeWriter); ok {
			err = errors.Join(err, writer.CloseWrite())
		}
		results <- result{err: err}
	}
	go copyDirection(secure, application)
	go copyDirection(application, secure)
	var combined error
	done := ctx.Done()
	closed := false
	closeEndpoints := func() {
		if !closed {
			closed = true
			_ = application.Close()
			_ = secure.Close()
		}
	}
	for remaining := 2; remaining > 0; {
		select {
		case completed := <-results:
			remaining--
			combined = errors.Join(combined, completed.err)
			if completed.err != nil {
				closeEndpoints()
			}
		case <-done:
			combined = errors.Join(combined, ctx.Err())
			done = nil
			closeEndpoints()
		}
	}
	return combined
}

type onceReadWriteCloser struct {
	io.ReadWriteCloser
	once sync.Once
	err  error
}

func (value *onceReadWriteCloser) Close() error {
	value.once.Do(func() { value.err = value.ReadWriteCloser.Close() })
	return value.err
}

func (value *onceReadWriteCloser) CloseWrite() error {
	if writer, ok := value.ReadWriteCloser.(closeWriter); ok {
		return writer.CloseWrite()
	}
	return nil
}
