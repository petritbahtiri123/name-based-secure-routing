package config

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestConfigRejectsOriginInClientSectionAndNonSharedSyntheticIP(t *testing.T) {
	valid := validConfigJSON()

	wrongIP := strings.Replace(valid, `"shared_synthetic_ip":"127.0.0.2"`, `"shared_synthetic_ip":"127.0.0.3"`, 1)
	if _, err := loadJSON(t, wrongIP); err == nil {
		t.Fatal("non-shared Synthetic IP was accepted")
	}

	malformedIP := strings.Replace(valid, `"shared_synthetic_ip":"127.0.0.2"`, `"shared_synthetic_ip":"not-an-ip"`, 1)
	if _, err := loadJSON(t, malformedIP); err == nil {
		t.Fatal("malformed Synthetic IP was accepted")
	}

	withOrigin := strings.Replace(valid, `"proxy_endpoint":"127.0.0.1:18080"`, `"proxy_endpoint":"127.0.0.1:18080","origin_endpoint":"127.0.0.1:19090"`, 1)
	if _, err := loadJSON(t, withOrigin); err == nil {
		t.Fatal("origin endpoint was representable in client configuration")
	}
}

func TestConfigPinsValidatedProfilesArtifactAndBounds(t *testing.T) {
	loaded, err := loadJSON(t, validConfigJSON())
	if err != nil {
		t.Fatal(err)
	}
	if loaded.Production.ALPN != "nbsr-quic-1" || loaded.Production.QUICVersion != "v1" || loaded.Production.TLSVersion != "1.3" || loaded.Production.StreamCreditProfile != "nbsr-stream-credit-1" {
		t.Fatalf("production profiles = %+v", loaded.Production)
	}
	if loaded.Client.SharedSyntheticIP != "127.0.0.2" || loaded.Client.ApplicationTransport != "tcp" || loaded.Client.ServicePort != 8080 {
		t.Fatalf("shared route config = %+v %+v", loaded.Client, loaded.Production)
	}
	if loaded.Destination.RustArtifact.SHA256 != ValidatedRustSHA256 {
		t.Fatalf("Rust hash = %q", loaded.Destination.RustArtifact.SHA256)
	}
	if loaded.Timeouts.HandshakeSeconds != 5 || loaded.Timeouts.OperationSeconds != 15 || loaded.Limits.MaxProxyConnections != 16 || loaded.Limits.MaxRequestBytes != 4096 {
		t.Fatalf("demo bounds = %+v %+v", loaded.Timeouts, loaded.Limits)
	}
}

func TestConfigRejectsNonnumericLoopbackPort(t *testing.T) {
	invalid := strings.Replace(validConfigJSON(), `"proxy_endpoint":"127.0.0.1:18080"`, `"proxy_endpoint":"127.0.0.1:not-a-port"`, 1)
	if _, err := loadJSON(t, invalid); err == nil {
		t.Fatal("nonnumeric loopback port was accepted")
	}
}

func TestServiceFixtureIsExplicitlyNonAuthoritative(t *testing.T) {
	fixture, err := LoadServiceFixture(filepath.Join("..", "..", "testdata", "service-a.json"))
	if err != nil {
		t.Fatal(err)
	}
	if fixture.Classification != DemoFixtureClassification || fixture.PresentationName != "service-a.nbsr.test" || fixture.ServiceIdentity == "" || fixture.Transport != "tcp" || fixture.Port != 8080 {
		t.Fatalf("fixture = %+v", fixture)
	}
}

func TestExampleConfigLoadsWithoutSecretMaterial(t *testing.T) {
	loaded, err := Load(filepath.Join("..", "..", "config.example.json"))
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(strings.ToLower(loaded.Client.ServiceFixture), "secret") || loaded.Secrets.Directory == "" {
		t.Fatalf("unsafe example config = %+v", loaded)
	}
}

func loadJSON(t *testing.T, value string) (Config, error) {
	t.Helper()
	path := filepath.Join(t.TempDir(), "config.json")
	if err := os.WriteFile(path, []byte(value), 0o600); err != nil {
		t.Fatal(err)
	}
	return Load(path)
}

func validConfigJSON() string {
	return `{"schema":"nbsr-demo-config-v1","production_semantic":{"alpn":"nbsr-quic-1","quic_version":"v1","tls_version":"1.3","stream_credit_profile":"nbsr-stream-credit-1"},"client":{"service_fixture":"testdata/service-a.json","shared_synthetic_ip":"127.0.0.2","proxy_endpoint":"127.0.0.1:18080","acp_endpoint":"https://127.0.0.1:18443","destination_readiness":"test-results/nbsr-demo/runtime/destination-ready.json","application_transport":"tcp","service_port":8080},"acp_fixture":{"classification":"DEMO FIXTURE — NOT PRODUCTION AUTHORITY","public_fixture":"test-results/nbsr-demo/runtime/acp-public.json"},"destination":{"authority_fixture":"test-results/nbsr-demo/runtime/destination-authority","rust_artifact":{"path":"C:\\NBSR-build\\tranche5-closure-b124939\\cargo-target\\release\\wp8_interop_server.exe","sha256":"b20b52e4d4ac0c3d0f7b6ca6e04e7cd80c5099e6ed185da7b04071f3fc97a888"}},"evidence":{"directory":"test-results/nbsr-demo/evidence"},"secrets":{"directory":"test-results/nbsr-demo/runtime/secrets"},"timeouts":{"handshake_seconds":5,"operation_seconds":15},"limits":{"max_proxy_connections":16,"max_request_bytes":4096}}`
}
