// Package cbor implements the bounded deterministic CBOR surface frozen by the profile.
package cbor

import (
	"bytes"
	"encoding/binary"
	"fmt"
	"math"
	"sort"
	"unicode/utf8"
)

type Kind uint8

const (
	Uint Kind = iota
	Nint
	Bytes
	Text
	Array
	Map
	Bool
	Null
	Tag
)

type Pair struct{ Key, Value Value }
type Value struct {
	Kind   Kind
	Uint   uint64
	Bytes  []byte
	Text   string
	Array  []Value
	Map    []Pair
	Bool   bool
	Tag    uint64
	Tagged *Value
}
type Limits struct {
	MaxDepth          int
	MaxArray, MaxMap  int
	MaxBytes, MaxText int
}

var DefaultLimits = Limits{16, 1024, 1024, 1 << 20, 1 << 20}

func Decode(raw []byte) (Value, error) { return DecodeLimits(raw, DefaultLimits) }
func DecodeLimits(raw []byte, lim Limits) (Value, error) {
	d := decoder{b: raw, lim: lim}
	v, _, err := d.one(0)
	if err != nil {
		return Value{}, err
	}
	if d.i != len(raw) {
		return Value{}, fmt.Errorf("trailing CBOR")
	}
	return v, nil
}

type decoder struct {
	b   []byte
	i   int
	lim Limits
}

func (d *decoder) take(n int) ([]byte, error) {
	if n < 0 || n > len(d.b)-d.i {
		return nil, fmt.Errorf("truncated CBOR")
	}
	x := d.b[d.i : d.i+n]
	d.i += n
	return x, nil
}
func (d *decoder) argument(ai byte) (uint64, error) {
	if ai < 24 {
		return uint64(ai), nil
	}
	sizes := map[byte]int{24: 1, 25: 2, 26: 4, 27: 8}
	n, ok := sizes[ai]
	if !ok {
		return 0, fmt.Errorf("indefinite/reserved CBOR")
	}
	b, e := d.take(n)
	if e != nil {
		return 0, e
	}
	var x uint64
	for _, c := range b {
		x = x<<8 | uint64(c)
	}
	if x < 24 || (n > 1 && x < uint64(1)<<(8*(n-1))) {
		return 0, fmt.Errorf("non-shortest CBOR argument")
	}
	return x, nil
}
func (d *decoder) one(depth int) (Value, []byte, error) {
	if depth > d.lim.MaxDepth {
		return Value{}, nil, fmt.Errorf("CBOR depth limit")
	}
	start := d.i
	h, e := d.take(1)
	if e != nil {
		return Value{}, nil, e
	}
	major, ai := h[0]>>5, h[0]&31
	switch major {
	case 0, 1:
		x, e := d.argument(ai)
		if e != nil {
			return Value{}, nil, e
		}
		k := Uint
		if major == 1 {
			k = Nint
		}
		v := Value{Kind: k, Uint: x}
		return v, d.b[start:d.i], nil
	case 2, 3:
		n, e := d.argument(ai)
		if e != nil {
			return Value{}, nil, e
		}
		max := d.lim.MaxBytes
		if major == 3 {
			max = d.lim.MaxText
		}
		if n > uint64(max) || n > uint64(math.MaxInt) {
			return Value{}, nil, fmt.Errorf("CBOR string limit")
		}
		b, e := d.take(int(n))
		if e != nil {
			return Value{}, nil, e
		}
		if major == 2 {
			return Value{Kind: Bytes, Bytes: append([]byte(nil), b...)}, d.b[start:d.i], nil
		}
		if !utf8.Valid(b) {
			return Value{}, nil, fmt.Errorf("invalid UTF-8")
		}
		return Value{Kind: Text, Text: string(b)}, d.b[start:d.i], nil
	case 4:
		n, e := d.argument(ai)
		if e != nil {
			return Value{}, nil, e
		}
		if n > uint64(d.lim.MaxArray) {
			return Value{}, nil, fmt.Errorf("CBOR array limit")
		}
		a := make([]Value, 0, n)
		for range n {
			x, _, e := d.one(depth + 1)
			if e != nil {
				return Value{}, nil, e
			}
			a = append(a, x)
		}
		return Value{Kind: Array, Array: a}, d.b[start:d.i], nil
	case 5:
		n, e := d.argument(ai)
		if e != nil {
			return Value{}, nil, e
		}
		if n > uint64(d.lim.MaxMap) {
			return Value{}, nil, fmt.Errorf("CBOR map limit")
		}
		m := make([]Pair, 0, n)
		var prev []byte
		for range n {
			k, kb, e := d.one(depth + 1)
			if e != nil {
				return Value{}, nil, e
			}
			if prev != nil && keyCompare(prev, kb) >= 0 {
				return Value{}, nil, fmt.Errorf("duplicate or noncanonical map key")
			}
			prev = append(prev[:0], kb...)
			v, _, e := d.one(depth + 1)
			if e != nil {
				return Value{}, nil, e
			}
			m = append(m, Pair{k, v})
		}
		return Value{Kind: Map, Map: m}, d.b[start:d.i], nil
	case 6:
		t, e := d.argument(ai)
		if e != nil {
			return Value{}, nil, e
		}
		x, _, e := d.one(depth + 1)
		if e != nil {
			return Value{}, nil, e
		}
		return Value{Kind: Tag, Tag: t, Tagged: &x}, d.b[start:d.i], nil
	case 7:
		if ai == 20 {
			return Value{Kind: Bool, Bool: false}, d.b[start:d.i], nil
		}
		if ai == 21 {
			return Value{Kind: Bool, Bool: true}, d.b[start:d.i], nil
		}
		if ai == 22 {
			return Value{Kind: Null}, d.b[start:d.i], nil
		}
		return Value{}, nil, fmt.Errorf("unsupported simple/float")
	}
	return Value{}, nil, fmt.Errorf("unsupported CBOR")
}

func Encode(v Value) ([]byte, error) {
	var b bytes.Buffer
	if err := enc(&b, v); err != nil {
		return nil, err
	}
	return b.Bytes(), nil
}
func head(b *bytes.Buffer, major byte, x uint64) {
	switch {
	case x < 24:
		b.WriteByte(major<<5 | byte(x))
	case x <= 255:
		b.WriteByte(major<<5 | 24)
		b.WriteByte(byte(x))
	case x <= 65535:
		b.WriteByte(major<<5 | 25)
		var q [2]byte
		binary.BigEndian.PutUint16(q[:], uint16(x))
		b.Write(q[:])
	case x <= math.MaxUint32:
		b.WriteByte(major<<5 | 26)
		var q [4]byte
		binary.BigEndian.PutUint32(q[:], uint32(x))
		b.Write(q[:])
	default:
		b.WriteByte(major<<5 | 27)
		var q [8]byte
		binary.BigEndian.PutUint64(q[:], x)
		b.Write(q[:])
	}
}
func enc(b *bytes.Buffer, v Value) error {
	switch v.Kind {
	case Uint:
		head(b, 0, v.Uint)
	case Nint:
		head(b, 1, v.Uint)
	case Bytes:
		head(b, 2, uint64(len(v.Bytes)))
		b.Write(v.Bytes)
	case Text:
		if !utf8.ValidString(v.Text) {
			return fmt.Errorf("invalid UTF-8")
		}
		head(b, 3, uint64(len(v.Text)))
		b.WriteString(v.Text)
	case Array:
		head(b, 4, uint64(len(v.Array)))
		for _, x := range v.Array {
			if e := enc(b, x); e != nil {
				return e
			}
		}
	case Map:
		type ep struct{ k, v []byte }
		xs := make([]ep, len(v.Map))
		for i, p := range v.Map {
			var kb, vb bytes.Buffer
			if e := enc(&kb, p.Key); e != nil {
				return e
			}
			if e := enc(&vb, p.Value); e != nil {
				return e
			}
			xs[i] = ep{kb.Bytes(), vb.Bytes()}
		}
		sort.Slice(xs, func(i, j int) bool { return keyCompare(xs[i].k, xs[j].k) < 0 })
		for i := 1; i < len(xs); i++ {
			if bytes.Equal(xs[i-1].k, xs[i].k) {
				return fmt.Errorf("duplicate map key")
			}
		}
		head(b, 5, uint64(len(xs)))
		for _, x := range xs {
			b.Write(x.k)
			b.Write(x.v)
		}
	case Bool:
		if v.Bool {
			b.WriteByte(0xf5)
		} else {
			b.WriteByte(0xf4)
		}
	case Null:
		b.WriteByte(0xf6)
	case Tag:
		head(b, 6, v.Tag)
		if v.Tagged == nil {
			return fmt.Errorf("nil tag")
		}
		return enc(b, *v.Tagged)
	default:
		return fmt.Errorf("unknown CBOR kind")
	}
	return nil
}
func keyCompare(a, b []byte) int {
	if len(a) < len(b) {
		return -1
	}
	if len(a) > len(b) {
		return 1
	}
	return bytes.Compare(a, b)
}

func Int(v Value) (int64, bool) {
	if v.Kind == Uint && v.Uint <= math.MaxInt64 {
		return int64(v.Uint), true
	}
	if v.Kind == Nint && v.Uint <= math.MaxInt64 {
		return -1 - int64(v.Uint), true
	}
	return 0, false
}
func Get(m Value, key uint64) (Value, bool) {
	if m.Kind != Map {
		return Value{}, false
	}
	for _, p := range m.Map {
		if p.Key.Kind == Uint && p.Key.Uint == key {
			return p.Value, true
		}
	}
	return Value{}, false
}
