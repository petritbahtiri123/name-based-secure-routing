package forward

import (
	"context"
	"errors"
	"io"
	"net"
	"strconv"
	"sync"
	"time"
)

var errInvalidConfig = errors.New("invalid adapter configuration")

func loopbackTarget(address string) bool {
	host, port, err := net.SplitHostPort(address)
	if err != nil || host != "127.0.0.1" {
		return false
	}
	n, err := strconv.Atoi(port)
	return err == nil && n > 0 && n <= 65535 && strconv.Itoa(n) == port
}

// ServeTCP forwards opaque bytes to one exact loopback target. It owns listener.
func ServeTCP(ctx context.Context, listener net.Listener, upstream string, limit int, timeout time.Duration) error {
	if listener == nil || !loopbackTarget(upstream) || limit != 16 || timeout <= 0 || timeout > time.Minute {
		return errInvalidConfig
	}
	ctx, cancel := context.WithCancel(ctx)
	var workers sync.WaitGroup
	stop := context.AfterFunc(ctx, func() { _ = listener.Close() })
	defer func() { cancel(); _ = listener.Close(); stop(); workers.Wait() }()
	capacity := make(chan struct{}, limit)
	for {
		client, err := listener.Accept()
		if err != nil {
			if ctx.Err() != nil {
				return nil
			}
			return errors.New("adapter listener failed")
		}
		select {
		case capacity <- struct{}{}:
		default:
			_ = client.Close()
			continue
		}
		workers.Add(1)
		go func() {
			defer workers.Done()
			defer func() { <-capacity }()
			defer client.Close()
			stopClient := context.AfterFunc(ctx, func() { _ = client.Close() })
			defer stopClient()
			dialer := net.Dialer{Timeout: timeout}
			destination, err := dialer.DialContext(ctx, "tcp4", upstream)
			if err != nil {
				return
			}
			defer destination.Close()
			stopDestination := context.AfterFunc(ctx, func() { _ = destination.Close() })
			defer stopDestination()
			deadline := time.Now().Add(timeout)
			_ = client.SetDeadline(deadline)
			_ = destination.SetDeadline(deadline)
			finished := make(chan error, 2)
			copyDirection := func(dst, src net.Conn) {
				// Hide fast-path interfaces so each direction has exactly one bounded buffer.
				_, err := io.CopyBuffer(struct{ io.Writer }{dst}, struct{ io.Reader }{src}, make([]byte, 32*1024))
				if err == nil {
					if tcp, ok := dst.(*net.TCPConn); ok {
						err = tcp.CloseWrite()
					} else {
						err = dst.Close()
					}
				}
				finished <- err
			}
			go copyDirection(destination, client)
			go copyDirection(client, destination)
			if <-finished != nil {
				_ = client.Close()
				_ = destination.Close()
			}
			<-finished
		}()
	}
}
