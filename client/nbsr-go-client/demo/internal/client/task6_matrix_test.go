package client

import (
	"bufio"
	"errors"
	"io"
	"net"
	"testing"
	"time"

	"nbsr.local/client/nbsr-go-client/demo/internal/fixture"
	"nbsr.local/client/nbsr-go-client/internal/authority"
)

func TestTask6UnknownServiceDeniedBeforeSecureRoute(t *testing.T) {
	opener := &recordingRouteOpener{}
	runtime := newTestRuntime(t, opener)
	connection, err := net.DialTimeout("tcp", runtime.ProxyAddress(), time.Second)
	if err != nil {
		t.Fatal(err)
	}
	_, _ = io.WriteString(connection, "CONNECT unknown.nbsr.test:8080 HTTP/1.1\r\n\r\n")
	_ = connection.SetReadDeadline(time.Now().Add(time.Second))
	reader := bufio.NewReader(connection)
	status, _ := reader.ReadString('\n')
	for {
		line, readErr := reader.ReadString('\n')
		if readErr != nil || line == "\r\n" {
			break
		}
	}
	_, payloadErr := reader.ReadByte()
	_ = connection.Close()
	waitRuntimeIdle(t, runtime)
	opener.mu.Lock()
	defer opener.mu.Unlock()
	if len(opener.routes) != 0 || status != "HTTP/1.1 200 Connection Established\r\n" || payloadErr == nil {
		t.Fatalf("unknown service did not fail closed: status=%q payload_error=%v routes=%d", status, payloadErr, len(opener.routes))
	}
}

func TestTask6AuthorityDeniedBeforeTransportOrApplication(t *testing.T) {
	task6DeniedAssembly(t, fixture.MutateStaleGeneration, authority.ErrStaleGeneration)
}

func TestTask6ServiceDigestMismatchBeforeTransportOrApplication(t *testing.T) {
	task6DeniedAssembly(t, fixture.MutateServiceDigest, authority.ErrBindingMismatch)
}

func task6DeniedAssembly(t *testing.T, mutation fixture.Mutation, want error) {
	t.Helper()
	connector := newPhaseConnector(false)
	channel := newPhaseChannelOpener(phaseChannelAccept)
	h := newPhaseHarness(t, connector, channel, fixture.WithMutation(mutation))
	connection := h.openProxyFlow(t, []byte("forbidden-application-payload"))
	if err := <-h.routeDone; !errors.Is(err, want) {
		t.Fatalf("route denial = %v, want %v", err, want)
	}
	_ = connection.Close()
	h.waitFlowClean(t)
	h.cancel()
	h.assertClean(t)
	if connector.calls.Load() != 0 || channel.applicationOpens.Load() != 0 || channel.payloadWrites.Load() != 0 {
		t.Fatalf("denial crossed authority boundary: transports=%d streams=%d payloads=%d", connector.calls.Load(), channel.applicationOpens.Load(), channel.payloadWrites.Load())
	}
}
