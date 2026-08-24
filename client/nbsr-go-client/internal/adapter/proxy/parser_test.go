package proxy

import (
	"io"
	"strings"
	"testing"
	"time"
)

func TestParseHTTPConnectUsesRequestTargetNotHostHeader(t *testing.T) {
	request := "CONNECT API.Example:443 HTTP/1.1\r\nHost: attacker.example:443\r\n\r\n"
	target, err := ParseHTTPConnect(strings.NewReader(request), 1024)
	if err != nil {
		t.Fatal(err)
	}
	if target.Name != "api.example" || target.Port != 443 {
		t.Fatalf("target = %+v", target)
	}
}

func TestParseHTTPConnectReturnsBeforeClientClosesConnection(t *testing.T) {
	reader, writer := io.Pipe()
	defer reader.Close()
	defer writer.Close()
	result := make(chan error, 1)
	go func() {
		_, err := ParseHTTPConnect(reader, 1024)
		result <- err
	}()
	if _, err := writer.Write([]byte("CONNECT api.example:443 HTTP/1.1\r\n\r\n")); err != nil {
		t.Fatal(err)
	}
	select {
	case err := <-result:
		if err != nil {
			t.Fatal(err)
		}
	case <-time.After(250 * time.Millisecond):
		t.Fatal("CONNECT parser waited for connection close")
	}
}

func TestParseHTTPConnectRejectsIPAndOversize(t *testing.T) {
	if _, err := ParseHTTPConnect(strings.NewReader("CONNECT 127.0.0.1:443 HTTP/1.1\r\n\r\n"), 1024); err == nil {
		t.Fatal("IP-literal CONNECT accepted")
	}
	if _, err := ParseHTTPConnect(strings.NewReader("CONNECT api.example:443 HTTP/1.1\r\n\r\n"), 8); err == nil {
		t.Fatal("oversized CONNECT accepted")
	}
}

func TestParseSOCKS5ConnectRequiresDomainName(t *testing.T) {
	request := append([]byte{5, 1, 0, 3, 11}, []byte("API.Example")...)
	request = append(request, 0x01, 0xbb)
	target, err := ParseSOCKS5Connect(request)
	if err != nil {
		t.Fatal(err)
	}
	if target.Name != "api.example" || target.Port != 443 {
		t.Fatalf("target = %+v", target)
	}
	if _, err := ParseSOCKS5Connect([]byte{5, 1, 0, 1, 127, 0, 0, 1, 1, 187}); err == nil {
		t.Fatal("SOCKS5 IP target accepted")
	}
}
