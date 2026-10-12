//go:build connector_development

package connector

import (
	"bytes"
	"crypto/sha256"
	"encoding/binary"
	"errors"
	"nbsr.local/interop/nbsr-go-peer/internal/cbor"
)

// All interfaces in this package are DEVELOPMENT fixtures, not live trust APIs.
// No runtime imports this build-tagged package. There is no default verifier.
type Clock interface {
	Now() uint64
	AdvanceBackoff(seconds uint64) error
}
type Peer interface {
	Protocol() string
	Identity() [32]byte
	Exchange([]byte) ([]byte, error)
	Export(string, []byte) ([32]byte, error)
	Close() error
}
type Dialer interface{ Dial() (Peer, error) }
type Authority interface {
	Check(Peer, Envelope, uint64) (uint64, error)
}
type Owner struct {
	Registration, Epoch [16]byte
	Generation, Expires uint64
	Digest              [32]byte
	Eligible            bool
}
type pending struct {
	request                     Envelope
	deadline, authorityDeadline uint64
	challenge                   map[uint64]any
	proofSent                   bool
}
type Coordinator struct {
	clock                   Clock
	authority               Authority
	expected                [32]byte
	session                 [16]byte
	peer                    Peer
	template                map[uint64]any
	high, tx, rx            uint64
	pending                 *pending
	owner                   *Owner
	connectStarted, stopped bool
	attemptDeadline         uint64
}

func NewCoordinator(clock Clock, authority Authority, expected [32]byte, session [16]byte, template map[uint64]any) (*Coordinator, error) {
	if clock == nil || authority == nil || expected == [32]byte{} || session == [16]byte{} || !bodyValid(Request, template) {
		return nil, ErrInvalid
	}
	raw, _ := cbor.Encode(template)
	v, err := cbor.DecodeExact(raw, cbor.DefaultLimits())
	if err != nil {
		return nil, ErrInvalid
	}
	return &Coordinator{clock: clock, authority: authority, expected: expected, session: session, template: v.(map[uint64]any)}, nil
}
func (c *Coordinator) Owner() *Owner {
	if c.owner == nil {
		return nil
	}
	v := *c.owner
	v.Eligible = v.Eligible && !c.stopped && c.clock.Now() < v.Expires
	return &v
}
func (c *Coordinator) Connect(d Dialer) error {
	if c.peer != nil || c.connectStarted || c.stopped || d == nil {
		return errors.New("owned connection requires cleanup")
	}
	c.connectStarted = true
	for attempt := 0; attempt < 3; attempt++ {
		p, err := d.Dial()
		if p != nil {
			c.peer = p
			if err != nil {
				if closeErr := c.closePeer(); closeErr != nil {
					c.stopped = true
					return closeErr
				}
			}
		}
		if err == nil && p == nil {
			return ErrInvalid
		}
		if err == nil {
			if p.Protocol() != ALPN || p.Identity() != c.expected {
				if closeErr := c.Close(); closeErr != nil {
					return closeErr
				}
				return ErrInvalid
			}
			if c.clock.Now() > 253402300794 {
				if err := c.Close(); err != nil {
					return err
				}
				return ErrInvalid
			}
			c.attemptDeadline = c.clock.Now() + 5
			return nil
		}
		if attempt < 2 {
			if err = c.clock.AdvanceBackoff(uint64(attempt + 1)); err != nil {
				return err
			}
		}
	}
	return errors.New("connect attempt budget exhausted")
}
func (c *Coordinator) next(kind uint64, body map[uint64]any, rid [16]byte) ([]byte, error) {
	if c.tx == ^uint64(0) {
		return nil, ErrInvalid
	}
	c.tx++
	return Encode(Envelope{kind, rid, c.session, c.tx, body})
}
func (c *Coordinator) live() bool {
	return !c.stopped && c.peer != nil && c.peer.Protocol() == ALPN && c.peer.Identity() == c.expected
}
func (c *Coordinator) Begin(body map[uint64]any) error {
	if !c.live() || c.pending != nil || c.high == ^uint64(0) || !bodyValid(Request, body) {
		return ErrInvalid
	}
	for _, k := range []uint64{2, 3, 4, 5, 6, 7, 8, 12} {
		a, _ := cbor.Encode(body[k])
		b, _ := cbor.Encode(c.template[k])
		if !bytes.Equal(a, b) {
			return ErrInvalid
		}
	}
	now := c.clock.Now()
	if now > 253402300794 || body[14] != now || (c.owner == nil && now >= c.attemptDeadline) {
		return ErrInvalid
	}
	if body[1] == "register" {
		if c.owner != nil {
			return ErrInvalid
		}
	} else {
		if c.owner == nil || !c.owner.Eligible || now >= c.owner.Expires || !bytes.Equal(body[15].([]byte), c.owner.Digest[:]) {
			return ErrInvalid
		}
	}
	rid := [16]byte{}
	copy(rid[:8], c.session[:8])
	binary.BigEndian.PutUint64(rid[8:], c.high+1)
	raw, err := Encode(Envelope{Request, rid, c.session, 1, body})
	if err != nil {
		return err
	}
	request, err := Decode(ALPN, raw)
	if err != nil {
		return err
	}
	expires, err := c.authority.Check(c.peer, request, now)
	if err != nil || expires <= now || expires > 253402300799 {
		if c.owner != nil {
			c.owner.Eligible = false
		}
		return ErrInvalid
	}
	deadline := now + 5
	if expires < deadline {
		deadline = expires
	}
	if c.owner != nil && c.owner.Expires < deadline {
		deadline = c.owner.Expires
	}
	if c.owner == nil && c.attemptDeadline < deadline {
		deadline = c.attemptDeadline
	}
	c.high++
	c.pending = &pending{request: request, deadline: deadline, authorityDeadline: expires}
	return c.Retry()
}
func (c *Coordinator) receive(raw []byte) (Envelope, error) {
	e, err := Decode(c.peer.Protocol(), raw)
	if err != nil {
		return e, err
	}
	p := c.pending
	if p == nil || e.SessionID != c.session || e.RequestID != p.request.RequestID || e.Sequence <= c.rx {
		return Envelope{}, ErrInvalid
	}
	c.rx = e.Sequence
	return e, nil
}
func (c *Coordinator) validPending() bool {
	return c.pending != nil && c.live() && c.clock.Now() < c.pending.deadline && (c.owner == nil || (c.owner.Eligible && c.clock.Now() < c.owner.Expires))
}
func (c *Coordinator) Retry() error {
	if !c.validPending() {
		return ErrInvalid
	}
	p := c.pending
	expires, err := c.authority.Check(c.peer, p.request, c.clock.Now())
	if err != nil || expires < c.pending.authorityDeadline || expires > 253402300799 {
		if c.owner != nil {
			c.owner.Eligible = false
		}
		return ErrInvalid
	}
	if !c.validPending() {
		return ErrInvalid
	}
	raw, err := c.next(Request, p.request.Body, p.request.RequestID)
	if err != nil {
		return err
	}
	response, err := c.peer.Exchange(raw)
	if err != nil {
		return err
	}
	if !c.validPending() {
		return ErrInvalid
	}
	e, err := c.receive(response)
	if err != nil {
		return err
	}
	if e.Kind == Reject {
		return c.reject(e)
	}
	if e.Kind == Accept {
		if !p.proofSent {
			return ErrInvalid
		}
		return c.accept(e)
	}
	if e.Kind != Challenge {
		return ErrInvalid
	}
	requestBytes, _ := cbor.Encode(p.request.Body)
	digest := sha256.Sum256(requestBytes)
	if !bytes.Equal(e.Body[1].([]byte), digest[:]) || e.Body[3].(uint64) > p.deadline || e.Body[3].(uint64) <= c.clock.Now() {
		return ErrInvalid
	}
	if p.challenge != nil {
		before, _ := cbor.Encode(p.challenge)
		after, _ := cbor.Encode(e.Body)
		if !bytes.Equal(before, after) {
			return ErrInvalid
		}
	} else {
		p.challenge = e.Body
		p.deadline = e.Body[3].(uint64)
	}
	b := p.request.Body
	context, _ := cbor.Encode([]any{"NBSR-CONNECTOR-REGISTRATION-CONTEXT-v1", uint64(1), c.session[:], p.request.RequestID[:], digest[:], e.Body[2], b[4], b[5], b[6], b[8], b[12]})
	proof, err := c.peer.Export(ExporterLabel, context)
	if err != nil || !c.validPending() {
		return ErrInvalid
	}
	raw, err = c.next(Proof, map[uint64]any{0: uint64(1), 1: digest[:], 2: e.Body[2], 3: proof[:]}, p.request.RequestID)
	if err != nil {
		return err
	}
	p.proofSent = true // Exchange may fail after the peer commits; retry keeps this correlation.
	response, err = c.peer.Exchange(raw)
	if err != nil {
		return err
	}
	if !c.validPending() {
		return ErrInvalid
	}
	e, err = c.receive(response)
	if err != nil {
		return err
	}
	if e.Kind == Reject {
		return c.reject(e)
	}
	return c.accept(e)
}
func (c *Coordinator) accept(e Envelope) error {
	if e.Kind != Accept || !c.validPending() {
		return ErrInvalid
	}
	p := c.pending
	b := e.Body
	req := p.request.Body
	raw, _ := cbor.Encode(req)
	h := sha256.Sum256(raw)
	now := c.clock.Now()
	if !bytes.Equal(b[1].([]byte), h[:]) || !bytes.Equal(b[8].([]byte), req[11].([]byte)) || !bytes.Equal(b[9].([]byte), req[12].([]byte)) || b[5].(uint64) > now || b[6].(uint64) <= now || b[6].(uint64) > p.authorityDeadline || b[6].(uint64)-b[5].(uint64) > req[13].(uint64) {
		return ErrInvalid
	}
	expires, err := c.authority.Check(c.peer, p.request, now)
	if err != nil || expires < b[6].(uint64) || expires > 253402300799 || !c.validPending() || c.clock.Now() >= b[6].(uint64) {
		if c.owner != nil {
			c.owner.Eligible = false
		}
		return ErrInvalid
	}
	var o Owner
	copy(o.Registration[:], b[2].([]byte))
	copy(o.Epoch[:], b[3].([]byte))
	o.Generation = b[4].(uint64)
	o.Expires = b[6].(uint64)
	o.Eligible = true
	if c.owner != nil && (o.Registration != c.owner.Registration || o.Epoch != c.owner.Epoch || o.Generation != c.owner.Generation) {
		return ErrInvalid
	}
	raw, _ = cbor.Encode([]any{"NBSR-CONNECTOR-ACCEPT-DIGEST-v1", uint64(1), c.session[:], p.request.RequestID[:], b})
	o.Digest = sha256.Sum256(raw)
	c.owner = &o
	c.pending = nil
	return nil
}
func (c *Coordinator) reject(e Envelope) error {
	raw, _ := cbor.Encode(c.pending.request.Body)
	digest := sha256.Sum256(raw)
	if bytes.Equal(e.Body[1].([]byte), digest[:]) {
		c.pending = nil
	}
	return ErrInvalid
}
func (c *Coordinator) Withdraw() error {
	if !c.live() || c.owner == nil {
		return ErrInvalid
	}
	o := c.owner
	o.Eligible = false
	c.pending = nil
	rid := [16]byte{}
	copy(rid[:8], c.session[:8])
	binary.BigEndian.PutUint64(rid[8:], c.high)
	raw, err := c.next(Withdraw, map[uint64]any{0: uint64(1), 1: o.Registration[:], 2: o.Epoch[:], 3: o.Generation, 4: o.Digest[:]}, rid)
	if err != nil {
		return err
	}
	if _, err = c.peer.Exchange(raw); err != nil {
		return err
	}
	return c.Close()
}
func (c *Coordinator) Close() error {
	c.stopped = true
	c.pending = nil
	if c.owner != nil {
		c.owner.Eligible = false
	}
	return c.closePeer()
}
func (c *Coordinator) closePeer() error {
	if c.peer == nil {
		return nil
	}
	if err := c.peer.Close(); err != nil {
		return err
	}
	c.peer = nil
	c.owner = nil
	c.pending = nil
	return nil
}

// Poll is explicit fixture-time cleanup, not an asynchronous runtime deadline.
func (c *Coordinator) Poll() error {
	now := c.clock.Now()
	if c.stopped || now > 253402300799 || (c.pending != nil && now >= c.pending.deadline) || (c.owner != nil && now >= c.owner.Expires) || (c.peer != nil && c.owner == nil && now >= c.attemptDeadline) {
		return c.Close()
	}
	return nil
}
