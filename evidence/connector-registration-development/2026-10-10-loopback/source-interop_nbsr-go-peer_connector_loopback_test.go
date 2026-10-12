//go:build connector_development

package connector

// This child-process harness is test-only. Its authority is explicitly synthetic.
// Private fixture material arrives on stdin and is never printed or persisted.
import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"errors"
	"fmt"
	quic "github.com/quic-go/quic-go"
	"io"
	"nbsr.local/interop/nbsr-go-peer/internal/cbor"
	"net"
	"os"
	"testing"
	"time"
)

type loopConfig struct {
	Endpoint, Case                    string
	CA, Cert, Key, ServerKey, Request []byte
}
type loopPeer struct {
	conn      *quic.Conn
	stream    *quic.Stream
	transport *quic.Transport
	socket    *net.UDPConn
	identity  [32]byte
	badExport bool
	closed    bool
	withhold  bool
	failClose bool
	lastProof []byte
}

func loopDial(c loopConfig) (*loopPeer, error) {
	// Parse before any socket operation. Literal IPv4 loopback only, never DNS.
	host, _, split := net.SplitHostPort(c.Endpoint)
	if split != nil || host != "127.0.0.1" {
		return nil, ErrInvalid
	}
	addr, err := net.ResolveUDPAddr("udp4", c.Endpoint)
	if err != nil || addr.Port == 0 {
		return nil, ErrInvalid
	}
	ca, err := x509.ParseCertificate(c.CA)
	if err != nil {
		return nil, ErrInvalid
	}
	cert, err := x509.ParseCertificate(c.Cert)
	if err != nil {
		return nil, ErrInvalid
	}
	key, err := x509.ParsePKCS8PrivateKey(c.Key)
	if err != nil {
		return nil, ErrInvalid
	}
	roots := x509.NewCertPool()
	roots.AddCert(ca)
	if c.Case == "untrusted" {
		roots = x509.NewCertPool()
	}
	alpn := ALPN
	if c.Case == "wrong_alpn" {
		alpn = "connector-deliberately-unsupported"
	}
	cfg := &tls.Config{RootCAs: roots, Certificates: []tls.Certificate{{Certificate: [][]byte{cert.Raw}, PrivateKey: key}}, ServerName: "connector-gateway.test", MinVersion: tls.VersionTLS13, MaxVersion: tls.VersionTLS13, NextProtos: []string{alpn}, SessionTicketsDisabled: true}
	cfg.VerifyConnection = func(s tls.ConnectionState) error {
		if len(s.VerifiedChains) == 0 || len(s.PeerCertificates) == 0 {
			return ErrInvalid
		}
		pub, ok := s.PeerCertificates[0].PublicKey.(ed25519.PublicKey)
		if !ok || !bytes.Equal(pub, c.ServerKey) {
			return ErrInvalid
		}
		return nil
	}
	sock, err := net.ListenUDP("udp4", &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1)})
	if err != nil {
		return nil, err
	}
	tr := &quic.Transport{Conn: sock}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	conn, err := tr.Dial(ctx, addr, cfg, &quic.Config{Versions: []quic.Version{quic.Version1}, Allow0RTT: false, MaxIncomingStreams: 0, MaxIncomingUniStreams: 0, HandshakeIdleTimeout: 2 * time.Second, MaxIdleTimeout: 5 * time.Second})
	if err != nil {
		tr.Close()
		sock.Close()
		return nil, err
	}
	state := conn.ConnectionState()
	if state.TLS.NegotiatedProtocol != ALPN || state.TLS.Version != tls.VersionTLS13 || state.Used0RTT {
		conn.CloseWithError(1, "")
		tr.Close()
		sock.Close()
		return nil, ErrInvalid
	}
	stream, err := conn.OpenStreamSync(ctx)
	if err != nil {
		conn.CloseWithError(1, "")
		tr.Close()
		sock.Close()
		return nil, err
	}
	if stream.StreamID() != 0 {
		conn.CloseWithError(1, "")
		tr.Close()
		sock.Close()
		return nil, ErrInvalid
	}
	return &loopPeer{conn: conn, stream: stream, transport: tr, socket: sock, identity: sha256.Sum256(c.ServerKey), badExport: c.Case == "bad_exporter"}, nil
}
func (p *loopPeer) Protocol() string   { return ALPN }
func (p *loopPeer) Identity() [32]byte { return p.identity }
func (p *loopPeer) Export(label string, ctx []byte) ([32]byte, error) {
	if label != ExporterLabel {
		return [32]byte{}, ErrInvalid
	}
	if p.badExport {
		ctx = append(append([]byte{}, ctx...), 0)
	}
	state := p.conn.ConnectionState().TLS
	raw, err := state.ExportKeyingMaterial(label, ctx, 32)
	var out [32]byte
	copy(out[:], raw)
	return out, err
}
func frame(raw []byte) []byte {
	n := len(raw)
	if n < 64 {
		return append([]byte{byte(n)}, raw...)
	}
	if n < 16384 {
		return append([]byte{byte(n>>8) | 64, byte(n)}, raw...)
	}
	return append([]byte{128 | byte(n>>24), byte(n >> 16), byte(n >> 8), byte(n)}, raw...)
}
func (p *loopPeer) Exchange(raw []byte) ([]byte, error) {
	if len(raw) == 0 || len(raw) > 65536 {
		return nil, ErrInvalid
	}
	p.stream.SetDeadline(time.Now().Add(5 * time.Second))
	decoded, _ := Decode(ALPN, raw)
	if decoded.Kind == Proof {
		p.lastProof = append([]byte{}, raw...)
	}
	if !(p.withhold && decoded.Kind == Proof) {
		if _, err := p.stream.Write(frame(raw)); err != nil {
			return nil, err
		}
	}
	var first [1]byte
	if _, err := io.ReadFull(p.stream, first[:]); err != nil {
		return nil, err
	}
	width := 1 << (first[0] >> 6)
	if width == 8 {
		return nil, ErrInvalid
	}
	prefix := make([]byte, width)
	prefix[0] = first[0]
	if _, err := io.ReadFull(p.stream, prefix[1:]); err != nil {
		return nil, err
	}
	n := int(prefix[0] & 63)
	for _, v := range prefix[1:] {
		n = n<<8 | int(v)
	}
	if n < 1 || n > 65536 || (width == 2 && n < 64) || (width == 4 && n < 16384) {
		return nil, ErrInvalid
	}
	out := make([]byte, n)
	_, err := io.ReadFull(p.stream, out)
	return out, err
}
func (p *loopPeer) Close() error {
	if p.failClose {
		p.failClose = false
		return errors.New("injected close failure before transport shutdown")
	}
	if p.closed {
		return nil
	}
	p.stream.CancelRead(0)
	p.stream.CancelWrite(0)
	if err := p.conn.CloseWithError(0, ""); err != nil {
		return err
	}
	// quic.Transport.Close waits for its reader loop; explicit socket ownership
	// remains here. Only after both complete may Coordinator release its owner.
	if err := p.transport.Close(); err != nil {
		return err
	}
	if err := p.socket.Close(); err != nil && !errors.Is(err, net.ErrClosed) {
		return err
	}
	probe, err := net.ListenUDP("udp4", p.socket.LocalAddr().(*net.UDPAddr))
	if err != nil {
		return err
	}
	if err = probe.Close(); err != nil {
		return err
	}
	p.closed = true
	fmt.Printf("loopback_socket_released=%s\n", p.socket.LocalAddr())
	return nil
}

type loopDialer struct{ p *loopPeer }

func (d loopDialer) Dial() (Peer, error) { return d.p, nil }

type loopAuthority struct {
	expected [32]byte
	template map[uint64]any
}

func (a loopAuthority) Check(p Peer, e Envelope, now uint64) (uint64, error) {
	if p.Identity() != a.expected || p.Protocol() != ALPN || now != 100 || e.Kind != Request {
		return 0, ErrInvalid
	}
	for _, k := range []uint64{0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14} {
		x, _ := cbor.Encode(a.template[k])
		y, _ := cbor.Encode(e.Body[k])
		if !bytes.Equal(x, y) {
			return 0, ErrInvalid
		}
	}
	return 1000, nil // Explicit synthetic receipt; no purpose/chain authentication.
}
func TestDevelopmentLoopbackProcess(t *testing.T) {
	if os.Getenv("NBSR_CONNECTOR_LOOPBACK") != "1" {
		t.Skip("explicit parent-only loopback harness")
	}
	var cfg loopConfig
	if json.NewDecoder(io.LimitReader(os.Stdin, 128*1024)).Decode(&cfg) != nil {
		t.Fatal("invalid private fixture input")
	}
	p, err := loopDial(cfg)
	if cfg.Case == "untrusted" || cfg.Case == "wrong_alpn" || cfg.Case == "wrong_server_key" {
		if err == nil {
			p.Close()
			t.Fatal("TLS negative accepted")
		}
		return
	}
	if err != nil {
		if cfg.Case == "wrong_peer" {
			return
		}
		t.Fatal("loopback dial failed")
	}
	defer func() {
		if p.Close() != nil {
			t.Error("cleanup failed")
		}
	}()
	env, err := Decode(ALPN, cfg.Request)
	if err != nil {
		t.Fatal("request fixture")
	}
	body := env.Body
	expected := sha256.Sum256(cfg.ServerKey)
	clock := &fixtureClock{now: 100}
	c, err := NewCoordinator(clock, loopAuthority{expected, body}, expected, env.SessionID, body)
	if err != nil {
		t.Fatal("coordinator setup")
	}
	if c.Connect(loopDialer{p}) != nil {
		t.Fatal("coordinator connect")
	}
	p.withhold = cfg.Case == "withheld_proof"
	err = c.Begin(body)
	positive := cfg.Case == "positive" || cfg.Case == "duplicate" || cfg.Case == "cross_session" || cfg.Case == "failed_close" || cfg.Case == "cancel_io"
	negative := !positive && cfg.Case != "replay" && cfg.Case != "deny_new" && cfg.Case != "terminate"
	if negative {
		if err == nil || c.Owner() != nil {
			t.Fatal("negative registration accepted")
		}
		if c.Close() != nil {
			t.Fatal("negative cleanup")
		}
		return
	}
	if err != nil || c.Owner() == nil {
		t.Fatal("registration failed")
	}
	before := *c.Owner()
	if cfg.Case == "duplicate" || cfg.Case == "cross_session" {
		second, e := loopDial(cfg)
		if e != nil {
			t.Fatal("second loopback dial")
		}
		defer second.Close()
		raw := p.lastProof
		if cfg.Case == "duplicate" {
			copy(env.SessionID[:], bytes.Repeat([]byte{'t'}, 16))
			copy(env.RequestID[:8], env.SessionID[:8])
			raw, e = Encode(env)
			if e != nil {
				t.Fatal("duplicate request")
			}
		}
		if _, e = second.Exchange(raw); e == nil {
			t.Fatal("second registration/replay accepted")
		}
		if second.Close() != nil {
			t.Fatal("second cleanup")
		}
	}
	if cfg.Case == "failed_close" {
		p.failClose = true
		if c.Close() == nil || c.Owner() == nil || c.Owner().Eligible || p.closed {
			t.Fatal("failed cleanup released ownership")
		}
	}
	if cfg.Case == "cancel_io" {
		// The worker may be cancelled before Read blocks. This proves join and
		// ownership retention, not a scheduling claim about an already-blocked read.
		done := make(chan error, 1)
		started := make(chan struct{})
		go func() { close(started); var b [1]byte; _, e := p.stream.Read(b[:]); done <- e }()
		<-started
		p.stream.CancelRead(7)
		select {
		case e := <-done:
			if e == nil {
				t.Fatal("cancelled read succeeded")
			}
		case <-time.After(5 * time.Second):
			t.Fatal("I/O worker not joined")
		}
		if c.Owner() == nil {
			t.Fatal("cancelled read released owner")
		}
	}
	if cfg.Case == "replay" {
		_, err = p.Exchange(cfg.Request)
		if err == nil {
			t.Fatal("old directional sequence accepted")
		}
	}
	if cfg.Case == "positive" || cfg.Case == "deny_new" || cfg.Case == "terminate" {
		body[1] = "renew"
		body[15] = before.Digest[:]
		err = c.Begin(body)
		if cfg.Case == "positive" {
			if err != nil || c.Owner() == nil || c.Owner().Registration != before.Registration {
				t.Fatal("same-connection renewal failed")
			}
		} else if err == nil {
			t.Fatal("invalidated renewal accepted")
		}
	}
	if positive {
		if p.stream.Close() != nil {
			t.Fatal("completion FIN")
		}
		select {
		case <-p.conn.Context().Done():
		case <-time.After(5 * time.Second):
			t.Fatal("server cleanup confirmation deadline")
		}
	}
	if c.Close() != nil || c.Owner() != nil || !p.closed {
		t.Fatal("confirmed cleanup required")
	}
}
