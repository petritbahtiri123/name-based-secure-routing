package main

import "testing"

func TestLifecycleConfigurationRequiresBoundedIndependentServices(t *testing.T) {
	valid := config{ReadinessPath: "ready", F75Package: "f75", LocalAttestationPackage: "local", SafePayload: "Z", LifecycleAuthorityDir: "authority", LifecycleConnections: 1, LifecycleServices: 20, LifecycleStreamsPerService: 64}
	if err := valid.validate(); err != nil {
		t.Fatalf("valid lifecycle configuration rejected: %v", err)
	}
	invalid := valid
	invalid.LifecycleServices = 21
	if err := invalid.validate(); err == nil {
		t.Fatal("service count above frozen benchmark limit accepted")
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
