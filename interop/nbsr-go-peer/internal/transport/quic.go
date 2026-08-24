// Package transport contains only the independent peer's public quic-go/TLS
// adapter. It has no NBSR authority or state-machine decisions.
package transport

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"errors"
	"io"
	"os"
	"sync"

	quic "github.com/quic-go/quic-go"
	"nbsr.local/interop/nbsr-go-peer/internal/core"
)

type Readiness struct {
	ALPN          string `json:"alpn"`
	CADER         string `json:"ca_der"`
	ClientCertDER string `json:"client_cert_der"`
	ClientKeyDER  string `json:"client_key_der"`
	Endpoint      string `json:"endpoint"`
	QUICVersion   string `json:"quic_version"`
	ServerName    string `json:"server_name"`
	TLSVersion    string `json:"tls_version"`
}

func LoadReadiness(path string) (Readiness, error) {
	file, err := os.Open(path)
	if err != nil {
		return Readiness{}, err
	}
	defer file.Close()
	decoder := json.NewDecoder(io.LimitReader(file, 16*1024))
	decoder.DisallowUnknownFields()
	var ready Readiness
	if err := decoder.Decode(&ready); err != nil {
		return Readiness{}, err
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return Readiness{}, errors.New("readiness must contain one object")
	}
	if ready.ALPN != "nbsr-quic-1" || ready.QUICVersion != "v1" || ready.TLSVersion != "1.3" || ready.ServerName != "destination.edge" || ready.Endpoint == "" {
		return Readiness{}, errors.New("unsupported transport readiness")
	}
	return ready, nil
}

type Peer struct {
	connection *quic.Conn
	control    *quic.Stream
	tlsState   tls.ConnectionState
	controlMu  sync.Mutex
}

func Dial(ctx context.Context, ready Readiness) (*Peer, error) {
	caRaw, err := os.ReadFile(ready.CADER)
	if err != nil {
		return nil, err
	}
	ca, err := x509.ParseCertificate(caRaw)
	if err != nil {
		return nil, err
	}
	certRaw, err := os.ReadFile(ready.ClientCertDER)
	if err != nil {
		return nil, err
	}
	cert, err := x509.ParseCertificate(certRaw)
	if err != nil {
		return nil, err
	}
	keyRaw, err := os.ReadFile(ready.ClientKeyDER)
	if err != nil {
		return nil, err
	}
	key, err := x509.ParsePKCS8PrivateKey(keyRaw)
	if err != nil {
		return nil, err
	}
	roots := x509.NewCertPool()
	roots.AddCert(ca)
	tlsConfig := &tls.Config{RootCAs: roots, Certificates: []tls.Certificate{{Certificate: [][]byte{cert.Raw}, PrivateKey: key, Leaf: cert}}, ServerName: ready.ServerName, NextProtos: []string{ready.ALPN}, MinVersion: tls.VersionTLS13, MaxVersion: tls.VersionTLS13, SessionTicketsDisabled: true, KeyLogWriter: nil}
	connection, err := quic.DialAddr(ctx, ready.Endpoint, tlsConfig, &quic.Config{Versions: []quic.Version{quic.Version1}, Allow0RTT: false})
	if err != nil {
		return nil, err
	}
	state := connection.ConnectionState()
	if state.Version != quic.Version1 || state.TLS.Version != tls.VersionTLS13 || state.TLS.NegotiatedProtocol != ready.ALPN || state.Used0RTT {
		connection.CloseWithError(1, "unsupported transport")
		return nil, errors.New("transport negotiation mismatch")
	}
	control, err := connection.OpenStreamSync(ctx)
	if err != nil {
		connection.CloseWithError(1, "control failed")
		return nil, err
	}
	if control.StreamID() != 0 {
		connection.CloseWithError(1, "control stream mismatch")
		return nil, errors.New("first control stream is not stream 0")
	}
	return &Peer{connection: connection, control: control, tlsState: state.TLS}, nil
}

func (peer *Peer) SendEnvelope(envelope core.Envelope) error {
	wire, err := core.EncodeEnvelope(envelope)
	if err != nil {
		return err
	}
	frame, err := core.EncodeControlFrame(wire)
	if err != nil {
		return err
	}
	_, err = peer.control.Write(frame)
	return err
}

func (peer *Peer) SendRawControl(payload []byte) error {
	frame, err := core.EncodeControlFrame(payload)
	if err != nil {
		return err
	}
	_, err = peer.control.Write(frame)
	return err
}

func (peer *Peer) ReceiveEnvelope() (core.Envelope, error) {
	first := []byte{0}
	if _, err := io.ReadFull(peer.control, first); err != nil {
		return core.Envelope{}, err
	}
	width := 1 << (first[0] >> 6)
	prefix := make([]byte, width)
	prefix[0] = first[0]
	if width > 1 {
		if _, err := io.ReadFull(peer.control, prefix[1:]); err != nil {
			return core.Envelope{}, err
		}
	}
	length, err := quicVarint(prefix)
	if err != nil || length < 1 || length > 65536 {
		return core.Envelope{}, errors.New("invalid control frame length")
	}
	wire := make([]byte, int(length))
	if _, err := io.ReadFull(peer.control, wire); err != nil {
		return core.Envelope{}, err
	}
	return core.DecodeEnvelope(wire)
}

func quicVarint(prefix []byte) (uint64, error) {
	if len(prefix) != 1 && len(prefix) != 2 && len(prefix) != 4 {
		return 0, errors.New("unsupported QUIC varint width")
	}
	// Decode the already-bounded prefix without importing quic-go internals.
	value := uint64(prefix[0] & 0x3f)
	for _, item := range prefix[1:] {
		value = value<<8 | uint64(item)
	}
	if (len(prefix) == 2 && value < 64) || (len(prefix) == 4 && value < 16384) || len(prefix) == 8 {
		return 0, errors.New("non-shortest QUIC varint")
	}
	return value, nil
}

func (peer *Peer) ExportKeyingMaterial(contextBytes []byte) ([]byte, error) {
	return peer.tlsState.ExportKeyingMaterial("EXPORTER-NBSR-Service-Channel-v2", contextBytes, 32)
}
func (peer *Peer) OpenApplication(ctx context.Context) (*quic.Stream, error) {
	return peer.connection.OpenStreamSync(ctx)
}

func encodeStreamCreditRefill(kind byte, channel [16]byte, epoch uint64) ([]byte, error) {
	if (kind != 1 && kind != 2) || epoch == 0 {
		return nil, errors.New("invalid stream credit refill")
	}
	wire := make([]byte, 31)
	wire[0] = 30
	copy(wire[1:5], "NSCR")
	wire[5] = 1
	wire[6] = kind
	copy(wire[7:23], channel[:])
	for index := 0; index < 8; index++ {
		wire[30-index] = byte(epoch >> (8 * index))
	}
	return wire, nil
}

func decodeStreamCreditRefill(wire []byte, kind byte) ([16]byte, uint64, error) {
	var channel [16]byte
	if len(wire) != 31 || wire[0] != 30 || string(wire[1:5]) != "NSCR" || wire[5] != 1 || wire[6] != kind {
		return channel, 0, errors.New("invalid stream credit refill")
	}
	copy(channel[:], wire[7:23])
	var epoch uint64
	for _, value := range wire[23:31] {
		epoch = epoch<<8 | uint64(value)
	}
	if epoch == 0 {
		return channel, 0, errors.New("invalid stream credit refill")
	}
	return channel, epoch, nil
}

func (peer *Peer) RefillStreamCredits(channel [16]byte, epoch uint64) error {
	request, err := encodeStreamCreditRefill(1, channel, epoch)
	if err != nil {
		return err
	}
	peer.controlMu.Lock()
	defer peer.controlMu.Unlock()
	if _, err := peer.control.Write(request); err != nil {
		return err
	}
	grant := make([]byte, 31)
	if _, err := io.ReadFull(peer.control, grant); err != nil {
		return err
	}
	gotChannel, gotEpoch, err := decodeStreamCreditRefill(grant, 2)
	if err != nil || gotChannel != channel || gotEpoch != epoch {
		return errors.New("stream credit refill grant mismatch")
	}
	return nil
}
func (peer *Peer) Close() error { peer.connection.CloseWithError(0, "done"); return nil }
