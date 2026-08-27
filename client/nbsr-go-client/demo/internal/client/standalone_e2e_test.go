package client

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"

	democonfig "nbsr.local/client/nbsr-go-client/demo/internal/config"
	"nbsr.local/interop/nbsr-go-peer/wirepeer"
)

func TestStandaloneClientRealSecureRoute(t *testing.T) {
	runStandaloneScenario(t, "success")
}

func TestStandaloneBackendFailureHasNoFallback(t *testing.T) {
	runStandaloneScenario(t, "backend-failure")
}

func TestStandaloneTransportFailureHasNoFallback(t *testing.T) {
	runStandaloneScenario(t, "transport-failure")
}

func runStandaloneScenario(t *testing.T, scenario string) {
	t.Helper()
	clientBinary := requiredE2EPath(t, "NBSR_TASK4_CLIENT_BINARY")
	authorityBinary := requiredE2EPath(t, "NBSR_TASK4_AUTHORITY_BINARY")
	trustDir := requiredE2EPath(t, "NBSR_TASK4_AUTHORITY_DIR")
	trustRoot := t.TempDir()
	runtimeDir := filepath.Join(trustRoot, "test-results", "nbsr-demo", "runtime")
	if err := os.MkdirAll(filepath.Join(runtimeDir, "client-bootstrap"), 0o700); err != nil {
		t.Fatal(err)
	}
	acpAddress := freeLoopbackAddress(t)
	proxyAddress := freeLoopbackAddress(t)
	authority := exec.Command(authorityBinary, "--listen", acpAddress, "--runtime", "test-results/nbsr-demo/runtime", "--client-bootstrap", "test-results/nbsr-demo/runtime/client-bootstrap", "--runtime-admission", "test-results/nbsr-demo/runtime/runtime-admission.conf")
	authority.Dir = trustRoot
	var authorityLog bytes.Buffer
	authority.Stdout, authority.Stderr = &authorityLog, &authorityLog
	if err := authority.Start(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = authority.Process.Kill(); _ = authority.Wait() })
	waitForFile(t, filepath.Join(runtimeDir, "client-bootstrap", "client-bootstrap.json"), 10*time.Second, authorityLog.String)

	backend := requiredE2EPath(t, "NBSR_TASK4_BACKEND_BINARY")
	backendFailureCount := ""
	if scenario == "backend-failure" {
		backendFailureCount = filepath.Join(runtimeDir, "failing-backend.count")
		backend = filepath.Join(t.TempDir(), "failing-backend.exe")
		build := exec.Command("go", "build", "-ldflags", "-X main.countPath="+backendFailureCount, "-o", backend, "./internal/client/testdata/failing-backend")
		build.Dir = filepath.Join(repoRoot(t), "client", "nbsr-go-client", "demo")
		if output, buildErr := build.CombinedOutput(); buildErr != nil {
			t.Fatalf("build failing backend: %v %s", buildErr, output)
		}
	}
	backendMap := filepath.Join(runtimeDir, "backend.map")
	mapText := fmt.Sprintf("NBSR-DEMO-BACKEND-MAP-v1\nservice_id=nbsr-demo-service-a-v1\nexecutable=%s\nsha256=%x\n", filepath.ToSlash(backend), hashFile(t, backend))
	if err := os.WriteFile(backendMap, []byte(mapText), 0o600); err != nil {
		t.Fatal(err)
	}
	readyPath, resultPath, ackPath := filepath.Join(runtimeDir, "destination-ready.json"), filepath.Join(runtimeDir, "destination-result.json"), filepath.Join(runtimeDir, "destination.ack")
	rust := exec.Command(requiredE2EPath(t, "NBSR_TASK4_RUST_BINARY"), "--ready", readyPath, "--result", resultPath, "--authority-dir", trustDir, "--completion-ack", ackPath, "--demo-backend-map", backendMap, "--runtime-admission", filepath.Join(runtimeDir, "runtime-admission.conf"))
	var rustLog bytes.Buffer
	rust.Stdout, rust.Stderr = &rustLog, &rustLog
	if err := rust.Start(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = rust.Process.Kill(); _ = rust.Wait() })
	waitForFile(t, readyPath, 10*time.Second, rustLog.String)

	servicePath := filepath.Join(trustRoot, "service-a.json")
	service := democonfig.ServiceFixture{Classification: democonfig.DemoFixtureClassification, PresentationName: "service-a.nbsr.test", ServiceIdentity: "nbsr-demo-service-a-v1", Transport: "tcp", Port: 8080}
	writeJSONTest(t, servicePath, service)
	configuration := democonfig.Config{Schema: democonfig.Schema, Production: democonfig.ProductionSemantic{ALPN: wirepeer.ALPN, QUICVersion: wirepeer.QUICVersion, TLSVersion: wirepeer.TLSVersion, StreamCreditProfile: wirepeer.StreamCreditProfile}, Client: democonfig.ClientConfig{ServiceFixture: "service-a.json", SharedSyntheticIP: democonfig.SharedSyntheticIP, ProxyEndpoint: proxyAddress, ACPEndpoint: "https://" + acpAddress, DestinationReadiness: "test-results/nbsr-demo/runtime/destination-ready.json", ApplicationTransport: "tcp", ServicePort: 8080}, ACPFixture: democonfig.ACPFixtureConfig{Classification: democonfig.DemoFixtureClassification, PublicFixture: "test-results/nbsr-demo/runtime/acp-public.json"}, Destination: democonfig.DestinationConfig{AuthorityFixture: "test-results/nbsr-demo/runtime/destination-authority", RustArtifact: democonfig.ArtifactRef{Path: democonfig.ValidatedRustArtifactPath, SHA256: democonfig.ValidatedRustSHA256}}, Evidence: democonfig.EvidenceConfig{Directory: "test-results/nbsr-demo/evidence"}, Secrets: democonfig.SecretReferences{Directory: "test-results/nbsr-demo/runtime/secrets"}, Timeouts: democonfig.Timeouts{HandshakeSeconds: 5, OperationSeconds: 15}, Limits: democonfig.Limits{MaxProxyConnections: 16, MaxRequestBytes: 4096}}
	writeJSONTest(t, filepath.Join(trustRoot, "config.example.json"), configuration)
	clientReady := filepath.Join(runtimeDir, "client-ready.json")
	clientProcess := exec.Command(clientBinary, "--config", "config.example.json", "--bootstrap", "test-results/nbsr-demo/runtime/client-bootstrap", "--ready", "test-results/nbsr-demo/runtime/client-ready.json")
	clientProcess.Dir = trustRoot
	var clientLog bytes.Buffer
	clientProcess.Stdout, clientProcess.Stderr = &clientLog, &clientLog
	if err := clientProcess.Start(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = clientProcess.Process.Kill(); _ = clientProcess.Wait() })
	waitForFile(t, clientReady, 10*time.Second, clientLog.String)
	if scenario == "transport-failure" {
		_ = rust.Process.Kill()
		_ = rust.Wait()
	}

	connection, err := net.DialTimeout("tcp", proxyAddress, time.Second)
	if err != nil {
		t.Fatal(err)
	}
	reader := bufio.NewReader(connection)
	_, _ = io.WriteString(connection, "CONNECT service-a.nbsr.test:8080 HTTP/1.1\r\nHost: service-a.nbsr.test:8080\r\n\r\n")
	for {
		line, readErr := reader.ReadString('\n')
		if readErr != nil {
			t.Fatal(readErr)
		}
		if line == "\r\n" {
			break
		}
	}
	path := "/"
	_, _ = io.WriteString(connection, "GET "+path+" HTTP/1.1\r\nHost: service-a.nbsr.test:8080\r\nUser-Agent: task4c-standalone\r\n\r\n")
	_ = connection.(*net.TCPConn).CloseWrite()
	_ = connection.SetReadDeadline(time.Now().Add(5 * time.Second))
	response, err := io.ReadAll(io.LimitReader(reader, 4097))
	_ = connection.Close()
	if scenario == "success" && (err != nil || !strings.Contains(string(response), "\r\n\r\n"+expectedTask4Body)) {
		t.Fatalf("standalone response=%q err=%v client=%s authority=%s rust=%s", response, err, &clientLog, &authorityLog, &rustLog)
	}
	if scenario != "success" && strings.Contains(string(response), expectedTask4Body) {
		t.Fatal("failure scenario used a successful backend or fallback")
	}
	if scenario == "transport-failure" {
		if _, statErr := os.Stat(resultPath); statErr == nil {
			result, _ := os.ReadFile(resultPath)
			if bytes.Contains(result, []byte(`"backend_requests":1`)) {
				t.Fatalf("transport failure invoked backend: %s", result)
			}
		}
		_ = clientProcess.Process.Kill()
		_ = clientProcess.Wait()
		_ = authority.Process.Kill()
		_ = authority.Wait()
		return
	}
	if err := os.WriteFile(ackPath, []byte("complete"), 0o600); err != nil {
		t.Fatal(err)
	}
	if waitErr := rust.Wait(); scenario == "success" && waitErr != nil {
		t.Fatalf("Rust: %v %s", waitErr, &rustLog)
	}
	result, err := os.ReadFile(resultPath)
	if scenario == "success" && (err != nil || !bytes.Contains(result, []byte(`"backend_requests":1`))) {
		t.Fatalf("result=%s err=%v", result, err)
	}
	if scenario == "backend-failure" {
		count, countErr := os.ReadFile(backendFailureCount)
		if countErr != nil || string(count) != "1" || bytes.Contains(result, []byte(`"status":"PASS"`)) {
			t.Fatalf("backend failure count=%q countErr=%v result=%s", count, countErr, result)
		}
	}
	_ = clientProcess.Process.Kill()
	_ = clientProcess.Wait()
	_ = authority.Process.Kill()
	_ = authority.Wait()
}

func freeLoopbackAddress(t *testing.T) string {
	t.Helper()
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	address := listener.Addr().String()
	_ = listener.Close()
	return address
}
func writeJSONTest(t *testing.T, path string, value any) {
	t.Helper()
	raw, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, append(raw, '\n'), 0o600); err != nil {
		t.Fatal(err)
	}
}
