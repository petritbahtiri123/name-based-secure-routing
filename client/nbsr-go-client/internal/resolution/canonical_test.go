package resolution

import (
	"crypto/sha256"
	"testing"
)

func TestCanonicalizePresentationNameUsesFrozenRules(t *testing.T) {
	tests := []struct {
		input string
		want  CanonicalName
	}{
		{"API.Example.", "api.example"},
		{"b\u00fccher.example", "xn--bcher-kva.example"},
	}
	for _, test := range tests {
		got, err := CanonicalizePresentationName(test.input)
		if err != nil || got != test.want {
			t.Fatalf("CanonicalizePresentationName(%q) = (%q, %v), want (%q, nil)", test.input, got, err, test.want)
		}
	}
}

func TestCanonicalizePresentationNameRejectsInvalidNames(t *testing.T) {
	for _, input := range []string{"", "127.0.0.1", "2001:db8::1", "bad..example", "-bad.example", string(make([]byte, 254))} {
		if _, err := CanonicalizePresentationName(input); err == nil {
			t.Fatalf("CanonicalizePresentationName(%q) accepted invalid name", input)
		}
	}
}

func TestDigestCanonicalNameHashesCanonicalASCII(t *testing.T) {
	name := CanonicalName("api.example")
	want := sha256.Sum256([]byte("api.example"))
	if got := DigestCanonicalName(name); got != want {
		t.Fatalf("DigestCanonicalName = %x, want %x", got, want)
	}
}
