package session

import "nbsr.local/client/nbsr-go-client/internal/corestate"

const StreamCreditProfileID = "nbsr-stream-credit-1"

func encodeStreamCreditPreface(channel corestate.ChannelID, generation, epoch uint64, slot uint8, streamID corestate.StreamID) ([]byte, error) {
	if generation == 0 || epoch == 0 || slot >= StreamCreditCount || streamID == 0 || uint64(streamID)%4 != 0 {
		return nil, ErrCreditMalformed
	}
	body := []byte{0xa6, 0x00, 0x01, 0x01, 0x50}
	body = append(body, channel[:]...)
	body = appendCBORUint(body, 2)
	body = appendCBORUint(body, generation)
	body = appendCBORUint(body, 3)
	body = appendCBORUint(body, epoch)
	body = appendCBORUint(body, 4)
	body = appendCBORUint(body, uint64(slot))
	body = appendCBORUint(body, 5)
	body = appendCBORUint(body, uint64(streamID))
	if len(body) > 128 {
		return nil, ErrCreditMalformed
	}
	return appendQUICVarint(nil, uint64(len(body)), body), nil
}

func appendCBORUint(wire []byte, value uint64) []byte {
	switch {
	case value < 24:
		return append(wire, byte(value))
	case value <= 0xff:
		return append(wire, 24, byte(value))
	case value <= 0xffff:
		return append(wire, 25, byte(value>>8), byte(value))
	case value <= 0xffffffff:
		return append(wire, 26, byte(value>>24), byte(value>>16), byte(value>>8), byte(value))
	default:
		return append(wire, 27, byte(value>>56), byte(value>>48), byte(value>>40), byte(value>>32), byte(value>>24), byte(value>>16), byte(value>>8), byte(value))
	}
}

func appendQUICVarint(wire []byte, value uint64, body []byte) []byte {
	switch {
	case value <= 63:
		wire = append(wire, byte(value))
	case value <= 16383:
		wire = append(wire, byte(value>>8)|0x40, byte(value))
	case value <= 1073741823:
		wire = append(wire, byte(value>>24)|0x80, byte(value>>16), byte(value>>8), byte(value))
	default:
		wire = append(wire, byte(value>>56)|0xc0, byte(value>>48), byte(value>>40), byte(value>>32), byte(value>>24), byte(value>>16), byte(value>>8), byte(value))
	}
	return append(wire, body...)
}
