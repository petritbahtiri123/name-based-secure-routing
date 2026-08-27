package client

import (
	"bufio"
	"bytes"
	"context"
	"crypto/sha256"
	"errors"
	"io"
	"net"
	"net/netip"
	"strings"
	"sync"
	"testing"
	"time"

	"nbsr.local/client/nbsr-go-client/internal/authority"
	"nbsr.local/client/nbsr-go-client/internal/resolution"
)

const backendBody = "hello from service-a through NBSR"

type recordingRouteOpener struct {
	mu     sync.Mutex
	routes []resolution.RouteContext
	err    error
	hold   chan net.Conn
	stream io.ReadWriteCloser
}

func (o *recordingRouteOpener) OpenVerifiedRoute(_ context.Context, mapped *resolution.MappedRoute) (io.ReadWriteCloser, error) {
	route, err := mapped.Context()
	if err != nil {
		return nil, err
	}
	o.mu.Lock()
	o.routes = append(o.routes, route)
	o.mu.Unlock()
	if o.err != nil {
		return nil, o.err
	}
	if o.stream != nil {
		return o.stream, nil
	}
	client, backend := net.Pipe()
	if o.hold != nil {
		o.hold <- backend
		return client, nil
	}
	go func() {
		defer backend.Close()
		request := make([]byte, len("GET / HTTP/1.1\r\nHost: ignored.example\r\n\r\n"))
		_, _ = io.ReadFull(backend, request)
		_, _ = io.WriteString(backend, "HTTP/1.1 200 OK\r\nContent-Length: 33\r\n\r\n"+backendBody)
	}()
	return client, nil
}

func TestProxyRequestTraversesResolutionAndPreSecureRouteRelay(t *testing.T) {
	opener := &recordingRouteOpener{}
	runtime, err := NewRuntime(RuntimeConfig{
		ListenAddress: "127.0.0.1:0", SharedSyntheticIP: netip.MustParseAddr("127.0.0.2"),
		NowUnix: 1_893_456_000, MaxConnections: 4, MaxRequestBytes: 4096,
	}, demoResolutionInput(), opener)
	if err != nil {
		t.Fatal(err)
	}
	defer runtime.Close()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go func() { _ = runtime.Serve(ctx) }()

	connection, err := net.DialTimeout("tcp", runtime.ProxyAddress(), time.Second)
	if err != nil {
		t.Fatal(err)
	}
	defer connection.Close()
	pipelined := "CONNECT service-a.nbsr.test:8080 HTTP/1.1\r\nHost: ignored.example\r\n\r\nGET / HTTP/1.1\r\nHost: ignored.example\r\n\r\n"
	if _, err = io.WriteString(connection, pipelined); err != nil {
		t.Fatal(err)
	}
	reader := bufio.NewReader(connection)
	status, err := reader.ReadString('\n')
	if err != nil || status != "HTTP/1.1 200 Connection Established\r\n" {
		t.Fatalf("CONNECT status = %q, %v", status, err)
	}
	for {
		line, readErr := reader.ReadString('\n')
		if readErr != nil {
			t.Fatal(readErr)
		}
		if line == "\r\n" {
			break
		}
	}
	response := make([]byte, len("HTTP/1.1 200 OK\r\nContent-Length: 33\r\n\r\n")+len(backendBody))
	_, err = io.ReadFull(reader, response)
	if err != nil || !bytes.Contains(response, []byte(backendBody)) {
		t.Fatalf("response = %q, %v", response, err)
	}
	if err := connection.Close(); err != nil {
		t.Fatal(err)
	}
	deadline := time.Now().Add(time.Second)
	for runtime.ProxyUsage().ActiveConnections != 0 && time.Now().Before(deadline) {
		time.Sleep(time.Millisecond)
	}
	opener.mu.Lock()
	defer opener.mu.Unlock()
	if len(opener.routes) != 1 || opener.routes[0].ServiceIdentity != "nbsr-demo-service-a-v1" || opener.routes[0].Intent.Port != 8080 {
		t.Fatalf("mapping-owned routes = %+v", opener.routes)
	}
	if runtime.FlowUsage().Entries != 0 || runtime.MappingReferences() != 0 || runtime.ProxyUsage().ActiveConnections != 0 {
		t.Fatalf("runtime did not return idle: %+v refs=%d %+v", runtime.FlowUsage(), runtime.MappingReferences(), runtime.ProxyUsage())
	}
}

func TestRuntimeReleasesProxyOwnershipOnRouteFailure(t *testing.T) {
	runtime := newTestRuntime(t, &recordingRouteOpener{err: errors.New("route denied")})
	connection := connectTestProxy(t, runtime)
	defer connection.Close()
	waitRuntimeIdle(t, runtime)
}

func TestRuntimeCancellationClosesActiveApplicationAndSecureStream(t *testing.T) {
	hold := make(chan net.Conn, 1)
	opener := &recordingRouteOpener{hold: hold}
	runtime := newTestRuntime(t, opener)
	connection := connectTestProxy(t, runtime)
	securePeer := <-hold
	defer securePeer.Close()
	if !runtime.cancelServing() {
		t.Fatal("serve cancellation unavailable")
	}
	_ = connection.SetReadDeadline(time.Now().Add(time.Second))
	if _, err := connection.Read(make([]byte, 1)); err == nil {
		t.Fatal("cancelled application connection remained open")
	}
	waitRuntimeIdle(t, runtime)
}

func TestRuntimeApplicationDisconnectDoesNotLeakTrackedConnection(t *testing.T) {
	hold := make(chan net.Conn, 1)
	runtime := newTestRuntime(t, &recordingRouteOpener{hold: hold})
	connection := connectTestProxy(t, runtime)
	securePeer := <-hold
	defer securePeer.Close()
	if err := connection.Close(); err != nil {
		t.Fatal(err)
	}
	waitRuntimeIdle(t, runtime)
}

func TestRuntimeCapacityRejectsOnlyExcessFlowAndRecovers(t *testing.T) {
	hold := make(chan net.Conn, 2)
	runtime := newTestRuntimeWithLimit(t, &recordingRouteOpener{hold: hold}, 1)
	first := connectTestProxy(t, runtime)
	firstSecure := <-hold
	defer firstSecure.Close()
	if got := runtime.ProxyUsage().ActiveConnections; got != 1 {
		t.Fatalf("active connections = %d, want 1", got)
	}
	excess, err := net.DialTimeout("tcp", runtime.ProxyAddress(), time.Second)
	if err != nil {
		t.Fatal(err)
	}
	_, _ = io.WriteString(excess, "CONNECT service-a.nbsr.test:8080 HTTP/1.1\r\n\r\n")
	_ = excess.SetReadDeadline(time.Now().Add(time.Second))
	if _, err := excess.Read(make([]byte, 1)); err == nil {
		t.Fatal("excess connection was not rejected")
	}
	_ = excess.Close()
	if !runtime.serving() || runtime.ProxyUsage().ActiveConnections != 1 {
		t.Fatalf("overload terminated server or disturbed active flow: serving=%v usage=%+v", runtime.serving(), runtime.ProxyUsage())
	}
	if runtime.ProxyUsage().RejectedConnections != 1 {
		t.Fatalf("overload event count = %+v", runtime.ProxyUsage())
	}
	if _, err := first.Write([]byte("x")); err != nil {
		t.Fatal(err)
	}
	_ = firstSecure.SetReadDeadline(time.Now().Add(time.Second))
	byteRead := make([]byte, 1)
	if _, err := io.ReadFull(firstSecure, byteRead); err != nil || byteRead[0] != 'x' {
		t.Fatalf("active flow failed after overload: %q %v", byteRead, err)
	}
	_ = first.Close()
	_ = firstSecure.Close()
	waitRuntimeIdle(t, runtime)
	third := connectTestProxy(t, runtime)
	thirdSecure := <-hold
	_ = third.Close()
	_ = thirdSecure.Close()
	waitRuntimeIdle(t, runtime)
	if runtime.ProxyUsage().ActiveConnections > 1 {
		t.Fatal("capacity bound exceeded")
	}
}

func TestRuntimeForwardingFailureReleasesProxyOwnership(t *testing.T) {
	stream := newFailingRouteStream()
	runtime := newTestRuntime(t, &recordingRouteOpener{stream: stream})
	connection := connectTestProxy(t, runtime)
	defer connection.Close()
	_, _ = connection.Write([]byte("request"))
	waitRuntimeIdle(t, runtime)
}

func TestRuntimeRejectsConcurrentServeAndClosesWithoutLateFlowStart(t *testing.T) {
	runtime := newTestRuntime(t, &recordingRouteOpener{err: errors.New("route denied")})
	if err := runtime.Serve(context.Background()); err == nil {
		t.Fatal("concurrent Serve succeeded")
	}

	connection, err := net.DialTimeout("tcp", runtime.ProxyAddress(), time.Second)
	if err != nil {
		t.Fatal(err)
	}
	closeDone := make(chan error, 1)
	go func() { closeDone <- runtime.Close() }()
	_, _ = io.WriteString(connection, "CONNECT service-a.nbsr.test:8080 HTTP/1.1\r\n\r\n")
	_ = connection.Close()
	select {
	case err = <-closeDone:
		if err != nil {
			t.Fatal(err)
		}
	case <-time.After(time.Second):
		t.Fatal("Close raced a late flow start")
	}
	if usage := runtime.ProxyUsage(); usage.ActiveConnections != 0 {
		t.Fatalf("active proxy connections after Close = %d", usage.ActiveConnections)
	}
}

type failingRouteStream struct {
	closed chan struct{}
	once   sync.Once
}

func newFailingRouteStream() *failingRouteStream {
	return &failingRouteStream{closed: make(chan struct{})}
}
func (stream *failingRouteStream) Read([]byte) (int, error) {
	<-stream.closed
	return 0, io.EOF
}
func (*failingRouteStream) Write([]byte) (int, error) { return 0, errors.New("forward failed") }
func (stream *failingRouteStream) Close() error {
	stream.once.Do(func() { close(stream.closed) })
	return nil
}

func newTestRuntime(t *testing.T, opener resolution.SecureRouteOpener) *Runtime {
	return newTestRuntimeWithLimit(t, opener, 4)
}

func newTestRuntimeWithLimit(t *testing.T, opener resolution.SecureRouteOpener, limit int) *Runtime {
	t.Helper()
	runtime, err := NewRuntime(RuntimeConfig{ListenAddress: "127.0.0.1:0", SharedSyntheticIP: netip.MustParseAddr("127.0.0.2"), NowUnix: 1_893_456_000, MaxConnections: limit, MaxRequestBytes: 4096}, demoResolutionInput(), opener)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = runtime.Close() })
	ctx := context.Background()
	go func() { _ = runtime.Serve(ctx) }()
	deadline := time.Now().Add(time.Second)
	for !runtime.serving() && time.Now().Before(deadline) {
		time.Sleep(time.Millisecond)
	}
	return runtime
}

func connectTestProxy(t *testing.T, runtime *Runtime) net.Conn {
	t.Helper()
	connection, err := net.DialTimeout("tcp", runtime.ProxyAddress(), time.Second)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = io.WriteString(connection, "CONNECT service-a.nbsr.test:8080 HTTP/1.1\r\n\r\n"); err != nil {
		t.Fatal(err)
	}
	reader := bufio.NewReader(connection)
	for {
		line, readErr := reader.ReadString('\n')
		if readErr != nil {
			t.Fatal(readErr)
		}
		if line == "\r\n" {
			break
		}
	}
	return connection
}

func waitRuntimeIdle(t *testing.T, runtime *Runtime) {
	t.Helper()
	deadline := time.Now().Add(time.Second)
	for runtime.ProxyUsage().ActiveConnections != 0 && time.Now().Before(deadline) {
		time.Sleep(time.Millisecond)
	}
	if usage := runtime.ProxyUsage(); usage.ActiveConnections != 0 {
		t.Fatalf("proxy ownership leaked: %+v", usage)
	}
}

func demoResolutionInput() resolution.ResultInput {
	canonical := []byte("demo route intent for service-a.nbsr.test")
	intent := authority.RouteIntent{
		Canonical: canonical, Digest: authority.RouteIntentDigest(sha256.Sum256(canonical)), ServiceIdentity: "nbsr-demo-service-a-v1",
		SourceOperator: "source.operator", SourceEdge: "source.edge", TargetOperator: "destination.operator", TargetEdges: []string{"destination.edge"},
		Transport: "tcp", Port: 8080, RecordSequence: 1, PolicyHash: authority.PolicyDigest(sha256.Sum256([]byte("demo-policy-v1"))),
		RouteID: [16]byte{1}, LeaseID: [16]byte{2}, ExpiresAt: 1_893_456_300,
	}
	return resolution.ResultInput{PresentationName: strings.Clone("service-a.nbsr.test"), ServiceIdentity: intent.ServiceIdentity, Intent: intent, RecordExpiresAt: 1_893_456_300}
}
