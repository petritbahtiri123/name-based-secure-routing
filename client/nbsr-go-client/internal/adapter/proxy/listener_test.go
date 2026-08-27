package proxy

import (
	"bufio"
	"context"
	"errors"
	"io"
	"net"
	"testing"
	"time"

	"nbsr.local/client/nbsr-go-client/internal/adapter"
	"nbsr.local/client/nbsr-go-client/internal/resolution"
)

type oneListener struct{ connection net.Conn }

type halfCloseNetConn struct {
	net.Conn
	closeWriteCalls int
	closeCalls      int
	closeWriteErr   error
}

func (connection *halfCloseNetConn) CloseWrite() error {
	connection.closeWriteCalls++
	return connection.closeWriteErr
}
func (connection *halfCloseNetConn) Close() error {
	connection.closeCalls++
	return nil
}

func (listener *oneListener) Accept() (net.Conn, error) {
	connection := listener.connection
	listener.connection = nil
	if connection == nil {
		return nil, net.ErrClosed
	}
	return connection, nil
}

func TestServerPreservesPayloadBufferedWithHTTPConnect(t *testing.T) {
	serverSide, clientSide := net.Pipe()
	defer clientSide.Close()
	flows, _ := resolution.NewFlowStore(resolution.FlowLimits{MaxEntries: 1, MaxBytes: 16})
	correlator, _ := NewCorrelator(staticResolver{"api.example": 7}, flows)
	server, _ := NewServer(&oneListener{connection: serverSide}, correlator, ServerLimits{MaxConnections: 1, MaxRequestBytes: 1024, HandshakeTimeout: time.Second})
	capturedResult := make(chan []byte, 1)
	go func() {
		captured, err := server.Accept(context.Background())
		if err != nil {
			capturedResult <- nil
			return
		}
		payload := make([]byte, 5)
		_, _ = io.ReadFull(captured.Downstream, payload)
		_ = captured.Downstream.Close()
		capturedResult <- payload
	}()
	if _, err := clientSide.Write([]byte("CONNECT api.example:443 HTTP/1.1\r\n\r\nhello")); err != nil {
		t.Fatal(err)
	}
	response := make([]byte, len("HTTP/1.1 200 Connection Established\r\n\r\n"))
	if _, err := io.ReadFull(clientSide, response); err != nil {
		t.Fatal(err)
	}
	select {
	case payload := <-capturedResult:
		if string(payload) != "hello" {
			t.Fatalf("payload = %q, want hello", payload)
		}
	case <-time.After(time.Second):
		t.Fatal("buffered application payload was lost")
	}
}

func TestProxyConnectionWrappersPreserveHalfCloseCapability(t *testing.T) {
	wantErr := errors.New("half close failed")
	base := &halfCloseNetConn{closeWriteErr: wantErr}
	buffered := &bufferedConnection{Conn: base, reader: base}
	tracked := &trackedConnection{Conn: buffered, release: func() {}}
	if err := buffered.CloseWrite(); !errors.Is(err, wantErr) {
		t.Fatalf("buffered CloseWrite error = %v", err)
	}
	if err := tracked.CloseWrite(); !errors.Is(err, wantErr) {
		t.Fatalf("tracked CloseWrite error = %v", err)
	}
	if base.closeWriteCalls != 2 || base.closeCalls != 0 {
		t.Fatalf("underlying calls: CloseWrite=%d Close=%d", base.closeWriteCalls, base.closeCalls)
	}
}

func TestPendingAcceptDoesNotCountAsActiveConnection(t *testing.T) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	flows, _ := resolution.NewFlowStore(resolution.FlowLimits{MaxEntries: 1, MaxBytes: 16})
	correlator, _ := NewCorrelator(staticResolver{"api.example": 7}, flows)
	server, _ := NewServer(listener, correlator, ServerLimits{MaxConnections: 1, MaxRequestBytes: 1024, HandshakeTimeout: time.Second})
	done := make(chan error, 1)
	go func() {
		_, acceptErr := server.Accept(context.Background())
		done <- acceptErr
	}()
	time.Sleep(25 * time.Millisecond)
	if got := server.Usage().ActiveConnections; got != 0 {
		t.Fatalf("pending accept counted as active: %d", got)
	}
	_ = server.Close()
	<-done
}
func (*oneListener) Close() error   { return nil }
func (*oneListener) Addr() net.Addr { return &net.TCPAddr{} }

func TestServerAcceptsHTTPConnectAndReturnsCapturedFlow(t *testing.T) {
	serverSide, clientSide := net.Pipe()
	defer clientSide.Close()
	flows, _ := resolution.NewFlowStore(resolution.FlowLimits{MaxEntries: 1, MaxBytes: 16})
	correlator, _ := NewCorrelator(staticResolver{"api.example": 7}, flows)
	server, err := NewServer(&oneListener{connection: serverSide}, correlator, ServerLimits{MaxConnections: 1, MaxRequestBytes: 1024, HandshakeTimeout: time.Second})
	if err != nil {
		t.Fatal(err)
	}
	result := make(chan error, 1)
	go func() {
		captured, err := server.Accept(context.Background())
		if err == nil {
			if captured.Context.MappingID != 7 || captured.Port != 443 || captured.Transport != "tcp" {
				t.Errorf("captured = %+v", captured)
			}
			_ = captured.Downstream.Close()
		}
		result <- err
	}()
	if _, err := clientSide.Write([]byte("CONNECT api.example:443 HTTP/1.1\r\n\r\n")); err != nil {
		t.Fatal(err)
	}
	response, err := bufio.NewReader(clientSide).ReadString('\n')
	if err != nil || response != "HTTP/1.1 200 Connection Established\r\n" {
		t.Fatalf("response = %q, %v", response, err)
	}
	select {
	case err := <-result:
		if err != nil {
			t.Fatal(err)
		}
	case <-time.After(time.Second):
		t.Fatal("server did not return captured flow")
	}
}

func TestCapturedConnectionCloseReleasesUnconsumedFlowContext(t *testing.T) {
	serverSide, clientSide := net.Pipe()
	defer clientSide.Close()
	flows, _ := resolution.NewFlowStore(resolution.FlowLimits{MaxEntries: 1, MaxBytes: 16})
	correlator, _ := NewCorrelator(staticResolver{"api.example": 7}, flows)
	server, _ := NewServer(&oneListener{connection: serverSide}, correlator, ServerLimits{MaxConnections: 1, MaxRequestBytes: 1024, HandshakeTimeout: time.Second})
	result := make(chan adapter.CapturedFlow, 1)
	go func() {
		captured, _ := server.Accept(context.Background())
		result <- captured
	}()
	if _, err := clientSide.Write([]byte("CONNECT api.example:443 HTTP/1.1\r\n\r\n")); err != nil {
		t.Fatal(err)
	}
	response := make([]byte, len("HTTP/1.1 200 Connection Established\r\n\r\n"))
	if _, err := io.ReadFull(clientSide, response); err != nil {
		t.Fatal(err)
	}
	captured := <-result
	if got := server.Usage(); got != (ServerUsage{ActiveConnections: 1, MaxConnections: 1}) {
		t.Fatalf("active usage = %+v", got)
	}
	if err := captured.Downstream.Close(); err != nil {
		t.Fatal(err)
	}
	if _, err := flows.Consume(captured.Context.LocalFlowID); !errors.Is(err, resolution.ErrUnknownFlow) {
		t.Fatalf("flow after disconnect = %v, want ErrUnknownFlow", err)
	}
	if got := server.Usage(); got.ActiveConnections != 0 {
		t.Fatalf("usage after disconnect = %+v", got)
	}
}

func TestServerRejectsWhenConnectionCapacityIsReserved(t *testing.T) {
	serverSide, clientSide := net.Pipe()
	defer clientSide.Close()
	flows, _ := resolution.NewFlowStore(resolution.FlowLimits{MaxEntries: 2, MaxBytes: 32})
	correlator, _ := NewCorrelator(staticResolver{"api.example": 7}, flows)
	server, _ := NewServer(&oneListener{connection: serverSide}, correlator, ServerLimits{MaxConnections: 1, MaxRequestBytes: 1024, HandshakeTimeout: time.Second})
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err := server.Accept(ctx); err == nil {
		t.Fatal("cancelled accept succeeded")
	}
}
