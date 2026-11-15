package authority

import (
	"context"
	"io"
	"net"
	"net/url"
	"os"
	"syscall"
)

// TransportDiagnostic is a lossy error-class hint, not an authenticated result.
// It contains no URL, request, response, identity, key material, or raw error text.
type TransportDiagnostic uint8

const (
	TransportOther TransportDiagnostic = iota + 1
	TransportDeadline
	TransportCanceled
	TransportEOF
	TransportNetworkTimeout
	TransportNetworkOther
)

// classifyTransportDiagnostic inspects at most eight standard-library wrappers.
// It never invokes error methods (Error/Is/As/Unwrap/Timeout), including on custom
// errors. Unknown/deeper chains are intentionally less informative. This is not
// a wall-clock latency guarantee. As with the transport itself, error values must
// not be concurrently mutated by their producer.
func classifyTransportDiagnostic(err error) TransportDiagnostic {
	network := false
	for depth := 0; depth < 8; depth++ {
		switch err {
		case context.DeadlineExceeded:
			return TransportDeadline
		case context.Canceled:
			return TransportCanceled
		case io.EOF, io.ErrUnexpectedEOF:
			return TransportEOF
		case os.ErrDeadlineExceeded, syscall.ETIMEDOUT:
			return TransportNetworkTimeout
		}
		switch e := err.(type) {
		case *url.Error:
			if e == nil {
				return TransportOther
			}
			err = e.Err
		case *net.OpError:
			if e == nil {
				return TransportOther
			}
			network = true
			err = e.Err
		case *os.SyscallError:
			if e == nil {
				return TransportOther
			}
			err = e.Err
		default:
			if network {
				return TransportNetworkOther
			}
			return TransportOther
		}
	}
	return TransportOther
}

// Only channel delivery is nonblocking; no observer callback or worker is used.
// A nil/full/unread channel drops hints. Closing concurrently with sends is not
// supported (and is a data race); callers must wait until all requests finish.
// Sending to an already-closed channel is contained as a dropped hint.
func emitTransportDiagnostic(out chan<- TransportDiagnostic, err error) {
	if out == nil {
		return
	}
	defer func() { _ = recover() }()
	kind := classifyTransportDiagnostic(err)
	select {
	case out <- kind:
	default:
	}
}
