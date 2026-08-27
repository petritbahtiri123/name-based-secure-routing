package client

import (
	"bufio"
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"fmt"
	"io"
	"net"
	"net/netip"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"

	"nbsr.local/client/nbsr-go-client/demo/internal/fixture"
	"nbsr.local/client/nbsr-go-client/internal/corestate"
	"nbsr.local/client/nbsr-go-client/internal/identity"
	"nbsr.local/client/nbsr-go-client/internal/session"
	"nbsr.local/interop/nbsr-go-peer/wirepeer"
)

const expectedTask4Body = "hello from service-a through NBSR"

func TestFullTask4RealSecureRoute(t *testing.T) {
	rustBinary := requiredE2EPath(t, "NBSR_TASK4_RUST_BINARY")
	backendBinary := requiredE2EPath(t, "NBSR_TASK4_BACKEND_BINARY")
	authorityDir := requiredE2EPath(t, "NBSR_TASK4_AUTHORITY_DIR")

	var seed [ed25519.SeedSize]byte
	for index := range seed {
		seed[index] = 0x44
	}
	proof, err := NewTSProofOwner(ed25519.NewKeyFromSeed(seed[:]), 2)
	if err != nil {
		t.Fatal(err)
	}
	defaults, err := fixture.Start(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	request := defaults.AcquireRequest()
	defaults.Close()
	request.Key.TSGeneration = 2
	request.Key.ProofThumbprint = proof.KeyRef().Thumbprint
	view := session.DestinationRouteView{ServiceIdentity: request.Intent.ServiceIdentity, ServiceDigest: corestate.ServiceDigest(request.Key.ServiceDigest), Intent: request.Intent, ProofThumbprint: request.Key.ProofThumbprint}
	copy(view.ProofPublicKey[:], proof.PublicKey())
	server, err := fixture.Start(t.TempDir(), fixture.WithRouteInputs(request, view))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(server.Close)
	authorityClient, err := NewAuthorityClient(server)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = authorityClient.Close() })

	runtimeDir := t.TempDir()
	admissionPath := filepath.Join(runtimeDir, "runtime-admission.conf")
	admission, err := server.PublicRuntimeAdmissionConfig(sequence32(0x80))
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(admissionPath, admission, 0o600); err != nil {
		t.Fatal(err)
	}
	backendHash := hashFile(t, backendBinary)
	backendMap := filepath.Join(runtimeDir, "backend.map")
	mapText := fmt.Sprintf("NBSR-DEMO-BACKEND-MAP-v1\nservice_id=%s\nexecutable=%s\nsha256=%x\n", request.Intent.ServiceIdentity, filepath.ToSlash(backendBinary), backendHash)
	if err := os.WriteFile(backendMap, []byte(mapText), 0o600); err != nil {
		t.Fatal(err)
	}
	readyPath, resultPath, ackPath := filepath.Join(runtimeDir, "ready.json"), filepath.Join(runtimeDir, "result.json"), filepath.Join(runtimeDir, "complete.ack")
	var rustLog bytes.Buffer
	rust := exec.Command(rustBinary, "--ready", readyPath, "--result", resultPath, "--authority-dir", authorityDir, "--completion-ack", ackPath, "--demo-backend-map", backendMap, "--runtime-admission", admissionPath)
	rust.Stdout, rust.Stderr = &rustLog, &rustLog
	if err := rust.Start(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = rust.Process.Kill(); _ = rust.Wait() })
	waitForFile(t, readyPath, 10*time.Second, func() string { return rustLog.String() })
	readiness, err := wirepeer.LoadReadiness(readyPath)
	if err != nil {
		t.Fatal(err)
	}

	proofKey := identity.TSProofKey{TSGeneration: 2, Key: proof.KeyRef()}
	local := identity.LocalStateIntegrityKey{Key: identity.KeyRef{ID: sha256.Sum256([]byte("task4-local-state")), Purpose: identity.PurposeLocalStateIntegrity, Generation: 1, Thumbprint: sha256.Sum256([]byte("task4-local-thumbprint"))}}
	registry, err := identity.NewMemoryRegistry(server.AcquireRequest().Device, nil, []identity.TSProofKey{proofKey}, local)
	if err != nil {
		t.Fatal(err)
	}
	issuerKID, issuerPublic := server.RouteIssuerTrust()
	federationContext, err := os.ReadFile(filepath.Join(repoRoot(t), "vectors", "wp8-f75-route-open", "federation-context.cbor"))
	if err != nil {
		t.Fatal(err)
	}
	connector := &wireConnector{proof: proof, readiness: readiness, now: server.NowUnix()}
	channelOpener := &wireChannelOpener{proof: proof, issuerKID: issuerKID, issuerPublicKey: issuerPublic, now: server.NowUnix(), federationContextDigest: sha256.Sum256(federationContext)}
	sessions, err := session.NewManager(task4SessionLimits(), fixedClock{server.NowUnix()}, authorityClient.Manager(), registry, connector, channelOpener)
	if err != nil {
		t.Fatal(err)
	}
	spec := session.TransportSessionSpec{Generation: 2, ReuseKey: session.ReuseKey{SourceOperator: request.Key.SourceOperator, Gateway: "destination.edge", Profile: request.Key.Profile, Transport: "quic", DeviceID: request.Key.DeviceID, DeviceGeneration: request.Key.DeviceGeneration, PolicyDigest: request.Key.PolicyHash, PolicyGeneration: request.Key.PolicyGeneration}, Proof: proofKey}
	planner, err := NewSessionRoutePlanner(sessions, spec, proof)
	if err != nil {
		t.Fatal(err)
	}
	opener, err := NewSecureRouteOpener(SecureRouteOpenerConfig{Authority: authorityClient, Sessions: sessions, Planner: planner, AcquireTemplate: server.AcquireRequest(), ChannelID: corestate.ChannelID(sequence16(0x40))})
	if err != nil {
		t.Fatal(err)
	}
	runtime, err := NewRuntime(RuntimeConfig{ListenAddress: "127.0.0.1:0", SharedSyntheticIP: netip.MustParseAddr("127.0.0.2"), NowUnix: server.NowUnix(), MaxConnections: 2, MaxRequestBytes: 4096}, demoResolutionInput(), opener)
	if err != nil {
		t.Fatal(err)
	}
	serveCtx, cancelServe := context.WithCancel(context.Background())
	serveDone := make(chan error, 1)
	go func() { serveDone <- runtime.Serve(serveCtx) }()
	waitForCondition(t, time.Second, runtime.serving, "proxy serve start")

	application, err := net.DialTimeout("tcp", runtime.ProxyAddress(), time.Second)
	if err != nil {
		t.Fatal(err)
	}
	tcp := application.(*net.TCPConn)
	if _, err := io.WriteString(tcp, "CONNECT service-a.nbsr.test:8080 HTTP/1.1\r\nHost: service-a.nbsr.test:8080\r\n\r\n"); err != nil {
		t.Fatal(err)
	}
	reader := bufio.NewReader(tcp)
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
	if _, err := io.WriteString(tcp, "GET / HTTP/1.1\r\nHost: service-a.nbsr.test:8080\r\nUser-Agent: task4-e2e\r\n\r\n"); err != nil {
		t.Fatal(err)
	}
	if err := tcp.CloseWrite(); err != nil {
		t.Fatal(err)
	}
	response, err := io.ReadAll(io.LimitReader(reader, 4097))
	if err != nil {
		t.Fatalf("response read: %v\nRust:\n%s\nsession=%+v authority=%+v", err, rustLog.String(), sessions.Usage(), authorityClient.Manager().Usage())
	}
	if len(response) > 4096 || !strings.Contains(string(response), "\r\n\r\n"+expectedTask4Body) {
		waitForCondition(t, 2*time.Second, func() bool { _, statErr := os.Stat(resultPath); return statErr == nil || rustLog.Len() != 0 }, "destination failure evidence")
		result, _ := os.ReadFile(resultPath)
		t.Fatalf("secure response = %q Rust:\n%s\nresult=%s", response, rustLog.String(), result)
	}
	_ = tcp.Close()
	waitForCondition(t, 2*time.Second, func() bool {
		return runtime.FlowUsage().Entries == 0 && runtime.MappingReferences() == 0 && runtime.ProxyUsage().ActiveConnections == 0
	}, "flow cleanup")
	cancelServe()
	_ = runtime.Close()
	<-serveDone
	if usage := sessions.Usage(); usage.ApplicationStreams != 0 || usage.PendingAdmissions != 0 || usage.Channels != 1 || usage.Sessions != 1 {
		t.Fatalf("flow cleanup did not preserve exactly one reusable SC/TS: %+v", usage)
	}
	if usage := authorityClient.Manager().Usage(); usage.PendingCalls != 0 || usage.PendingWaiters != 0 {
		t.Fatalf("authority usage leaked: %+v", usage)
	}
	if err := os.WriteFile(ackPath, []byte("complete"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := rust.Wait(); err != nil {
		t.Fatalf("Rust destination: %v\n%s", err, rustLog.String())
	}
	if err := opener.Close(); err != nil {
		t.Fatal(err)
	}
	if usage := sessions.Usage(); usage.ApplicationStreams != 0 || usage.PendingAdmissions != 0 || usage.Channels != 0 || usage.Sessions != 0 {
		t.Fatalf("assembly shutdown leaked session ownership: %+v", usage)
	}
	result, err := os.ReadFile(resultPath)
	if err != nil || !bytes.Contains(result, []byte(`"backend_requests":1`)) || !bytes.Contains(result, []byte(`"status":"PASS"`)) {
		t.Fatalf("destination result = %s, %v", result, err)
	}
}

func requiredE2EPath(t *testing.T, key string) string {
	t.Helper()
	value := os.Getenv(key)
	if value == "" {
		t.Skipf("%s is required for the real Task 4 process test", key)
	}
	absolute, err := filepath.Abs(value)
	if err != nil {
		t.Fatal(err)
	}
	return absolute
}

func repoRoot(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("cannot locate Task 4 test source")
	}
	return filepath.Clean(filepath.Join(filepath.Dir(file), "..", "..", "..", "..", ".."))
}

func hashFile(t *testing.T, path string) [32]byte {
	t.Helper()
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return sha256.Sum256(raw)
}

func waitForFile(t *testing.T, path string, timeout time.Duration, diagnostics func() string) {
	t.Helper()
	waitForCondition(t, timeout, func() bool { _, err := os.Stat(path); return err == nil }, "file "+path+"\n"+diagnostics())
}

func waitForCondition(t *testing.T, timeout time.Duration, condition func() bool, label string) {
	t.Helper()
	deadline := time.NewTimer(timeout)
	defer deadline.Stop()
	ticker := time.NewTicker(10 * time.Millisecond)
	defer ticker.Stop()
	for {
		if condition() {
			return
		}
		select {
		case <-deadline.C:
			t.Fatalf("timed out waiting for %s", label)
		case <-ticker.C:
		}
	}
}
