package client

import (
	"testing"

	"nbsr.local/client/nbsr-go-client/demo/internal/bootstrap"
	democonfig "nbsr.local/client/nbsr-go-client/demo/internal/config"
	"nbsr.local/client/nbsr-go-client/demo/internal/fixture"
	"nbsr.local/interop/nbsr-go-peer/wirepeer"
)

func TestStandaloneAssemblyUsesTheConcreteSecureRouteOpener(t *testing.T) {
	root := t.TempDir()
	server, err := fixture.StartStandaloneAt(t.TempDir(), "127.0.0.1:0", root)
	if err != nil {
		t.Fatal(err)
	}
	defer server.Close()
	state, err := bootstrap.Load(root)
	if err != nil {
		t.Fatal(err)
	}
	configuration := democonfig.Config{Client: democonfig.ClientConfig{ProxyEndpoint: "127.0.0.1:0", ACPEndpoint: state.Endpoint, SharedSyntheticIP: democonfig.SharedSyntheticIP}, Limits: democonfig.Limits{MaxProxyConnections: 2, MaxRequestBytes: 4096}}
	service := democonfig.ServiceFixture{Classification: democonfig.DemoFixtureClassification, PresentationName: "service-a.nbsr.test", ServiceIdentity: state.AcquireTemplate.Intent.ServiceIdentity, Transport: "tcp", Port: 8080}
	assembly, err := NewStandaloneAssembly(configuration, state, service, wirepeer.Readiness{ALPN: wirepeer.ALPN, QUICVersion: wirepeer.QUICVersion, TLSVersion: wirepeer.TLSVersion, Endpoint: "127.0.0.1:1", ServerName: "destination.edge"})
	if err != nil {
		t.Fatal(err)
	}
	defer assembly.Close()
	if assembly.Runtime == nil || assembly.Opener == nil || assembly.Runtime.ProxyAddress() == "" {
		t.Fatal("standalone assembly did not use shared secure runtime")
	}
}
