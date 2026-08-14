// Package streamcredit implements only the approved P2D interop wire preface.
package streamcredit

import "errors"

const ProfileID = "nbsr-stream-credit-1"

func appendUint(wire []byte, major byte, value uint64) []byte {
	switch {
	case value < 24:
		return append(wire, major<<5|byte(value))
	case value <= 0xff:
		return append(wire, major<<5|24, byte(value))
	case value <= 0xffff:
		return append(wire, major<<5|25, byte(value>>8), byte(value))
	case value <= 0xffffffff:
		return append(wire, major<<5|26, byte(value>>24), byte(value>>16), byte(value>>8), byte(value))
	default:
		return append(wire, major<<5|27, byte(value>>56), byte(value>>48), byte(value>>40), byte(value>>32), byte(value>>24), byte(value>>16), byte(value>>8), byte(value))
	}
}

// EncodePreface returns the shortest-length-prefixed deterministic CBOR map.
func EncodePreface(channel [16]byte, generation, epoch, slot, streamID uint64) ([]byte, error) {
	if generation == 0 || epoch == 0 || slot >= 64 || streamID == 0 || streamID%4 != 0 {
		return nil, errors.New("stream credit preface field out of bounds")
	}
	body := []byte{0xa6, 0x00, 0x01, 0x01, 0x50}
	body = append(body, channel[:]...)
	body = appendUint(body, 0, 2)
	body = appendUint(body, 0, generation)
	body = appendUint(body, 0, 3)
	body = appendUint(body, 0, epoch)
	body = appendUint(body, 0, 4)
	body = appendUint(body, 0, slot)
	body = appendUint(body, 0, 5)
	body = appendUint(body, 0, streamID)
	if len(body) > 63 {
		return nil, errors.New("stream credit preface exceeds one-byte interop bound")
	}
	return append([]byte{byte(len(body))}, body...), nil
}
