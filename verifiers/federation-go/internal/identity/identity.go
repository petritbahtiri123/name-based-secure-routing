package identity

import (
	"crypto/sha256"
	"fmt"
	"strings"
)

func OperatorID(key []byte) ([32]byte, error) {
	if len(key) != 32 {
		return [32]byte{}, fmt.Errorf("Ed25519 genesis key must be 32 bytes")
	}
	pre := append([]byte("NBSR-FEDERATION-OPERATOR-ID-v1\x00\x01"), key...)
	return sha256.Sum256(pre), nil
}

const charset = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"

func polymod(v []byte) uint32 {
	chk := uint32(1)
	gen := []uint32{0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3}
	for _, x := range v {
		top := chk >> 25
		chk = (chk&0x1ffffff)<<5 ^ uint32(x)
		for i, g := range gen {
			if (top>>i)&1 != 0 {
				chk ^= g
			}
		}
	}
	return chk
}
func hrpExpand(s string) []byte {
	r := make([]byte, 0, len(s)*2+1)
	for _, c := range []byte(s) {
		r = append(r, c>>5)
	}
	r = append(r, 0)
	for _, c := range []byte(s) {
		r = append(r, c&31)
	}
	return r
}
func convert(data []byte, from, to uint, pad bool) ([]byte, error) {
	var acc uint64
	var bits uint
	maxv := uint64(1<<to) - 1
	out := []byte{}
	for _, x := range data {
		if uint64(x)>>from != 0 {
			return nil, fmt.Errorf("invalid data")
		}
		acc = (acc << from) | uint64(x)
		bits += from
		for bits >= to {
			bits -= to
			out = append(out, byte(acc>>bits&maxv))
		}
	}
	if pad && bits > 0 {
		out = append(out, byte(acc<<(to-bits)&maxv))
	} else if !pad && (bits >= from || (acc<<(to-bits)&maxv) != 0) {
		return nil, fmt.Errorf("invalid padding")
	}
	return out, nil
}
func EncodeOperatorID(id []byte) (string, error) {
	if len(id) != 32 {
		return "", fmt.Errorf("operator ID must be 32 bytes")
	}
	data, e := convert(id, 8, 5, true)
	if e != nil {
		return "", e
	}
	hrp := "nbsr"
	vals := append(hrpExpand(hrp), data...)
	vals = append(vals, make([]byte, 6)...)
	pm := polymod(vals) ^ 0x2bc830a3
	var b strings.Builder
	b.WriteString(hrp)
	b.WriteByte('1')
	for _, x := range data {
		b.WriteByte(charset[x])
	}
	for i := 0; i < 6; i++ {
		b.WriteByte(charset[byte(pm>>uint(5*(5-i)))&31])
	}
	return b.String(), nil
}
func DecodeOperatorID(s string) ([]byte, error) {
	if s != strings.ToLower(s) || strings.ToUpper(s) == s {
		return nil, fmt.Errorf("mixed/upper case")
	}
	pos := strings.LastIndexByte(s, '1')
	if pos < 1 || pos+7 > len(s) || s[:pos] != "nbsr" {
		return nil, fmt.Errorf("invalid HRP/length")
	}
	vals := make([]byte, 0, len(s)-pos-1)
	for _, c := range []byte(s[pos+1:]) {
		i := strings.IndexByte(charset, c)
		if i < 0 {
			return nil, fmt.Errorf("invalid character")
		}
		vals = append(vals, byte(i))
	}
	if polymod(append(hrpExpand(s[:pos]), vals...)) != 0x2bc830a3 {
		return nil, fmt.Errorf("checksum")
	}
	out, e := convert(vals[:len(vals)-6], 5, 8, false)
	if e != nil || len(out) != 32 {
		return nil, fmt.Errorf("operator ID payload")
	}
	return out, nil
}
