package main

import (
	"bufio"
	"bytes"
	"errors"
	"io"
	"net/http"
	"os"
)

const maxRequestBytes = 4096

const response = "HTTP/1.1 200 OK\r\nContent-Length: 33\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\nhello from service-a through NBSR"

func main() {
	if err := run(os.Stdin, os.Stdout, os.Stderr); err != nil {
		os.Exit(1)
	}
}

func run(stdin io.Reader, stdout, stderr io.Writer) error {
	request, err := readOneRequest(stdin)
	if err != nil {
		_, _ = io.WriteString(stderr, "NBSR_DEMO_BACKEND_COMPLETE requests=0 status=rejected\n")
		return err
	}
	defer request.Body.Close()

	if _, err := io.WriteString(stdout, response); err != nil {
		_, _ = io.WriteString(stderr, "NBSR_DEMO_BACKEND_COMPLETE requests=0 status=failed\n")
		return err
	}
	if _, err := io.WriteString(stderr, "NBSR_DEMO_BACKEND_COMPLETE requests=1 status=ok\n"); err != nil {
		return err
	}
	return nil
}

func readOneRequest(stdin io.Reader) (*http.Request, error) {
	payload, err := io.ReadAll(io.LimitReader(stdin, maxRequestBytes+1))
	if err != nil {
		return nil, errors.New("request read failed")
	}
	if len(payload) == 0 {
		return nil, errors.New("empty request")
	}
	if len(payload) > maxRequestBytes {
		return nil, errors.New("request too large")
	}
	if bytes.IndexByte(payload, 0) >= 0 {
		return nil, errors.New("invalid request")
	}

	buffered := bufio.NewReader(bytes.NewReader(payload))
	request, err := http.ReadRequest(buffered)
	if err != nil {
		return nil, errors.New("malformed request")
	}
	if request.Method != http.MethodGet || request.RequestURI != "/" || request.Host != "service-a.nbsr.test:8080" ||
		request.URL == nil || request.URL.Scheme != "" || request.URL.Host != "" || request.URL.Path != "/" || request.URL.RawQuery != "" ||
		request.ContentLength != 0 || len(request.TransferEncoding) != 0 || request.Header.Get("Content-Length") != "" {
		request.Body.Close()
		return nil, errors.New("unsupported request")
	}
	body, err := io.ReadAll(io.LimitReader(request.Body, 1))
	if err != nil || len(body) != 0 || buffered.Buffered() != 0 {
		request.Body.Close()
		return nil, errors.New("request body or trailing bytes rejected")
	}
	return request, nil
}
