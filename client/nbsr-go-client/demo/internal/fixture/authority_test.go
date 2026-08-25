package fixture

import (
	"context"
	"errors"
	"testing"

	"nbsr.local/client/nbsr-go-client/internal/authority"
)

func TestAuthorityFixtureSignsOnlyExactCatalogRequest(t *testing.T) {
	server, err := Start(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(server.Close)
	request := server.AcquireRequest()
	if request.Key.ServiceDigest != authority.ServiceDigest([32]byte{0x07, 0xed, 0x4f, 0xf0, 0xa2, 0x36, 0x5c, 0xc9, 0x16, 0x49, 0xcf, 0x8a, 0x94, 0x05, 0xd2, 0xf1, 0xcd, 0x12, 0x61, 0xfc, 0xb2, 0x01, 0xa9, 0x22, 0xac, 0xdb, 0xf4, 0xf4, 0xbc, 0xf2, 0x13, 0xb5}) {
		t.Fatal("AuthorityKey is not derived from the canonical demo service name")
	}
}

func TestAuthorityFixtureRejectsUnknownServiceAndCancellation(t *testing.T) {
	server, err := Start(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(server.Close)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err := authority.SignDemoRouteGrant(ctx, authority.DemoRouteGrantInput{}, nil); !errors.Is(err, context.Canceled) {
		t.Fatalf("cancellation = %v", err)
	}
}
