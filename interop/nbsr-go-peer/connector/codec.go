//go:build connector_development

package connector

import (
	"bytes"
	"crypto/sha256"
	"encoding/binary"
	"errors"
	"regexp"

	"nbsr.local/interop/nbsr-go-peer/internal/cbor"
)

const Profile = "connector-registration-development-v1"
const ALPN = "nbsr-connector-dev-1"
const ExporterLabel = "EXPORTER-NBSR-Connector-Registration-v1"
const RegisterAction uint64 = 24576 // Connector-local namespace only; not global authority.
const Request uint64 = 24576
const Challenge uint64 = 24577
const Proof uint64 = 24578
const Accept uint64 = 24579
const Reject uint64 = 24580
const Withdraw uint64 = 24581

var ErrInvalid = errors.New("connector development input rejected")
var textID = regexp.MustCompile(`^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$`)

// Envelope is data, never proof of authentication or authorization.
type Envelope struct {
	Kind                 uint64
	RequestID, SessionID [16]byte
	Sequence             uint64
	Body                 map[uint64]any
}

func unsigned(x any, lo, hi uint64) bool { n, ok := x.(uint64); return ok && n >= lo && n <= hi }
func blob(x any, size int, nonzero bool) bool {
	b, ok := x.([]byte)
	return ok && len(b) == size && (!nonzero || !bytes.Equal(b, make([]byte, size)))
}
func text(x any) bool {
	s, ok := x.(string)
	return ok && len(s) >= 1 && len(s) <= 64 && textID.MatchString(s)
}
func exact(m map[uint64]any, n int) bool {
	if len(m) != n {
		return false
	}
	for i := 0; i < n; i++ {
		if _, ok := m[uint64(i)]; !ok {
			return false
		}
	}
	return true
}
func bodyValid(kind uint64, b map[uint64]any) bool {
	sizes := map[uint64]int{Request: 16, Challenge: 4, Proof: 4, Accept: 10, Reject: 3, Withdraw: 5}
	n, ok := sizes[kind]
	if !ok || !exact(b, n) || !unsigned(b[0], 1, 1) {
		return false
	}
	max := ^uint64(0)
	tm := uint64(253402300799)
	switch kind {
	case Request:
		if (b[1] != "register" && b[1] != "renew") || !text(b[2]) || !text(b[6]) || !unsigned(b[13], 1, 60) || !unsigned(b[14], 0, tm) {
			return false
		}
		for _, k := range []uint64{3, 4, 5, 8, 9, 11, 12} {
			if !blob(b[k], 32, false) {
				return false
			}
		}
		key, ok := b[7].([]byte)
		if !ok || len(key) < 1 || len(key) > 64 {
			return false
		}
		if b[1] == "register" {
			if b[15] != nil {
				return false
			}
		} else if !blob(b[15], 32, false) {
			return false
		}
		refs, ok := b[10].([]any)
		if !ok || len(refs) < 1 || len(refs) > 64 {
			return false
		}
		var previous []byte
		for _, r := range refs {
			a, ok := r.([]any)
			if !ok || len(a) != 2 || !unsigned(a[0], 1, 18) || !blob(a[1], 32, false) {
				return false
			}
			wire, e := cbor.Encode(a)
			if e != nil || (previous != nil && bytes.Compare(previous, wire) >= 0) {
				return false
			}
			previous = wire
		}
		encoded, e := cbor.Encode(refs)
		if e != nil {
			return false
		}
		h := sha256.Sum256(encoded)
		if !bytes.Equal(h[:], b[11].([]byte)) {
			return false
		}
		raw, e := cbor.Encode(b)
		return e == nil && len(raw) <= 16384
	case Challenge:
		return blob(b[1], 32, false) && blob(b[2], 32, true) && unsigned(b[3], 0, tm)
	case Proof:
		return blob(b[1], 32, false) && blob(b[2], 32, true) && blob(b[3], 32, false)
	case Accept:
		for _, k := range []uint64{1, 8, 9} {
			if !blob(b[k], 32, false) {
				return false
			}
		}
		for _, k := range []uint64{2, 3} {
			if !blob(b[k], 16, true) {
				return false
			}
		}
		for _, k := range []uint64{5, 6, 7} {
			if !unsigned(b[k], 0, tm) {
				return false
			}
		}
		if !unsigned(b[4], 1, max) {
			return false
		}
		a, z, d := b[5].(uint64), b[6].(uint64), b[7].(uint64)
		return z > a && z-a <= 60 && d == a+(z-a)/2
	case Withdraw:
		return blob(b[1], 16, true) && blob(b[2], 16, true) && unsigned(b[3], 1, max) && blob(b[4], 32, false)
	case Reject:
		e, ok := b[2].(map[uint64]any)
		if !ok || (!exact(e, 4) && !exact(e, 5)) || !blob(b[1], 32, false) {
			return false
		}
		_, flag := e[3].(bool)
		if !unsigned(e[0], 1, 1) || !unsigned(e[1], 1, 19) || !blob(e[2], 16, true) || !flag {
			return false
		}
		if v, ok := e[4]; ok && (!unsigned(v, 1, 3600) || e[3] != true) {
			return false
		}
		return true
	}
	return false
}
func Decode(alpn string, wire []byte) (Envelope, error) {
	var e Envelope
	if alpn != ALPN {
		return e, ErrInvalid
	}
	v, err := cbor.DecodeExact(wire, cbor.Limits{MaxInputBytes: 65536, MaxDepth: 8, MaxCollectionItems: 64, MaxByteStringBytes: 16384, MaxTextStringBytes: 128})
	if err != nil {
		return e, ErrInvalid
	}
	m, ok := v.(map[uint64]any)
	if !ok || !exact(m, 6) || !unsigned(m[0], 1, 1) || !unsigned(m[1], Request, Withdraw) || !blob(m[2], 16, true) || !blob(m[3], 16, true) || !unsigned(m[4], 1, ^uint64(0)) {
		return e, ErrInvalid
	}
	b, ok := m[5].(map[uint64]any)
	if !ok || !bodyValid(m[1].(uint64), b) {
		return e, ErrInvalid
	}
	copy(e.RequestID[:], m[2].([]byte))
	copy(e.SessionID[:], m[3].([]byte))
	if !bytes.Equal(e.RequestID[:8], e.SessionID[:8]) || binary.BigEndian.Uint64(e.RequestID[8:]) == 0 {
		return Envelope{}, ErrInvalid
	}
	if m[1].(uint64) == Reject && !bytes.Equal(b[2].(map[uint64]any)[2].([]byte), e.RequestID[:]) {
		return Envelope{}, ErrInvalid
	}
	e.Kind = m[1].(uint64)
	e.Sequence = m[4].(uint64)
	e.Body = b
	canonical, err := cbor.Encode(m)
	if err != nil || !bytes.Equal(canonical, wire) {
		return Envelope{}, ErrInvalid
	}
	return e, nil
}
func Encode(e Envelope) ([]byte, error) {
	raw, err := cbor.Encode(map[uint64]any{0: uint64(1), 1: e.Kind, 2: e.RequestID[:], 3: e.SessionID[:], 4: e.Sequence, 5: e.Body})
	if err != nil {
		return nil, ErrInvalid
	}
	if _, err = Decode(ALPN, raw); err != nil {
		return nil, err
	}
	return raw, nil
}
