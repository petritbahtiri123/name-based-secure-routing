package main

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net"
	"net/http"
	"net/netip"
	"os"
	"time"
)

const originName = "private-origin"
const originPort = "8080"
const maximumBytes = 4096

type resolver interface {
	LookupIPAddr(context.Context, string) ([]net.IPAddr, error)
}
type dialer interface {
	DialContext(context.Context, string, string) (net.Conn, error)
}

func run(ctx context.Context, input io.Reader, output io.Writer, cidr string, r resolver, d dialer) error {
	prefix, err := netip.ParsePrefix(cidr)
	if err != nil || !prefix.Addr().Is4() || !prefix.Addr().IsPrivate() || prefix != prefix.Masked() || prefix.Bits() < 8 {
		return errors.New("invalid containment")
	}
	type readResult struct {
		data []byte
		err  error
	}
	read := make(chan readResult, 1)
	go func() { data, err := io.ReadAll(io.LimitReader(input, maximumBytes+1)); read <- readResult{data, err} }()
	var raw []byte
	select {
	case result := <-read:
		if result.err != nil {
			return errors.New("request failed")
		}
		raw = result.data
	case <-ctx.Done():
		return ctx.Err()
	}
	if len(raw) == 0 || len(raw) > maximumBytes || bytes.IndexByte(raw, 0) >= 0 {
		return errors.New("invalid request")
	}
	buffer := bufio.NewReader(bytes.NewReader(raw))
	request, err := http.ReadRequest(buffer)
	if err != nil {
		return errors.New("invalid request")
	}
	defer request.Body.Close()
	if request.Method != "GET" || request.RequestURI != "/" || request.Host != "service-a.nbsr.test:8080" || request.URL == nil || request.URL.Scheme != "" || request.URL.Host != "" || request.ContentLength != 0 || len(request.TransferEncoding) != 0 || request.Header.Get("Content-Length") != "" {
		return errors.New("unsupported request")
	}
	body, err := io.ReadAll(io.LimitReader(request.Body, 1))
	if err != nil || len(body) != 0 || buffer.Buffered() != 0 {
		return errors.New("trailing request")
	}
	addresses, err := r.LookupIPAddr(ctx, originName)
	if err != nil || len(addresses) != 1 || addresses[0].Zone != "" {
		return errors.New("origin resolution failed")
	}
	ip, ok := netip.AddrFromSlice(addresses[0].IP.To4())
	if !ok || !prefix.Contains(ip) {
		return errors.New("origin containment failed")
	}
	connection, err := d.DialContext(ctx, "tcp4", net.JoinHostPort(ip.String(), originPort))
	if err != nil {
		return errors.New("origin connection failed")
	}
	defer connection.Close()
	stop := context.AfterFunc(ctx, func() { _ = connection.Close() })
	defer stop()
	deadline, ok := ctx.Deadline()
	if !ok {
		deadline = time.Now().Add(3 * time.Second)
	}
	if err := connection.SetDeadline(deadline); err != nil {
		return errors.New("origin deadline failed")
	}
	if _, err = io.Copy(connection, bytes.NewReader(raw)); err != nil {
		return errors.New("origin write failed")
	}
	response, err := io.ReadAll(io.LimitReader(connection, maximumBytes+1))
	if err != nil || len(response) == 0 || len(response) > maximumBytes {
		return errors.New("origin response failed")
	}
	responseReader := bufio.NewReader(bytes.NewReader(response))
	parsed, err := http.ReadResponse(responseReader, request)
	if err != nil {
		return errors.New("origin response invalid")
	}
	defer parsed.Body.Close()
	if parsed.StatusCode != 200 {
		return errors.New("origin did not succeed")
	}
	if _, err := io.ReadAll(io.LimitReader(parsed.Body, maximumBytes+1)); err != nil || responseReader.Buffered() != 0 {
		return errors.New("origin response incomplete or trailing")
	}
	if ctx.Err() != nil {
		return ctx.Err()
	}
	_, err = io.Copy(output, bytes.NewReader(response))
	return err
}

func main() {
	// The unchanged backend launcher clears the environment and sets cwd to
	// the executable parent. This fixed sibling file contains a subnet only.
	file, err := os.Open("origin-config.json")
	var raw []byte
	if err == nil {
		raw, err = io.ReadAll(io.LimitReader(file, 1025))
		_ = file.Close()
	}
	var config struct {
		Schema      string `json:"schema"`
		PrivateCIDR string `json:"private_cidr"`
	}
	if err == nil && len(raw) <= 1024 {
		decoder := json.NewDecoder(bytes.NewReader(raw))
		decoder.DisallowUnknownFields()
		err = decoder.Decode(&config)
		if err == nil {
			var extra any
			if decoder.Decode(&extra) != io.EOF {
				err = errors.New("trailing config")
			}
		}
	} else {
		err = errors.New("configuration unavailable")
	}
	if err == nil && config.Schema == "nbsr-isp-origin-config-v1" {
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		err = run(ctx, os.Stdin, os.Stdout, config.PrivateCIDR, net.DefaultResolver, &net.Dialer{})
		cancel()
	} else {
		err = errors.New("configuration invalid")
	}
	if err != nil {
		_, _ = io.WriteString(os.Stderr, "NBSR_DEMO_BACKEND_COMPLETE requests=0 status=failed\n")
		os.Exit(1)
	}
	_, err = io.WriteString(os.Stderr, "NBSR_DEMO_BACKEND_COMPLETE requests=1 status=ok\n")
	if err != nil {
		os.Exit(1)
	}
}
