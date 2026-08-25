package proxy

import (
	"context"
	"io"
	"net"
	"runtime"
	"testing"
	"time"

	"nbsr.local/client/nbsr-go-client/internal/adapter"
	"nbsr.local/client/nbsr-go-client/internal/resolution"
)

func TestProxyDisconnectChurnReturnsToSteadyState(t *testing.T) {
	const iterations = 300
	start := time.Now()
	runtime.GC()
	beforeGoroutines := runtime.NumGoroutine()
	var before, after runtime.MemStats
	runtime.ReadMemStats(&before)

	flows, err := resolution.NewFlowStore(resolution.FlowLimits{MaxEntries: 1, MaxBytes: 16})
	if err != nil {
		t.Fatal(err)
	}
	correlator, err := NewCorrelator(staticResolver{"api.example": 7}, flows)
	if err != nil {
		t.Fatal(err)
	}
	for iteration := 0; iteration < iterations; iteration++ {
		serverSide, clientSide := net.Pipe()
		server, err := NewServer(&oneListener{connection: serverSide}, correlator, ServerLimits{MaxConnections: 1, MaxRequestBytes: 1024, HandshakeTimeout: time.Second})
		if err != nil {
			t.Fatal(err)
		}
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
		if err := captured.Downstream.Close(); err != nil {
			t.Fatal(err)
		}
		_ = clientSide.Close()
		if usage := server.Usage(); usage.ActiveConnections != 0 {
			t.Fatalf("iteration %d proxy usage = %+v", iteration, usage)
		}
		if usage := flows.Usage(); usage.Entries != 0 || usage.Bytes != 0 {
			t.Fatalf("iteration %d flow usage = %+v", iteration, usage)
		}
	}

	runtime.GC()
	runtime.Gosched()
	afterGoroutines := runtime.NumGoroutine()
	runtime.ReadMemStats(&after)
	if afterGoroutines > beforeGoroutines+2 {
		t.Fatalf("goroutines grew from %d to %d", beforeGoroutines, afterGoroutines)
	}
	t.Logf("workload=proxy_disconnect iterations=%d concurrency=1 duration=%s goroutines_before=%d goroutines_after=%d heap_before=%d heap_after=%d gc_cycles=%d flow_entries=0 active_connections=0 failures=0",
		iterations, time.Since(start), beforeGoroutines, afterGoroutines, before.HeapAlloc, after.HeapAlloc, after.NumGC-before.NumGC)
}
