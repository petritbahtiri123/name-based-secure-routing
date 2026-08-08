package cbor

import (
	"encoding/hex"
	"testing"
)

func TestCanonicalRoundTripAndRejections(t *testing.T) {
	good := []string{"00", "20", "4100", "6161", "8201f6", "a201020203", "a26000181800", "d28440a04040"}
	for _, h := range good {
		b, _ := hex.DecodeString(h)
		v, err := Decode(b)
		if err != nil {
			t.Fatalf("%s: %v", h, err)
		}
		out, err := Encode(v)
		if err != nil || hex.EncodeToString(out) != h {
			t.Fatalf("round trip %s: %x %v", h, out, err)
		}
	}
	bad := []string{"1800", "5f40ff", "a201020103", "a202030102", "f90000", "00ff"}
	for _, h := range bad {
		b, _ := hex.DecodeString(h)
		if _, err := Decode(b); err == nil {
			t.Fatalf("accepted %s", h)
		}
	}
}
