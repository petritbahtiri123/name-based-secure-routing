//go:build connector_development

package connector

import "testing"

func TestDockerAddressOptIn(t *testing.T) {
	t.Setenv("NBSR_CONNECTOR_DOCKER_ENDPOINT", "")
	for _, endpoint := range []string{"172.30.1.2:4444", "example.com:4444", "127.0.0.2:4444", "127.0.0.1:0"} {
		if _, _, err := loopSocketAddresses(endpoint); err == nil {
			t.Fatalf("default accepted %q", endpoint)
		}
	}
	remote, local, err := loopSocketAddresses("127.0.0.1:4444")
	if err != nil || !remote.IP.IsLoopback() || !local.IsLoopback() {
		t.Fatal("default loopback changed")
	}
	t.Setenv("NBSR_CONNECTOR_DOCKER_ENDPOINT", "172.30.1.2:4444")
	remote, local, err = loopSocketAddresses("172.30.1.2:4444")
	if err != nil || !remote.IP.IsPrivate() || !local.IsUnspecified() {
		t.Fatal("explicit private endpoint rejected")
	}
	for _, endpoint := range []string{"172.30.1.3:4444", "172.30.1.2:4445", "127.0.0.1:4444", "8.8.8.8:4444", "[::1]:4444", "example.com:4444"} {
		if _, _, err := loopSocketAddresses(endpoint); err == nil {
			t.Fatalf("pinned endpoint accepted %q", endpoint)
		}
	}
	for _, endpoint := range []string{"8.8.8.8:4444", "[fc00::1]:4444", "[::ffff:172.30.1.2]:4444", "172.30.1.2:0"} {
		t.Setenv("NBSR_CONNECTOR_DOCKER_ENDPOINT", endpoint)
		if _, _, err := loopSocketAddresses(endpoint); err == nil {
			t.Fatalf("unsafe pin accepted %q", endpoint)
		}
	}
}
