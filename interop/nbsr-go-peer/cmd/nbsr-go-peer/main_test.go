package main

import "testing"

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
