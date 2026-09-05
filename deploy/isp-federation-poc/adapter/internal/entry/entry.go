package entry

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net"
	"net/netip"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"nbsr.local/isp-federation-poc/adapter/internal/forward"
)

type Config struct{ Listen, Upstream string }

var errConfiguration = errors.New("invalid adapter configuration")

// Load consumes an endpoint-only projection produced from validated runtime
// readiness. The adapter never reads certificates, keys or authority objects.
func Load(args []string, transport string) (Config, error) {
	var config Config
	if len(args) != 4 || args[0] != "--listen" || args[2] != "--ready" {
		return config, errConfiguration
	}
	port := uint16(18080)
	if transport == "udp" {
		port = 45980
	} else if transport != "tcp" {
		return config, errConfiguration
	}
	listen, err := netip.ParseAddrPort(args[1])
	if err != nil || !listen.Addr().Is4() || !listen.Addr().IsPrivate() || listen.Port() != port {
		return config, errConfiguration
	}
	file, err := os.Open(args[3])
	if err != nil {
		return config, errConfiguration
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil || !info.Mode().IsRegular() || info.Size() > 4096 {
		return config, errConfiguration
	}
	decoder := json.NewDecoder(io.LimitReader(file, 4097))
	token, err := decoder.Token()
	if err != nil || token != json.Delim('{') {
		return config, errConfiguration
	}
	fields := make(map[string]string)
	for decoder.More() {
		token, err = decoder.Token()
		key, ok := token.(string)
		if err != nil || !ok || (key != "schema" && key != "transport" && key != "upstream") {
			return config, errConfiguration
		}
		if _, exists := fields[key]; exists {
			return config, errConfiguration
		}
		var value string
		if decoder.Decode(&value) != nil {
			return config, errConfiguration
		}
		fields[key] = value
	}
	if _, err = decoder.Token(); err != nil {
		return config, errConfiguration
	}
	if _, err = decoder.Token(); err != io.EOF {
		return config, errConfiguration
	}
	upstream, err := netip.ParseAddrPort(fields["upstream"])
	if err != nil || upstream.Addr() != netip.MustParseAddr("127.0.0.1") || upstream.Port() == 0 ||
		fields["schema"] != "nbsr-isp-adapter-ready-v1" || fields["transport"] != transport || len(fields) != 3 {
		return config, errConfiguration
	}
	config.Listen, config.Upstream = listen.String(), upstream.String()
	return config, nil
}

func Main(transport string) {
	config, err := Load(os.Args[1:], transport)
	if err != nil {
		fail()
	}
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()
	if transport == "tcp" {
		listener, listenErr := net.Listen("tcp4", config.Listen)
		if listenErr != nil {
			fail()
		}
		err = forward.ServeTCP(ctx, listener, config.Upstream, 16, 20*time.Second)
	} else {
		// Both addresses were already parsed as IPv4 literals; no DNS resolution.
		address := netip.MustParseAddrPort(config.Listen)
		upstream := netip.MustParseAddrPort(config.Upstream)
		listener, listenErr := net.ListenUDP("udp4", net.UDPAddrFromAddrPort(address))
		if listenErr != nil {
			fail()
		}
		err = forward.ServeUDP(ctx, listener, net.UDPAddrFromAddrPort(upstream), 16, 20*time.Second)
	}
	if err != nil {
		fail()
	}
}

func fail() {
	_, _ = io.Copy(os.Stderr, strings.NewReader("NBSR_ISP_POC_ADAPTER status=failed\n"))
	os.Exit(1)
}
