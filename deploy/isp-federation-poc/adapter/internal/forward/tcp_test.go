package forward

import (
	"bytes"
	"context"
	"io"
	"net"
	"testing"
	"time"
)

func tcpListener(t *testing.T) net.Listener {
	t.Helper()
	l, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = l.Close() })
	return l
}

func awaitStop(t *testing.T, done <-chan error) {
	t.Helper()
	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("adapter did not stop")
	}
}

func TestTCPOpaqueBytesAndHalfClose(t *testing.T) {
	upstream := tcpListener(t)
	payload := []byte{0, 255, 13, 10, 128, 1, 2}
	echo := make(chan error, 1)
	go func() {
		conn, err := upstream.Accept()
		if err != nil {
			echo <- err
			return
		}
		defer conn.Close()
		_ = conn.SetDeadline(time.Now().Add(2 * time.Second))
		got, err := io.ReadAll(io.LimitReader(conn, 4097))
		if err == nil && !bytes.Equal(got, payload) {
			err = io.ErrUnexpectedEOF
		}
		if err == nil {
			_, err = conn.Write(got)
		}
		echo <- err
	}()
	listener := tcpListener(t)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	done := make(chan error, 1)
	go func() { done <- ServeTCP(ctx, listener, upstream.Addr().String(), 16, 2*time.Second) }()
	conn, err := net.DialTCP("tcp4", nil, listener.Addr().(*net.TCPAddr))
	if err != nil {
		t.Fatal(err)
	}
	defer conn.Close()
	_ = conn.SetDeadline(time.Now().Add(2 * time.Second))
	if _, err = conn.Write(payload); err != nil {
		t.Fatal(err)
	}
	if err = conn.CloseWrite(); err != nil {
		t.Fatal(err)
	}
	got, err := io.ReadAll(conn)
	if err != nil || !bytes.Equal(got, payload) {
		t.Fatalf("opaque response changed or failed: %v", err)
	}
	if err = <-echo; err != nil {
		t.Fatal(err)
	}
	cancel()
	awaitStop(t, done)
}

func TestTCPCancellationClosesActiveConnections(t *testing.T) {
	upstream := tcpListener(t)
	listener := tcpListener(t)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	done := make(chan error, 1)
	go func() { done <- ServeTCP(ctx, listener, upstream.Addr().String(), 16, time.Second) }()
	client, err := net.Dial("tcp4", listener.Addr().String())
	if err != nil {
		t.Fatal(err)
	}
	defer client.Close()
	cancel()
	awaitStop(t, done)
	_ = client.SetReadDeadline(time.Now().Add(time.Second))
	if _, err := client.Read(make([]byte, 1)); err == nil {
		t.Fatal("cancelled connection remained readable")
	}
}

func TestTCPRejectsNonLiteralLoopbackAndCapacityChange(t *testing.T) {
	for _, address := range []string{"localhost:80", "127.0.0.2:80", "10.0.0.1:80", "127.0.0.1:0", "127.0.0.1:80,127.0.0.1:81"} {
		ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
		if err := ServeTCP(ctx, tcpListener(t), address, 16, time.Second); err == nil {
			t.Errorf("accepted upstream %q", address)
		}
		cancel()
	}
	if err := ServeTCP(context.Background(), tcpListener(t), "127.0.0.1:80", 17, time.Second); err == nil {
		t.Fatal("accepted excess capacity")
	}
}
