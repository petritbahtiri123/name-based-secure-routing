package session

import (
	"bytes"
	"errors"
	"testing"

	"nbsr.local/client/nbsr-go-client/internal/corestate"
)

func TestEncodeStreamCreditPrefaceMatchesAcceptedP2DWire(t *testing.T) {
	var channel corestate.ChannelID
	for i := range channel {
		channel[i] = 0x11
	}
	wire, err := encodeStreamCreditPreface(channel, 1, 1, 0, 4)
	if err != nil {
		t.Fatal(err)
	}
	want := []byte{0x1d, 0xa6, 0x00, 0x01, 0x01, 0x50,
		0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11,
		0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11,
		0x02, 0x01, 0x03, 0x01, 0x04, 0x00, 0x05, 0x04}
	if !bytes.Equal(wire, want) {
		t.Fatalf("preface = %x, want %x", wire, want)
	}
}

func TestEncodeStreamCreditPrefaceRejectsMalformedOrWrongStream(t *testing.T) {
	var channel corestate.ChannelID
	for name, fields := range map[string][4]uint64{
		"zero generation": {0, 1, 0, 4},
		"zero epoch":      {1, 0, 0, 4},
		"slot 64":         {1, 1, 64, 4},
		"zero stream":     {1, 1, 0, 0},
		"wrong direction": {1, 1, 0, 5},
	} {
		t.Run(name, func(t *testing.T) {
			if _, err := encodeStreamCreditPreface(channel, fields[0], fields[1], uint8(fields[2]), corestate.StreamID(fields[3])); !errors.Is(err, ErrCreditMalformed) {
				t.Fatalf("error = %v, want ErrCreditMalformed", err)
			}
		})
	}
}
