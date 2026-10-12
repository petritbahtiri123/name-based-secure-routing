//go:build connector_development

package connector

import (
	"bytes"
	"crypto/sha256"
	"encoding/binary"
	"errors"
	"nbsr.local/interop/nbsr-go-peer/internal/cbor"
	"os"
	"testing"
)

// Synthetic fixtures: no TLS, cryptographic authority verification or I/O.
type fixtureClock struct {
	now   uint64
	waits []uint64
}

func (f *fixtureClock) Now() uint64 { return f.now }
func (f *fixtureClock) AdvanceBackoff(s uint64) error {
	f.waits = append(f.waits, s)
	f.now += s
	return nil
}

type fixtureAuthority struct {
	calls  int
	denyAt int
	expiry uint64
	after  func(int)
}

func (f *fixtureAuthority) Check(p Peer, e Envelope, now uint64) (uint64, error) {
	f.calls++
	if f.after != nil {
		f.after(f.calls)
	}
	if f.calls == f.denyAt {
		return 0, errors.New("explicit fixture authority denial")
	}
	return f.expiry, nil
}

type fixtureDialer struct {
	peer            Peer
	failures, calls int
	partial         bool
}

func (f *fixtureDialer) Dial() (Peer, error) {
	f.calls++
	if f.calls <= f.failures {
		if f.partial {
			return f.peer, errors.New("partial fixture dial")
		}
		return nil, errors.New("fixture dial")
	}
	return f.peer, nil
}

type fixturePeer struct {
	clock                                        *fixtureClock
	protocol                                     string
	identity                                     [32]byte
	sequence                                     uint64
	request                                      Envelope
	challenge, accepted                          map[uint64]any
	seen                                         []Envelope
	closes                                       int
	failClose, dropAccept, badProof, earlyAccept bool
	mutate                                       func(*Envelope)
	after                                        func(uint64)
}

func (f *fixturePeer) Protocol() string   { return f.protocol }
func (f *fixturePeer) Identity() [32]byte { return f.identity }
func fixtureExport(label string, context []byte) [32]byte {
	return sha256.Sum256(append(append([]byte("EXPLICIT NON-TLS TEST FIXTURE"), []byte(label)...), context...))
}
func (f *fixturePeer) Export(label string, context []byte) ([32]byte, error) {
	if label != ExporterLabel {
		return [32]byte{}, ErrInvalid
	}
	p := fixtureExport(label, context)
	if f.badProof {
		p[0] ^= 1
	}
	return p, nil
}
func (f *fixturePeer) Close() error {
	f.closes++
	if f.failClose {
		return errors.New("fixture cleanup failed")
	}
	return nil
}
func (f *fixturePeer) acceptBody() map[uint64]any {
	b := f.request.Body
	return map[uint64]any{0: uint64(1), 1: f.challenge[1], 2: bytes.Repeat([]byte{3}, 16), 3: bytes.Repeat([]byte{4}, 16), 4: uint64(1), 5: f.clock.now, 6: f.clock.now + b[13].(uint64), 7: f.clock.now + b[13].(uint64)/2, 8: b[11], 9: b[12]}
}
func (f *fixturePeer) Exchange(raw []byte) ([]byte, error) {
	e, err := Decode(ALPN, raw)
	if err != nil {
		return nil, err
	}
	f.seen = append(f.seen, e)
	kind := Challenge
	var body map[uint64]any
	switch e.Kind {
	case Request:
		old, _ := cbor.Encode(f.request.Body)
		next, _ := cbor.Encode(e.Body)
		if f.request.RequestID == e.RequestID {
			if !bytes.Equal(old, next) {
				return nil, ErrInvalid
			}
			if f.accepted != nil {
				kind = Accept
				body = f.accepted
			} else {
				body = f.challenge
			}
		} else {
			if binary.BigEndian.Uint64(e.RequestID[8:]) != binary.BigEndian.Uint64(f.request.RequestID[8:])+1 {
				return nil, errors.New("fixture counter gap")
			}
			f.request = e
			f.accepted = nil
			digest := sha256.Sum256(next)
			f.challenge = map[uint64]any{0: uint64(1), 1: digest[:], 2: bytes.Repeat([]byte{9}, 32), 3: f.clock.now + 5}
			body = f.challenge
		}
		if f.earlyAccept {
			kind = Accept
			body = f.acceptBody()
		}
	case Proof:
		b := f.request.Body
		context, _ := cbor.Encode([]any{"NBSR-CONNECTOR-REGISTRATION-CONTEXT-v1", uint64(1), e.SessionID[:], e.RequestID[:], f.challenge[1], f.challenge[2], b[4], b[5], b[6], b[8], b[12]})
		expected := fixtureExport(ExporterLabel, context)
		if !bytes.Equal(e.Body[3].([]byte), expected[:]) {
			return nil, errors.New("fixture exporter mismatch")
		}
		f.accepted = f.acceptBody()
		kind = Accept
		body = f.accepted
		if f.dropAccept {
			f.dropAccept = false
			return nil, errors.New("fixture lost ACCEPT")
		}
	case Withdraw:
		return nil, nil
	default:
		return nil, ErrInvalid
	}
	f.sequence++
	response := Envelope{kind, e.RequestID, e.SessionID, f.sequence, body}
	if f.mutate != nil {
		f.mutate(&response)
	}
	if f.after != nil {
		f.after(e.Kind)
	}
	return Encode(response)
}
func fixtureRequest(t *testing.T) map[uint64]any {
	t.Helper()
	raw, err := os.ReadFile("../../../vectors/connector-registration-development-v1/request.cbor")
	if err != nil {
		t.Fatal(err)
	}
	e, err := Decode(ALPN, raw)
	if err != nil {
		t.Fatal(err)
	}
	return e.Body
}
func fixtureSetup(t *testing.T) (*Coordinator, *fixturePeer, *fixtureClock, *fixtureAuthority) {
	t.Helper()
	clock := &fixtureClock{now: 100}
	authority := &fixtureAuthority{expiry: 1000}
	peer := &fixturePeer{clock: clock, protocol: ALPN, identity: [32]byte{1}}
	c, err := NewCoordinator(clock, authority, peer.identity, [16]byte{1}, fixtureRequest(t))
	if err != nil {
		t.Fatal(err)
	}
	if err = c.Connect(&fixtureDialer{peer: peer}); err != nil {
		t.Fatal(err)
	}
	return c, peer, clock, authority
}
func TestRegistrationRenewalLostAcceptAndWithdraw(t *testing.T) {
	c, p, clock, _ := fixtureSetup(t)
	p.dropAccept = true
	if c.Begin(fixtureRequest(t)) == nil {
		t.Fatal("expected lost response")
	}
	if c.Owner() != nil {
		t.Fatal("unconfirmed owner")
	}
	if err := c.Retry(); err != nil {
		t.Fatal(err)
	}
	initial := *c.Owner()
	if len(p.seen) != 3 || p.seen[0].RequestID != p.seen[2].RequestID || p.seen[2].Sequence <= p.seen[0].Sequence {
		t.Fatal("retry identity/sequence")
	}
	for i := 0; i < 9; i++ {
		clock.now++
		b := fixtureRequest(t)
		b[1] = "renew"
		b[14] = clock.now
		o := c.Owner()
		b[15] = o.Digest[:]
		if err := c.Begin(b); err != nil {
			t.Fatal(err)
		}
		if c.Owner().Registration != initial.Registration || c.Owner().Generation != initial.Generation {
			t.Fatal("owner changed")
		}
	}
	p.failClose = true
	if c.Withdraw() == nil {
		t.Fatal("cleanup failure hidden")
	}
	if c.Owner() == nil || c.Owner().Eligible {
		t.Fatal("failed cleanup lost ownership")
	}
	p.failClose = false
	if err := c.Close(); err != nil {
		t.Fatal(err)
	}
	if c.Owner() != nil {
		t.Fatal("confirmed cleanup retained owner")
	}
}
func TestPreSendDenialDoesNotConsumeCounter(t *testing.T) {
	c, p, _, a := fixtureSetup(t)
	a.denyAt = 1
	if c.Begin(fixtureRequest(t)) == nil {
		t.Fatal("authority denial accepted")
	}
	if len(p.seen) != 0 {
		t.Fatal("sent denied request")
	}
	a.denyAt = 0
	if err := c.Begin(fixtureRequest(t)); err != nil {
		t.Fatal(err)
	}
	if binary.BigEndian.Uint64(p.seen[0].RequestID[8:]) != 1 {
		t.Fatal("local rejection consumed wire counter")
	}
}
func TestClosedCoordinatorRequiresNewSession(t *testing.T) {
	c, p, _, _ := fixtureSetup(t)
	if err := c.Close(); err != nil {
		t.Fatal(err)
	}
	d := &fixtureDialer{peer: p}
	if c.Connect(d) == nil || d.calls != 0 {
		t.Fatal("reused closed session")
	}
}
func TestConnectBudgetPinsAndCleanup(t *testing.T) {
	for _, mode := range []string{"budget", "alpn", "identity", "failed-cleanup"} {
		t.Run(mode, func(t *testing.T) {
			_, p, clock, a := fixtureSetup(t)
			c, err := NewCoordinator(clock, a, p.identity, [16]byte{2}, fixtureRequest(t))
			if err != nil {
				t.Fatal(err)
			}
			d := &fixtureDialer{peer: p}
			switch mode {
			case "budget":
				d.failures = 3
			case "alpn":
				p.protocol = "nbsr-quic-1"
			case "identity":
				p.identity = [32]byte{9}
			case "failed-cleanup":
				d.failures = 1
				d.partial = true
				p.failClose = true
			}
			if c.Connect(d) == nil {
				t.Fatal("invalid connection accepted")
			}
			if mode == "budget" {
				if d.calls != 3 || len(clock.waits) != 2 {
					t.Fatal("unbounded budget")
				}
			} else if d.calls != 1 {
				t.Fatal("retried pin failure")
			}
			if mode == "failed-cleanup" && c.peer == nil {
				t.Fatal("lost failed connection ownership")
			}
		})
	}
}
func TestResponseAndAuthorityFailuresNeverInstallOwner(t *testing.T) {
	for _, mode := range []string{"digest", "session", "request-id", "sequence", "dependency", "policy", "deadline", "late", "authority", "proof", "generation", "early-accept"} {
		t.Run(mode, func(t *testing.T) {
			c, p, clock, a := fixtureSetup(t)
			if mode == "authority" {
				a.denyAt = 3
			}
			if mode == "proof" {
				p.badProof = true
			}
			if mode == "late" {
				p.after = func(uint64) { clock.now = 105 }
			}
			p.earlyAccept = mode == "early-accept"
			p.mutate = func(e *Envelope) {
				switch mode {
				case "digest":
					e.Body[1] = make([]byte, 32)
				case "session":
					e.SessionID[15] ^= 1
				case "request-id":
					e.RequestID[15]++
				case "sequence":
					e.Sequence = 1
				case "dependency":
					if e.Kind == Accept {
						e.Body[8] = make([]byte, 32)
					}
				case "policy":
					if e.Kind == Accept {
						e.Body[9] = make([]byte, 32)
					}
				case "deadline":
					if e.Kind == Challenge {
						e.Body[3] = uint64(106)
					}
				case "generation":
					if e.Kind == Accept {
						e.Body[4] = uint64(0)
					}
				}
			}
			if c.Begin(fixtureRequest(t)) == nil {
				t.Fatal("fault accepted")
			}
			if c.Owner() != nil {
				t.Fatal("invalid owner installed")
			}
		})
	}
}
func TestPendingExpiryAndCounterExhaustion(t *testing.T) {
	c, p, clock, _ := fixtureSetup(t)
	p.dropAccept = true
	_ = c.Begin(fixtureRequest(t))
	clock.now = 105
	before := len(p.seen)
	if c.Retry() == nil || len(p.seen) != before {
		t.Fatal("expired retry sent")
	}
	c, p, _, _ = fixtureSetup(t)
	c.high = ^uint64(0)
	if c.Begin(fixtureRequest(t)) == nil || len(p.seen) != 0 {
		t.Fatal("counter wrapped")
	}
	c, p, _, _ = fixtureSetup(t)
	c.tx = ^uint64(0)
	if c.Begin(fixtureRequest(t)) == nil || len(p.seen) != 0 {
		t.Fatal("sequence wrapped")
	}
}
func TestOwnerExpiryIsVisible(t *testing.T) {
	c, _, clock, _ := fixtureSetup(t)
	if err := c.Begin(fixtureRequest(t)); err != nil {
		t.Fatal(err)
	}
	clock.now = c.Owner().Expires
	if c.Owner().Eligible {
		t.Fatal("expired owner eligible")
	}
}

func TestAuthorityCallbackCannotInstallExpiredAcceptance(t *testing.T) {
	c, _, clock, a := fixtureSetup(t)
	a.after = func(call int) {
		if call == 3 {
			clock.now = 102
		}
	}
	b := fixtureRequest(t)
	b[13] = uint64(1)
	if c.Begin(b) == nil {
		t.Fatal("expired acceptance installed after authority callback")
	}
	if c.Owner() != nil {
		t.Fatal("expired owner retained as accepted")
	}
}

func TestExplicitCancellationBlocksProofRecoveryEvenBeforeDeadline(t *testing.T) {
	c, p, _, _ := fixtureSetup(t)
	p.dropAccept = true
	_ = c.Begin(fixtureRequest(t))
	p.failClose = true
	if c.Close() == nil {
		t.Fatal("expected cleanup failure")
	}
	before := len(p.seen)
	if c.Retry() == nil || len(p.seen) != before {
		t.Fatal("cancelled operation resumed")
	}
	p.failClose = false
	if err := c.Close(); err != nil {
		t.Fatal(err)
	}
}

func TestPollAndFailedCancellationRetainOwnedResources(t *testing.T) {
	for _, registered := range []bool{false, true} {
		t.Run(map[bool]string{false: "pending", true: "registered"}[registered], func(t *testing.T) {
			c, p, clock, _ := fixtureSetup(t)
			if registered {
				if err := c.Begin(fixtureRequest(t)); err != nil {
					t.Fatal(err)
				}
				clock.now = c.Owner().Expires
			} else {
				p.dropAccept = true
				_ = c.Begin(fixtureRequest(t))
				clock.now = 105
			}
			p.failClose = true
			if c.Poll() == nil {
				t.Fatal("failed close hidden")
			}
			if c.peer == nil {
				t.Fatal("lost ownership")
			}
			before := len(p.seen)
			if c.Retry() == nil || len(p.seen) != before {
				t.Fatal("cancelled proof resumed")
			}
			if registered && (c.Owner() == nil || c.Owner().Eligible) {
				t.Fatal("failed cleanup lost owner or eligibility")
			}
			p.failClose = false
			if err := c.Poll(); err != nil {
				t.Fatal(err)
			}
			if c.peer != nil || c.Owner() != nil {
				t.Fatal("cleanup incomplete")
			}
		})
	}
}
func TestRenewalCannotChangeHandleOrResurrectExpiry(t *testing.T) {
	for _, mode := range []string{"handle", "expired", "denied"} {
		t.Run(mode, func(t *testing.T) {
			c, p, clock, a := fixtureSetup(t)
			if err := c.Begin(fixtureRequest(t)); err != nil {
				t.Fatal(err)
			}
			old := *c.Owner()
			clock.now++
			b := fixtureRequest(t)
			b[1] = "renew"
			b[15] = old.Digest[:]
			if mode == "expired" {
				clock.now = old.Expires
			}
			b[14] = clock.now
			if mode == "denied" {
				a.denyAt = a.calls + 3
			}
			if mode == "handle" {
				p.mutate = func(e *Envelope) {
					if e.Kind == Accept {
						e.Body[2] = bytes.Repeat([]byte{8}, 16)
					}
				}
			}
			if c.Begin(b) == nil {
				t.Fatal("invalid renewal succeeded")
			}
			if c.Owner() == nil || c.Owner().Digest != old.Digest {
				t.Fatal("ownership changed")
			}
			if mode != "handle" && c.Owner().Eligible {
				t.Fatal("invalid authority resurrected")
			}
		})
	}
}
