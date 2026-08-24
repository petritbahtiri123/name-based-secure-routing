package proxy

import (
	"errors"
	"io"
	"net"
	"strconv"
	"strings"

	"nbsr.local/client/nbsr-go-client/internal/resolution"
)

var ErrInvalidProxyRequest = errors.New("invalid proxy request")

type Target struct {
	Name resolution.CanonicalName
	Port uint16
}

func ParseHTTPConnect(reader io.Reader, maxBytes int64) (Target, error) {
	if reader == nil || maxBytes <= 0 {
		return Target{}, ErrInvalidProxyRequest
	}
	wire, err := readHTTPHeader(reader, maxBytes)
	if err != nil {
		return Target{}, ErrInvalidProxyRequest
	}
	line, _, found := strings.Cut(string(wire), "\r\n")
	fields := strings.Fields(line)
	if !found || len(fields) != 3 || fields[0] != "CONNECT" || fields[2] != "HTTP/1.1" && fields[2] != "HTTP/1.0" {
		return Target{}, ErrInvalidProxyRequest
	}
	return parseAuthority(fields[1])
}

func readHTTPHeader(reader io.Reader, maxBytes int64) ([]byte, error) {
	wire := make([]byte, 0, min(maxBytes, 1024))
	var next [1]byte
	for int64(len(wire)) < maxBytes {
		if _, err := io.ReadFull(reader, next[:]); err != nil {
			return nil, ErrInvalidProxyRequest
		}
		wire = append(wire, next[0])
		if len(wire) >= 4 && string(wire[len(wire)-4:]) == "\r\n\r\n" {
			return wire, nil
		}
	}
	return nil, ErrInvalidProxyRequest
}

func ParseSOCKS5Connect(wire []byte) (Target, error) {
	if len(wire) < 8 || wire[0] != 5 || wire[1] != 1 || wire[2] != 0 || wire[3] != 3 {
		return Target{}, ErrInvalidProxyRequest
	}
	nameLength := int(wire[4])
	if nameLength == 0 || len(wire) != 7+nameLength {
		return Target{}, ErrInvalidProxyRequest
	}
	name, err := resolution.CanonicalizePresentationName(string(wire[5 : 5+nameLength]))
	port := uint16(wire[5+nameLength])<<8 | uint16(wire[6+nameLength])
	if err != nil || port == 0 {
		return Target{}, ErrInvalidProxyRequest
	}
	return Target{Name: name, Port: port}, nil
}

func parseAuthority(authority string) (Target, error) {
	host, portText, err := net.SplitHostPort(authority)
	if err != nil {
		return Target{}, ErrInvalidProxyRequest
	}
	name, err := resolution.CanonicalizePresentationName(host)
	port, portErr := strconv.ParseUint(portText, 10, 16)
	if err != nil || portErr != nil || port == 0 {
		return Target{}, ErrInvalidProxyRequest
	}
	return Target{Name: name, Port: uint16(port)}, nil
}
