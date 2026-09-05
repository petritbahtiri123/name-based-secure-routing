package main

import (
	"bytes"
	"context"
	"net"
	"testing"
)

func TestOriginConnectorRejectsWrongRequestBeforeResolution(t *testing.T) {
	for _, request := range []string{"GET / HTTP/1.1\r\nHost: wrong:8080\r\n\r\n", "POST / HTTP/1.1\r\nHost: service-a.nbsr.test:8080\r\n\r\n"} {
		resolver := &fakeResolver{}
		var output bytes.Buffer
		if err := run(context.Background(), bytes.NewBufferString(request), &output, "172.30.0.0/24", resolver, &net.Dialer{}); err == nil {
			t.Fatal("invalid request accepted")
		}
		if resolver.calls != 0 || output.Len() != 0 {
			t.Fatal("rejected input reached resolution or output")
		}
	}
}

type fakeResolver struct {
	calls   int
	results []net.IPAddr
}

func (r *fakeResolver) LookupIPAddr(ctx context.Context, name string) ([]net.IPAddr, error) {
	r.calls++
	if name != "private-origin" {
		panic("alternate origin name")
	}
	return r.results, nil
}

func TestOriginConnectorRejectsAmbiguousOrOutsideSubnet(t *testing.T) {
	for _, results := range [][]net.IPAddr{{}, {{IP: net.ParseIP("192.0.2.1")}}, {{IP: net.ParseIP("172.30.0.2")}, {IP: net.ParseIP("172.30.0.3")}}} {
		resolver := &fakeResolver{results: results}
		var output bytes.Buffer
		err := run(context.Background(), bytes.NewBufferString("GET / HTTP/1.1\r\nHost: service-a.nbsr.test:8080\r\n\r\n"), &output, "172.30.0.0/24", resolver, &net.Dialer{})
		if err == nil || output.Len() != 0 || resolver.calls != 1 {
			t.Fatal("ambiguous or out-of-subnet origin accepted")
		}
	}
}
