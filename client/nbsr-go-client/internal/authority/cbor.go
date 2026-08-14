package authority

// This is an independent, bounded port of the preferred deterministic-CBOR
// subset in interop/nbsr-go-peer/internal/cbor/cbor.go.  It deliberately does
// not import the peer's internal package.

import (
	"bytes"
	"encoding/binary"
	"errors"
	"fmt"
	"math"
	"sort"
	"unicode/utf8"
)

type cborLimits struct {
	maxInputBytes, maxDepth, maxCollectionItems, maxByteStringBytes, maxTextStringBytes int
}

func defaultCBORLimits() cborLimits {
	return cborLimits{maxInputBytes: 1 << 20, maxDepth: 16, maxCollectionItems: 128, maxByteStringBytes: 1 << 20, maxTextStringBytes: 4096}
}

type cborDecoder struct {
	wire []byte
	off  int
	lim  cborLimits
}

func decodeCBORExact(wire []byte, limits cborLimits) (any, error) {
	if len(wire) == 0 || len(wire) > limits.maxInputBytes {
		return nil, errors.New("CBOR input length is out of bounds")
	}
	d := cborDecoder{wire: wire, lim: limits}
	value, err := d.item(0)
	if err != nil {
		return nil, err
	}
	if d.off != len(wire) {
		return nil, errors.New("trailing CBOR data")
	}
	return value, nil
}

func (d *cborDecoder) item(depth int) (any, error) {
	if depth > d.lim.maxDepth || d.off >= len(d.wire) {
		return nil, errors.New("CBOR depth or length exceeded")
	}
	initial := d.wire[d.off]
	d.off++
	major, additional := initial>>5, initial&0x1f
	if additional == 31 {
		return nil, errors.New("indefinite CBOR item")
	}
	argument, err := d.argument(additional)
	if err != nil {
		return nil, err
	}
	switch major {
	case 0:
		return argument, nil
	case 1:
		if argument > math.MaxInt64 {
			return nil, errors.New("negative integer out of range")
		}
		return -1 - int64(argument), nil
	case 2:
		return d.bytes(argument, d.lim.maxByteStringBytes)
	case 3:
		raw, err := d.bytes(argument, d.lim.maxTextStringBytes)
		if err != nil || !utf8.Valid(raw) {
			return nil, errors.New("invalid CBOR text")
		}
		return string(raw), nil
	case 4:
		if argument > uint64(d.lim.maxCollectionItems) {
			return nil, errors.New("CBOR array too large")
		}
		items := make([]any, int(argument))
		for index := range items {
			items[index], err = d.item(depth + 1)
			if err != nil {
				return nil, err
			}
		}
		return items, nil
	case 5:
		if argument > uint64(d.lim.maxCollectionItems) {
			return nil, errors.New("CBOR map too large")
		}
		items := make(map[uint64]any, int(argument))
		var previous uint64
		for index := uint64(0); index < argument; index++ {
			keyValue, keyErr := d.item(depth + 1)
			key, ok := keyValue.(uint64)
			if keyErr != nil || !ok || (index > 0 && key <= previous) {
				return nil, errors.New("CBOR map keys must be unique ascending uints")
			}
			previous = key
			items[key], err = d.item(depth + 1)
			if err != nil {
				return nil, err
			}
		}
		return items, nil
	case 7:
		switch additional {
		case 20:
			return false, nil
		case 21:
			return true, nil
		case 22:
			return nil, nil
		default:
			return nil, errors.New("unsupported CBOR simple or float value")
		}
	default:
		return nil, errors.New("unsupported CBOR type")
	}
}

func (d *cborDecoder) argument(additional byte) (uint64, error) {
	width := 0
	switch {
	case additional < 24:
		return uint64(additional), nil
	case additional == 24:
		width = 1
	case additional == 25:
		width = 2
	case additional == 26:
		width = 4
	case additional == 27:
		width = 8
	default:
		return 0, errors.New("reserved CBOR additional information")
	}
	if d.off+width > len(d.wire) {
		return 0, errors.New("truncated CBOR argument")
	}
	raw := d.wire[d.off : d.off+width]
	d.off += width
	var value uint64
	switch width {
	case 1:
		value = uint64(raw[0])
	case 2:
		value = uint64(binary.BigEndian.Uint16(raw))
	case 4:
		value = uint64(binary.BigEndian.Uint32(raw))
	case 8:
		value = binary.BigEndian.Uint64(raw)
	}
	minimum := [...]uint64{0, 24, 256, 0, 65536, 0, 0, 0, 4294967296}[width]
	if value < minimum {
		return 0, errors.New("non-preferred CBOR argument")
	}
	return value, nil
}

func (d *cborDecoder) bytes(length uint64, maximum int) ([]byte, error) {
	if length > uint64(maximum) || length > uint64(len(d.wire)-d.off) {
		return nil, errors.New("CBOR string length is out of bounds")
	}
	value := append([]byte(nil), d.wire[d.off:d.off+int(length)]...)
	d.off += int(length)
	return value, nil
}

func encodeCBOR(value any) ([]byte, error) {
	var output bytes.Buffer
	if err := encodeCBORValue(&output, value); err != nil {
		return nil, err
	}
	return output.Bytes(), nil
}

func encodeCBORValue(output *bytes.Buffer, value any) error {
	switch typed := value.(type) {
	case uint64:
		writeCBORHead(output, 0, typed)
	case int64:
		if typed < 0 {
			writeCBORHead(output, 1, uint64(-1-typed))
		} else {
			writeCBORHead(output, 0, uint64(typed))
		}
	case []byte:
		writeCBORHead(output, 2, uint64(len(typed)))
		output.Write(typed)
	case string:
		if !utf8.ValidString(typed) {
			return errors.New("invalid UTF-8 string")
		}
		writeCBORHead(output, 3, uint64(len(typed)))
		output.WriteString(typed)
	case []any:
		writeCBORHead(output, 4, uint64(len(typed)))
		for _, item := range typed {
			if err := encodeCBORValue(output, item); err != nil {
				return err
			}
		}
	case map[uint64]any:
		writeCBORHead(output, 5, uint64(len(typed)))
		keys := make([]uint64, 0, len(typed))
		for key := range typed {
			keys = append(keys, key)
		}
		sort.Slice(keys, func(left, right int) bool { return keys[left] < keys[right] })
		for _, key := range keys {
			writeCBORHead(output, 0, key)
			if err := encodeCBORValue(output, typed[key]); err != nil {
				return err
			}
		}
	default:
		return fmt.Errorf("unsupported CBOR value %T", value)
	}
	return nil
}

func writeCBORHead(output *bytes.Buffer, major byte, value uint64) {
	switch {
	case value < 24:
		output.WriteByte(major<<5 | byte(value))
	case value <= math.MaxUint8:
		output.WriteByte(major<<5 | 24)
		output.WriteByte(byte(value))
	case value <= math.MaxUint16:
		output.WriteByte(major<<5 | 25)
		var raw [2]byte
		binary.BigEndian.PutUint16(raw[:], uint16(value))
		output.Write(raw[:])
	case value <= math.MaxUint32:
		output.WriteByte(major<<5 | 26)
		var raw [4]byte
		binary.BigEndian.PutUint32(raw[:], uint32(value))
		output.Write(raw[:])
	default:
		output.WriteByte(major<<5 | 27)
		var raw [8]byte
		binary.BigEndian.PutUint64(raw[:], value)
		output.Write(raw[:])
	}
}
