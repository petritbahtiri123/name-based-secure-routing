package streamcredit

import (
	"encoding/hex"
	"testing"
)

func TestPrefaceMatchesApprovedVectors(t *testing.T) {
	channel := [16]byte{0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1a, 0x1b, 0x1c, 0x1d, 0x1e, 0x1f}
	for _, test := range []struct {
		name string
		slot uint64
		hex  string
	}{
		{"slot-0", 0, "1da600010150101112131415161718191a1b1c1d1e1f0201030104000504"},
		{"slot-63", 63, "1ea600010150101112131415161718191a1b1c1d1e1f0201030104183f0504"},
	} {
		t.Run(test.name, func(t *testing.T) {
			got, err := EncodePreface(channel, 1, 1, test.slot, 4)
			if err != nil {
				t.Fatal(err)
			}
			if hex.EncodeToString(got) != test.hex {
				t.Fatalf("preface mismatch: %x", got)
			}
		})
	}
}

func TestPrefaceRejectsOutOfBoundsAuthority(t *testing.T) {
	channel := [16]byte{}
	for _, input := range []struct{ generation, epoch, slot, stream uint64 }{
		{0, 1, 0, 4}, {1, 0, 0, 4}, {1, 1, 64, 4}, {1, 1, 0, 0}, {1, 1, 0, 5},
	} {
		if _, err := EncodePreface(channel, input.generation, input.epoch, input.slot, input.stream); err == nil {
			t.Fatalf("invalid preface accepted: %+v", input)
		}
	}
}
