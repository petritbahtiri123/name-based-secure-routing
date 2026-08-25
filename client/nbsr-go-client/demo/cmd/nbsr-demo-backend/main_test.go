package main

import (
	"bytes"
	"strings"
	"testing"
)

func TestRunServesOneDeterministicRequest(t *testing.T) {
	request := "GET / HTTP/1.1\r\nHost: service-a.nbsr.test:8080\r\nUser-Agent: test\r\n\r\n"
	var stdout bytes.Buffer
	var stderr bytes.Buffer

	if err := run(strings.NewReader(request), &stdout, &stderr); err != nil {
		t.Fatalf("run: %v", err)
	}

	want := "HTTP/1.1 200 OK\r\nContent-Length: 33\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\nhello from service-a through NBSR"
	if stdout.String() != want {
		t.Fatalf("response = %q, want %q", stdout.String(), want)
	}
	if stderr.String() != "NBSR_DEMO_BACKEND_COMPLETE requests=1 status=ok\n" {
		t.Fatalf("completion status = %q", stderr.String())
	}
}

func TestRunRejectsMalformedOversizedAndInjectedRequests(t *testing.T) {
	valid := "GET / HTTP/1.1\r\nHost: service-a.nbsr.test:8080\r\n\r\n"
	tests := []struct {
		name    string
		request string
	}{
		{name: "early close", request: ""},
		{name: "malformed", request: "not HTTP\r\n\r\n"},
		{name: "wrong method", request: "POST / HTTP/1.1\r\nHost: service-a.nbsr.test:8080\r\nContent-Length: 0\r\n\r\n"},
		{name: "wrong host", request: "GET / HTTP/1.1\r\nHost: attacker.invalid:8080\r\n\r\n"},
		{name: "header injection", request: "GET / HTTP/1.1\r\nHost: service-a.nbsr.test:8080\r\nX-Test: safe\r\ninjected\r\n\r\n"},
		{name: "pipelined second request", request: valid + valid},
		{name: "oversized", request: "GET / HTTP/1.1\r\nHost: service-a.nbsr.test:8080\r\nX-Fill: " + strings.Repeat("a", maxRequestBytes) + "\r\n\r\n"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			var stdout bytes.Buffer
			var stderr bytes.Buffer
			if err := run(strings.NewReader(test.request), &stdout, &stderr); err == nil {
				t.Fatal("request unexpectedly accepted")
			}
			if stdout.Len() != 0 {
				t.Fatalf("rejected request produced %d response bytes", stdout.Len())
			}
			if stderr.String() != "NBSR_DEMO_BACKEND_COMPLETE requests=0 status=rejected\n" {
				t.Fatalf("completion status = %q", stderr.String())
			}
		})
	}
}
