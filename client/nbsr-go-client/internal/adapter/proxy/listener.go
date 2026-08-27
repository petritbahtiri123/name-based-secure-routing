package proxy

import (
	"bufio"
	"context"
	"errors"
	"io"
	"net"
	"sync"
	"sync/atomic"
	"time"

	"nbsr.local/client/nbsr-go-client/internal/adapter"
)

var ErrInvalidServerLimits = errors.New("invalid proxy server limits")
var ErrConnectionCapacity = errors.New("proxy connection capacity exhausted")

type ServerLimits struct {
	MaxConnections   int
	MaxRequestBytes  int64
	HandshakeTimeout time.Duration
}

type Server struct {
	listener   net.Listener
	correlator *Correlator
	limits     ServerLimits
	active     chan struct{}
	rejected   atomic.Uint64
}

// ServerUsage reports aggregate proxy connection use without peer details.
type ServerUsage struct {
	ActiveConnections, MaxConnections int
	RejectedConnections               uint64
}

func NewServer(listener net.Listener, correlator *Correlator, limits ServerLimits) (*Server, error) {
	if listener == nil || correlator == nil || limits.MaxConnections <= 0 || limits.MaxRequestBytes <= 0 || limits.HandshakeTimeout <= 0 {
		return nil, ErrInvalidServerLimits
	}
	return &Server{
		listener: listener, correlator: correlator, limits: limits,
		active: make(chan struct{}, limits.MaxConnections),
	}, nil
}

func (server *Server) Accept(ctx context.Context) (adapter.CapturedFlow, error) {
	if err := ctx.Err(); err != nil {
		return adapter.CapturedFlow{}, err
	}
	connection, err := server.listener.Accept()
	if err != nil {
		return adapter.CapturedFlow{}, err
	}
	select {
	case server.active <- struct{}{}:
	case <-ctx.Done():
		_ = connection.Close()
		return adapter.CapturedFlow{}, ctx.Err()
	default:
		_ = connection.Close()
		for current := server.rejected.Load(); current != ^uint64(0) && !server.rejected.CompareAndSwap(current, current+1); current = server.rejected.Load() {
		}
		return adapter.CapturedFlow{}, ErrConnectionCapacity
	}
	release := func() { <-server.active }
	if err := connection.SetDeadline(time.Now().Add(server.limits.HandshakeTimeout)); err != nil {
		_ = connection.Close()
		release()
		return adapter.CapturedFlow{}, err
	}
	target, downstream, success, err := server.readTarget(connection)
	if err != nil {
		_ = connection.Close()
		release()
		return adapter.CapturedFlow{}, err
	}
	if _, err := connection.Write(success); err != nil {
		_ = connection.Close()
		release()
		return adapter.CapturedFlow{}, err
	}
	if err := connection.SetDeadline(time.Time{}); err != nil {
		_ = connection.Close()
		release()
		return adapter.CapturedFlow{}, err
	}
	flowContext, err := server.correlator.Bind(target)
	if err != nil {
		_ = connection.Close()
		release()
		return adapter.CapturedFlow{}, err
	}
	return adapter.CapturedFlow{
		Context: flowContext, Transport: "tcp", Port: target.Port,
		Downstream: &trackedConnection{Conn: downstream, release: func() {
			server.correlator.release(flowContext.LocalFlowID)
			release()
		}},
	}, nil
}

func (server *Server) readTarget(connection net.Conn) (Target, net.Conn, []byte, error) {
	readerSize := server.limits.MaxRequestBytes
	if readerSize > 4096 {
		readerSize = 4096
	}
	reader := bufio.NewReaderSize(connection, int(readerSize))
	first, err := reader.Peek(1)
	if err != nil {
		return Target{}, nil, nil, ErrInvalidProxyRequest
	}
	if first[0] != 5 {
		target, err := ParseHTTPConnect(reader, server.limits.MaxRequestBytes)
		if err != nil {
			return Target{}, nil, nil, err
		}
		return target, &bufferedConnection{Conn: connection, reader: reader}, []byte("HTTP/1.1 200 Connection Established\r\n\r\n"), nil
	}

	var greeting [2]byte
	if _, err := io.ReadFull(reader, greeting[:]); err != nil || greeting[0] != 5 || greeting[1] == 0 {
		return Target{}, nil, nil, ErrInvalidProxyRequest
	}
	methods := make([]byte, int(greeting[1]))
	if int64(len(methods)+2) > server.limits.MaxRequestBytes {
		return Target{}, nil, nil, ErrInvalidProxyRequest
	}
	if _, err := io.ReadFull(reader, methods); err != nil || !contains(methods, 0) {
		return Target{}, nil, nil, ErrInvalidProxyRequest
	}
	if _, err := connection.Write([]byte{5, 0}); err != nil {
		return Target{}, nil, nil, err
	}
	var prefix [5]byte
	if _, err := io.ReadFull(reader, prefix[:]); err != nil || prefix[0] != 5 || prefix[1] != 1 || prefix[2] != 0 || prefix[3] != 3 || prefix[4] == 0 {
		return Target{}, nil, nil, ErrInvalidProxyRequest
	}
	rest := make([]byte, int(prefix[4])+2)
	if int64(len(methods)+len(prefix)+len(rest)+2) > server.limits.MaxRequestBytes {
		return Target{}, nil, nil, ErrInvalidProxyRequest
	}
	if _, err := io.ReadFull(reader, rest); err != nil {
		return Target{}, nil, nil, ErrInvalidProxyRequest
	}
	wire := append(prefix[:], rest...)
	target, err := ParseSOCKS5Connect(wire)
	if err != nil {
		return Target{}, nil, nil, err
	}
	return target, &bufferedConnection{Conn: connection, reader: reader}, []byte{5, 0, 0, 1, 0, 0, 0, 0, 0, 0}, nil
}

func contains(values []byte, wanted byte) bool {
	for _, value := range values {
		if value == wanted {
			return true
		}
	}
	return false
}

func (server *Server) Close() error { return server.listener.Close() }

func (server *Server) Usage() ServerUsage {
	return ServerUsage{ActiveConnections: len(server.active), MaxConnections: cap(server.active), RejectedConnections: server.rejected.Load()}
}

type trackedConnection struct {
	net.Conn
	once    sync.Once
	release func()
}

type bufferedConnection struct {
	net.Conn
	reader io.Reader
}

type closeWriter interface{ CloseWrite() error }

func (connection *bufferedConnection) Read(buffer []byte) (int, error) {
	return connection.reader.Read(buffer)
}

func (connection *bufferedConnection) CloseWrite() error {
	if writer, ok := connection.Conn.(closeWriter); ok {
		return writer.CloseWrite()
	}
	return net.ErrClosed
}

func (connection *trackedConnection) CloseWrite() error {
	if writer, ok := connection.Conn.(closeWriter); ok {
		return writer.CloseWrite()
	}
	return net.ErrClosed
}

func (connection *trackedConnection) Close() error {
	err := connection.Conn.Close()
	connection.once.Do(connection.release)
	return err
}

var _ adapter.FlowSource = (*Server)(nil)
