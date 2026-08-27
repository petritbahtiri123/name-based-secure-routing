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
	var first result
	closed := false
	select {
	case first = <-results:
	case <-ctx.Done():
		_ = application.Close()
		_ = secure.Close()
		closed = true
		first.err = ctx.Err()
	}
	if first.err != nil && !closed {
		_ = application.Close()
		_ = secure.Close()
	}
	second := <-results
	return errors.Join(first.err, second.err)
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
