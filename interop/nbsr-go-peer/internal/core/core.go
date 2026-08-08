// Package core implements the independent peer's frozen Core v0.2 envelope,
// message-body structural validation, and control-stream framing.
package core

import (
	"encoding/binary"
	"errors"
	"fmt"
	"math"
	"unicode/utf8"

	"nbsr.local/interop/nbsr-go-peer/internal/cbor"
)

type MessageType uint64

const (
	ClientHello  MessageType = 1
	EdgeHello    MessageType = 2
	RouteOpen    MessageType = 3
	RouteAccept  MessageType = 4
	RouteReject  MessageType = 5
	StreamOpen   MessageType = 6
	StreamAccept MessageType = 7
	StreamReject MessageType = 8
)

type Envelope struct {
	ProtocolVersion uint64
	MessageType     MessageType
	RequestID       [16]byte
	SessionID       [16]byte
	Sequence        uint64
	Body            map[uint64]any
	Extensions      map[uint64]any
}

func DecodeEnvelope(wire []byte) (Envelope, error) {
	value, err := cbor.DecodeExact(wire, cbor.DefaultLimits())
	if err != nil {
		return Envelope{}, err
	}
	object, ok := value.(map[uint64]any)
	if !ok {
		return Envelope{}, errors.New("ControlEnvelope must be a map")
	}
	for key := uint64(0); key <= 5; key++ {
		if _, present := object[key]; !present {
			return Envelope{}, fmt.Errorf("missing envelope key %d", key)
		}
	}
	version, ok := object[0].(uint64)
	if !ok || version != 2 {
		return Envelope{}, errors.New("unsupported Core version")
	}
	messageCode, ok := object[1].(uint64)
	if !ok || messageCode < 1 || messageCode > 8 {
		return Envelope{}, errors.New("unsupported message type")
	}
	request, err := fixedBytes(object[2], 16)
	if err != nil {
		return Envelope{}, errors.New("invalid request ID")
	}
	session, err := fixedBytes(object[3], 16)
	if err != nil {
		return Envelope{}, errors.New("invalid session ID")
	}
	sequence, ok := object[4].(uint64)
	if !ok || sequence == 0 {
		return Envelope{}, errors.New("invalid monotonic sequence")
	}
	body, ok := object[5].(map[uint64]any)
	if !ok {
		return Envelope{}, errors.New("body must be a numeric-key map")
	}
	if err := ValidateBody(MessageType(messageCode), body); err != nil {
		return Envelope{}, err
	}
	if critical, present := object[6]; present {
		items, ok := critical.([]any)
		if !ok || len(items) == 0 {
			return Envelope{}, errors.New("invalid critical extension list")
		}
		return Envelope{}, errors.New("critical extensions are unsupported")
	}
	extensions := make(map[uint64]any)
	for key, item := range object {
		if key <= 6 {
			continue
		}
		if key < 1000 {
			return Envelope{}, errors.New("unknown reserved envelope key")
		}
		extensions[key] = item
	}
	var requestID, sessionID [16]byte
	copy(requestID[:], request)
	copy(sessionID[:], session)
	return Envelope{version, MessageType(messageCode), requestID, sessionID, sequence, body, extensions}, nil
}

func EncodeEnvelope(envelope Envelope) ([]byte, error) {
	if envelope.ProtocolVersion != 2 || envelope.Sequence == 0 {
		return nil, errors.New("invalid envelope")
	}
	if err := ValidateBody(envelope.MessageType, envelope.Body); err != nil {
		return nil, err
	}
	object := map[uint64]any{
		0: envelope.ProtocolVersion, 1: uint64(envelope.MessageType), 2: envelope.RequestID[:],
		3: envelope.SessionID[:], 4: envelope.Sequence, 5: envelope.Body,
	}
	for key, item := range envelope.Extensions {
		if key < 1000 {
			return nil, errors.New("extension key is reserved")
		}
		object[key] = item
	}
	return cbor.Encode(object)
}

func ValidateBody(message MessageType, body map[uint64]any) error {
	switch message {
	case ClientHello:
		if err := exactKeys(body, 0, 7); err != nil {
			return err
		}
		if !uintEquals(body[0], 1) || !ascii(body[1], 1, 64) || !ascii(body[2], 1, 64) || !ascii(body[3], 1, 64) || !ascii(body[4], 1, 64) || !bytesLength(body[5], 32) || !bytesLength(body[6], 32) || !uintRange(body[7], 0, 253402300799) {
			return errors.New("invalid CLIENT_HELLO body")
		}
	case EdgeHello:
		if err := exactKeys(body, 0, 6); err != nil {
			return err
		}
		if !uintEquals(body[0], 1) || !ascii(body[1], 1, 64) || !ascii(body[2], 1, 64) || !bytesLength(body[3], 32) || !bytesLength(body[4], 32) || !bytesLength(body[5], 32) || !uintRange(body[6], 0, 253402300799) {
			return errors.New("invalid EDGE_HELLO body")
		}
	case RouteOpen:
		version, ok := body[0].(uint64)
		if !ok || (version != 1 && version != 2) {
			return errors.New("invalid ROUTE_OPEN version")
		}
		last := uint64(7)
		if version == 2 {
			last = 8
		}
		if err := exactKeys(body, 0, last); err != nil {
			return err
		}
		if !bytesLength(body[1], 16) || !bytesRange(body[2], 1, 32768) || !bytesLength(body[3], 32) || !transport(body[4]) || !uintRange(body[5], 1, 65535) || !uintRange(body[6], 0, 253402300799) || !bytesLength(body[7], 64) {
			return errors.New("invalid ROUTE_OPEN body")
		}
		if version == 2 && !validFederationBinding(body[8]) {
			return errors.New("invalid F75 federation binding")
		}
	case RouteAccept:
		if err := exactKeys(body, 0, 4); err != nil {
			return err
		}
		if !uintEquals(body[0], 1) || !bytesLength(body[1], 16) || !bytesLength(body[2], 16) || !bytesLength(body[3], 32) || !uintRange(body[4], 0, 253402300799) {
			return errors.New("invalid ROUTE_ACCEPT body")
		}
	case StreamOpen:
		if err := exactKeys(body, 0, 6); err != nil {
			return err
		}
		stream, ok := body[1].(uint64)
		if !uintEquals(body[0], 1) || !ok || stream < 4 || stream > (1<<62)-1 || stream%4 != 0 || !bytesLength(body[2], 16) || !bytesLength(body[3], 16) || !bytesLength(body[4], 32) || body[5] != "tcp" || !uintRange(body[6], 1, 65535) {
			return errors.New("invalid STREAM_OPEN body")
		}
	case StreamAccept:
		if err := exactKeys(body, 0, 4); err != nil {
			return err
		}
		stream, ok := body[1].(uint64)
		if !uintEquals(body[0], 1) || !ok || stream < 4 || stream > (1<<62)-1 || stream%4 != 0 || !bytesLength(body[2], 16) || !bytesLength(body[3], 16) || !uintRange(body[4], 0, 253402300799) {
			return errors.New("invalid STREAM_ACCEPT body")
		}
	default:
		return errors.New("message body is not implemented")
	}
	return nil
}

func validFederationBinding(value any) bool {
	binding, ok := value.(map[uint64]any)
	if !ok || exactKeys(binding, 0, 5) != nil {
		return false
	}
	return uintEquals(binding[0], 1) && uintEquals(binding[1], 1) && uintEquals(binding[2], 1) && binding[3] == "nbsr-federation-dev-v1" && bytesLength(binding[4], 32) && bytesLength(binding[5], 32)
}

func exactKeys(body map[uint64]any, first, last uint64) error {
	if len(body) != int(last-first+1) {
		return errors.New("body has missing or unknown keys")
	}
	for key := first; key <= last; key++ {
		if _, ok := body[key]; !ok {
			return errors.New("body has missing or unknown keys")
		}
	}
	return nil
}

func fixedBytes(value any, length int) ([]byte, error) {
	raw, ok := value.([]byte)
	if !ok || len(raw) != length {
		return nil, errors.New("wrong byte length")
	}
	return raw, nil
}
func bytesLength(value any, length int) bool {
	raw, ok := value.([]byte)
	return ok && len(raw) == length
}
func bytesRange(value any, minimum, maximum int) bool {
	raw, ok := value.([]byte)
	return ok && len(raw) >= minimum && len(raw) <= maximum
}
func uintEquals(value any, expected uint64) bool {
	actual, ok := value.(uint64)
	return ok && actual == expected
}
func uintRange(value any, minimum, maximum uint64) bool {
	actual, ok := value.(uint64)
	return ok && actual >= minimum && actual <= maximum
}
func ascii(value any, minimum, maximum int) bool {
	text, ok := value.(string)
	return ok && len(text) >= minimum && len(text) <= maximum && utf8.ValidString(text) && isASCII(text)
}
func isASCII(value string) bool {
	for _, item := range []byte(value) {
		if item > 0x7f {
			return false
		}
	}
	return true
}
func transport(value any) bool {
	text, ok := value.(string)
	return ok && (text == "tcp" || text == "udp")
}

func EncodeControlFrame(payload []byte) ([]byte, error) {
	if len(payload) < 1 || len(payload) > 65536 {
		return nil, errors.New("control frame length out of bounds")
	}
	prefix := encodeQUICVarint(uint64(len(payload)))
	return append(prefix, payload...), nil
}

func DecodeControlFrame(wire []byte) (payload []byte, rest []byte, err error) {
	length, prefix, err := decodeQUICVarint(wire)
	if err != nil {
		return nil, nil, err
	}
	if length < 1 || length > 65536 || uint64(len(wire)-prefix) < length {
		return nil, nil, errors.New("control frame length out of bounds")
	}
	end := prefix + int(length)
	return append([]byte(nil), wire[prefix:end]...), wire[end:], nil
}

func encodeQUICVarint(value uint64) []byte {
	if value < 64 {
		return []byte{byte(value)}
	}
	if value < 16384 {
		var output [2]byte
		binary.BigEndian.PutUint16(output[:], uint16(value)|0x4000)
		return output[:]
	}
	var output [4]byte
	binary.BigEndian.PutUint32(output[:], uint32(value)|0x80000000)
	return output[:]
}

func decodeQUICVarint(wire []byte) (uint64, int, error) {
	if len(wire) == 0 {
		return 0, 0, errors.New("missing QUIC varint")
	}
	width := 1 << (wire[0] >> 6)
	if len(wire) < width {
		return 0, 0, errors.New("truncated QUIC varint")
	}
	var value uint64
	switch width {
	case 1:
		value = uint64(wire[0] & 0x3f)
	case 2:
		value = uint64(binary.BigEndian.Uint16(wire[:2]) & 0x3fff)
	case 4:
		value = uint64(binary.BigEndian.Uint32(wire[:4]) & 0x3fffffff)
	case 8:
		value = binary.BigEndian.Uint64(wire[:8]) & math.MaxInt64 >> 1
	}
	if (width == 2 && value < 64) || (width == 4 && value < 16384) || (width == 8 && value < 1<<30) {
		return 0, 0, errors.New("non-shortest QUIC varint")
	}
	return value, width, nil
}
