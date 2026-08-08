package identity

import (
	"encoding/hex"
	"testing"
)

func TestFrozenOperatorID(t *testing.T) {
	key, _ := hex.DecodeString("000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f")
	id, err := OperatorID(key)
	if err != nil {
		t.Fatal(err)
	}
	if hex.EncodeToString(id[:]) != "56c83296d5d62b74a9f161125c5fc9b441fb8f85b174606f3379ca57503e1e86" {
		t.Fatalf("digest %x", id)
	}
	s, err := EncodeOperatorID(id[:])
	if err != nil {
		t.Fatal(err)
	}
	if s != "nbsr12myr99k46c4hf203vyf9ch7fk3qlhru9k96xqmen0899w5p7r6rqgutt5k" {
		t.Fatalf("bech32m %s", s)
	}
	back, err := DecodeOperatorID(s)
	if err != nil || hex.EncodeToString(back) != hex.EncodeToString(id[:]) {
		t.Fatalf("decode %x %v", back, err)
	}
}
