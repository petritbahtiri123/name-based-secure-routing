package forward

import (
	"bytes"
	"context"
	"net"
	"testing"
	"time"
)

func udpListener(t *testing.T) *net.UDPConn {
	t.Helper()
	conn, err := net.ListenUDP("udp4", &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1)})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = conn.Close() })
	return conn
}

func TestUDPOpaqueDatagramsAndPeerIsolation(t *testing.T) {
	upstream := udpListener(t)
	listener := udpListener(t)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	done := make(chan error, 1)
	go func() { done <- ServeUDP(ctx, listener, upstream.LocalAddr().(*net.UDPAddr), 16, time.Second) }()
	clients := []*net.UDPConn{udpListener(t), udpListener(t)}
	payloads := [][]byte{{0, 255, 1}, {128, 0, 2, 13, 10}}
	for i, client := range clients {
		_ = client.SetDeadline(time.Now().Add(2 * time.Second))
		if _, err := client.WriteToUDP(payloads[i], listener.LocalAddr().(*net.UDPAddr)); err != nil {
			t.Fatal(err)
		}
	}
	addresses := map[string]bool{}
	for range clients {
		_ = upstream.SetDeadline(time.Now().Add(2 * time.Second))
		buf := make([]byte, 65535)
		n, peer, err := upstream.ReadFromUDP(buf)
		if err != nil {
			t.Fatal(err)
		}
		addresses[peer.String()] = true
		if _, err = upstream.WriteToUDP(buf[:n], peer); err != nil {
			t.Fatal(err)
		}
	}
	if len(addresses) != 2 {
		t.Fatal("peers shared an upstream socket")
	}
	for i, client := range clients {
		buf := make([]byte, 65535)
		n, _, err := client.ReadFromUDP(buf)
		if err != nil || !bytes.Equal(buf[:n], payloads[i]) {
			t.Fatalf("datagram crossed peers or changed: %v", err)
		}
	}
	cancel()
	awaitStop(t, done)
	for address := range addresses {
		parsed, err := net.ResolveUDPAddr("udp4", address)
		if err != nil {
			t.Fatal(err)
		}
		rebound, err := net.ListenUDP("udp4", parsed)
		if err != nil {
			t.Fatalf("upstream socket retained after cancellation: %v", err)
		}
		_ = rebound.Close()
	}
}

func TestUDPCapacityAndIdleReclamation(t *testing.T) {
	upstream, listener := udpListener(t), udpListener(t)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	done := make(chan error, 1)
	go func() { done <- ServeUDP(ctx, listener, upstream.LocalAddr().(*net.UDPAddr), 16, 200*time.Millisecond) }()
	buffer := make([]byte, 8)
	for range 16 {
		client := udpListener(t)
		if _, err := client.WriteToUDP([]byte{1}, listener.LocalAddr().(*net.UDPAddr)); err != nil {
			t.Fatal(err)
		}
		_ = upstream.SetReadDeadline(time.Now().Add(time.Second))
		if _, _, err := upstream.ReadFromUDP(buffer); err != nil {
			t.Fatal(err)
		}
	}
	extra := udpListener(t)
	if _, err := extra.WriteToUDP([]byte{2}, listener.LocalAddr().(*net.UDPAddr)); err != nil {
		t.Fatal(err)
	}
	_ = upstream.SetReadDeadline(time.Now().Add(30 * time.Millisecond))
	if _, _, err := upstream.ReadFromUDP(buffer); err == nil {
		t.Fatal("capacity exceeded")
	}
	time.Sleep(350 * time.Millisecond)
	if _, err := extra.WriteToUDP([]byte{3}, listener.LocalAddr().(*net.UDPAddr)); err != nil {
		t.Fatal(err)
	}
	_ = upstream.SetReadDeadline(time.Now().Add(time.Second))
	n, _, err := upstream.ReadFromUDP(buffer)
	if err != nil || n != 1 || buffer[0] != 3 {
		t.Fatalf("idle peers were not reclaimed: %v", err)
	}
	cancel()
	awaitStop(t, done)
}

func TestUDPRejectsNonLoopbackAndUnboundedConfiguration(t *testing.T) {
	for _, upstream := range []*net.UDPAddr{nil, {IP: net.IPv4(10, 0, 0, 1), Port: 42}, {IP: net.IPv4(127, 0, 0, 1), Port: 0}} {
		ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
		if err := ServeUDP(ctx, udpListener(t), upstream, 16, time.Second); err == nil {
			t.Fatal("accepted invalid upstream")
		}
		cancel()
	}
	if err := ServeUDP(context.Background(), udpListener(t), &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1), Port: 42}, 17, time.Second); err == nil {
		t.Fatal("accepted excess peers")
	}
}
