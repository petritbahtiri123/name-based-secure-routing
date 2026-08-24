package main

import (
	"bufio"
	"encoding/json"
	"os"
	"runtime"
	"sync/atomic"
	"testing"
	"time"

	"nbsr.local/interop/nbsr-go-peer/internal/perfclock"
)

func TestLifecycleConfigurationRequiresBoundedIndependentServices(t *testing.T) {
	valid := config{ReadinessPath: "ready", F75Package: "f75", LocalAttestationPackage: "local", SafePayload: "Z", LifecycleAuthorityDir: "authority", LifecycleConnections: 1, LifecycleServices: 20, LifecycleStreamsPerService: 64}
	if err := valid.validate(); err != nil {
		t.Fatalf("valid lifecycle configuration rejected: %v", err)
	}
	invalid := valid
	invalid.LifecycleServices = 33
	if err := invalid.validate(); err == nil {
		t.Fatal("service count above frozen protocol limit accepted")
	}
	valid.LifecycleServices = 32
	if err := valid.validate(); err != nil {
		t.Fatalf("frozen 32-channel session limit rejected: %v", err)
	}
	invalid = valid
	invalid.LifecycleConnections = 0
	if err := invalid.validate(); err == nil {
		t.Fatal("zero lifecycle connections accepted")
	}
	invalid = valid
	invalid.LifecycleStreamsPerService = 65
	if err := invalid.validate(); err == nil {
		t.Fatal("stream count above frozen per-channel limit accepted")
	}
	valid.LifecycleConcurrent = true
	if err := valid.validate(); err != nil {
		t.Fatalf("bounded concurrent lifecycle rejected: %v", err)
	}
}

func TestRuntimeSamplerPreservesCadenceAndProcessedRequestCount(t *testing.T) {
	path := t.TempDir() + "/runtime.ndjson"
	var processed atomic.Uint64
	stop, err := startRuntimeSampler(path, 10*time.Millisecond, &processed)
	if err != nil {
		t.Fatal(err)
	}
	processed.Store(17)
	time.Sleep(35 * time.Millisecond)
	if err := stop(); err != nil {
		t.Fatal(err)
	}
	file, err := os.Open(path)
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	scanner := bufio.NewScanner(file)
	count := 0
	for scanner.Scan() {
		var sample goRuntimeSample
		if err := json.Unmarshal(scanner.Bytes(), &sample); err != nil {
			t.Fatal(err)
		}
		if sample.ProcessedRequests != 17 || sample.HeapSysBytes == 0 || sample.ObservedAtNS <= 0 {
			t.Fatalf("incomplete runtime sample: %+v", sample)
		}
		count++
	}
	if err := scanner.Err(); err != nil {
		t.Fatal(err)
	}
	if count < 2 {
		t.Fatalf("runtime samples disappeared: %d", count)
	}
}

func TestLifecycleIDsAreDistinctAcrossServiceAuthorities(t *testing.T) {
	seenRequests := map[[16]byte]bool{}
	seenChannels := map[[16]byte]bool{}
	for index := 0; index < 20; index++ {
		request, channel, route := lifecycleIDs(index)
		if seenRequests[request] || seenChannels[channel] || request == channel || channel == route {
			t.Fatalf("authority identity collision at service %d", index)
		}
		seenRequests[request] = true
		seenChannels[channel] = true
	}
}

func TestPayloadMatrixAcceptsOneMiBAndRejectsLargerInput(t *testing.T) {
	base := config{ReadinessPath: "ready", F75Package: "f75", LocalAttestationPackage: "local", BenchmarkSamples: 1}
	base.SafePayload = string(make([]byte, 1<<20))
	if err := base.validate(); err != nil {
		t.Fatalf("one MiB payload rejected: %v", err)
	}
	base.SafePayload += "x"
	if err := base.validate(); err == nil {
		t.Fatal("payload above one MiB accepted")
	}
}

func TestOpenLoopOfferedRateMustBePositive(t *testing.T) {
	valid := config{ReadinessPath: "ready", F75Package: "f75", LocalAttestationPackage: "local", SafePayload: "Z", BenchmarkSamples: 1, OfferedRate: 100}
	if err := valid.validate(); err != nil {
		t.Fatalf("positive offered rate rejected: %v", err)
	}
	valid.OfferedRate = -1
	if err := valid.validate(); err == nil {
		t.Fatal("negative offered rate accepted")
	}
}

func TestStreamCreditProfileIsExactAndOperationsAreBounded(t *testing.T) {
	base := config{ReadinessPath: "ready", F75Package: "f75", LocalAttestationPackage: "local", SafePayload: "Z", BenchmarkSamples: 1, StreamCreditProfile: "nbsr-stream-credit-1"}
	if err := base.validate(); err != nil {
		t.Fatalf("approved stream-credit profile rejected: %v", err)
	}
	base.StreamCreditProfile = "nbsr-stream-credit-2"
	if err := base.validate(); err == nil {
		t.Fatal("unknown stream-credit profile accepted")
	}
	base.StreamCreditProfile = "nbsr-stream-credit-1"
	base.BenchmarkSamples = 80
	if err := base.validate(); err != nil {
		t.Fatalf("bounded refill interop rejected: %v", err)
	}
	base.BenchmarkSamples = 129
	if err := base.validate(); err == nil {
		t.Fatal("stream-credit interop accepted more than two bounded windows")
	}
}

func TestCreditMutationsAreNotClassifiedAsRouteMutations(t *testing.T) {
	for _, mutation := range []string{"malformed_credit_preface", "credit_profile_mismatch", "credit_legacy_downgrade"} {
		if !isCreditMutation(mutation) {
			t.Fatalf("credit mutation misclassified: %s", mutation)
		}
	}
	if isCreditMutation("wrong_service") {
		t.Fatal("route mutation classified as stream-credit mutation")
	}
}

func TestLargeSampleCountRequiresStreamingOpenLoopMode(t *testing.T) {
	cell := config{ReadinessPath: "ready", F75Package: "f75", LocalAttestationPackage: "local", SafePayload: "Z", BenchmarkSamples: 100_001}
	if err := cell.validate(); err == nil {
		t.Fatal("large buffered sample count accepted")
	}
	cell.OfferedRate = 1000
	if err := cell.validate(); err != nil {
		t.Fatalf("large streaming sample count rejected: %v", err)
	}
	cell.BenchmarkSamples = 10_000_001
	if err := cell.validate(); err == nil {
		t.Fatal("sample count above harness safety limit accepted")
	}
}

func TestOpenLoopWaitUsesTheSameQPCClockAsRecordedLatency(t *testing.T) {
	origin := perfclock.Now()
	waitUntilQPC(origin, 1_000_000)
	if elapsed := perfclock.Since(origin); elapsed < 1_000_000 {
		t.Fatalf("QPC deadline returned early: %d", elapsed)
	}
}

func TestGoRuntimeDeltaRetainsAllocationAndGCEvidence(t *testing.T) {
	start := runtime.MemStats{TotalAlloc: 100, Mallocs: 10, Frees: 4, NumGC: 2, PauseTotalNs: 7}
	end := runtime.MemStats{HeapAlloc: 50, HeapSys: 80, HeapIdle: 20, HeapInuse: 60, HeapReleased: 10, TotalAlloc: 160, Mallocs: 16, Frees: 7, NumGC: 4, PauseTotalNs: 17}
	end.PauseNs[0], end.PauseNs[1] = 3, 9
	got := runtimeDelta(start, end)
	if got.TotalAllocBytes != 60 || got.Mallocs != 6 || got.Frees != 3 || got.GCCycles != 2 || got.TotalGCPauseNS != 10 || got.MaximumRecentGCPauseNS != 9 {
		t.Fatalf("unexpected runtime delta: %+v", got)
	}
	if got.HeapAllocBytes != 50 || got.HeapSysBytes != 80 || got.HeapIdleBytes != 20 || got.HeapInuseBytes != 60 || got.HeapReleasedBytes != 10 {
		t.Fatalf("runtime heap fields disappeared: %+v", got)
	}
}
