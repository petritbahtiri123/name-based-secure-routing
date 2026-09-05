package entry

import (
	"os"
	"path/filepath"
	"testing"
)

func TestAdapterClosedEndpointReadiness(t *testing.T) {
	ready := filepath.Join(t.TempDir(), "ready.json")
	valid := `{"schema":"nbsr-isp-adapter-ready-v1","transport":"tcp","upstream":"127.0.0.1:54321"}`
	if err := os.WriteFile(ready, []byte(valid), 0600); err != nil {
		t.Fatal(err)
	}
	config, err := Load([]string{"--listen", "10.20.0.2:18080", "--ready", ready}, "tcp")
	if err != nil || config.Upstream != "127.0.0.1:54321" {
		t.Fatalf("valid endpoint projection rejected: %v", err)
	}
	for _, listen := range []string{"0.0.0.0:18080", "localhost:18080", "127.0.0.1:18080", "10.20.0.2:80"} {
		if _, err := Load([]string{"--listen", listen, "--ready", ready}, "tcp"); err == nil {
			t.Fatalf("accepted listener %s", listen)
		}
	}
	for _, invalid := range []string{
		`{"schema":"nbsr-isp-adapter-ready-v1","transport":"tcp","upstream":"127.0.0.1:54321","fallback":"127.0.0.1:1"}`,
		`{"schema":"nbsr-isp-adapter-ready-v1","transport":"udp","upstream":"127.0.0.1:54321"}`,
		`{"schema":"nbsr-isp-adapter-ready-v1","transport":"tcp","upstream":"localhost:54321"}`,
		valid + `{}`,
	} {
		if err := os.WriteFile(ready, []byte(invalid), 0600); err != nil {
			t.Fatal(err)
		}
		if _, err := Load([]string{"--listen", "10.20.0.2:18080", "--ready", ready}, "tcp"); err == nil {
			t.Fatal("accepted malformed readiness")
		}
	}
	if _, err := Load([]string{"--listen", "10.20.0.2:18080", "--ready", ready, "--upstream", "127.0.0.1:1"}, "tcp"); err == nil {
		t.Fatal("accepted alternate target")
	}
}
