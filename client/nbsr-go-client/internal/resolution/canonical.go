package resolution

import (
	"crypto/sha256"
	"errors"
	"net"
	"strings"

	"golang.org/x/net/idna"

	"nbsr.local/client/nbsr-go-client/internal/corestate"
)

var ErrInvalidResolution = errors.New("invalid resolution")

type CanonicalName string

func CanonicalizePresentationName(value string) (CanonicalName, error) {
	if strings.HasSuffix(value, ".") {
		value = strings.TrimSuffix(value, ".")
	}
	if value == "" {
		return "", ErrInvalidResolution
	}
	ascii, err := idna.Lookup.ToASCII(value)
	if err != nil {
		return "", ErrInvalidResolution
	}
	ascii = strings.ToLower(ascii)
	if len(ascii) == 0 || len(ascii) > 253 || strings.HasSuffix(ascii, ".") || net.ParseIP(ascii) != nil {
		return "", ErrInvalidResolution
	}
	for _, label := range strings.Split(ascii, ".") {
		if !validDNSLabel(label) {
			return "", ErrInvalidResolution
		}
	}
	return CanonicalName(ascii), nil
}

func validDNSLabel(label string) bool {
	if len(label) == 0 || len(label) > 63 || !asciiAlphaNumeric(label[0]) || !asciiAlphaNumeric(label[len(label)-1]) {
		return false
	}
	for i := range len(label) {
		if !asciiAlphaNumeric(label[i]) && label[i] != '-' {
			return false
		}
	}
	return true
}

func asciiAlphaNumeric(value byte) bool {
	return value >= 'a' && value <= 'z' || value >= '0' && value <= '9'
}

func DigestCanonicalName(name CanonicalName) corestate.ServiceDigest {
	return corestate.ServiceDigest(sha256.Sum256([]byte(name)))
}
