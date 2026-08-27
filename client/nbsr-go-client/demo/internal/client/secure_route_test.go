package client

import (
	"context"
	"crypto/ed25519"
	"errors"
	"testing"

	"nbsr.local/client/nbsr-go-client/internal/corestate"
	"nbsr.local/client/nbsr-go-client/internal/resolution"
	"nbsr.local/client/nbsr-go-client/internal/session"
)

var _ resolution.SecureRouteOpener = (*SecureRouteOpener)(nil)

func TestNewSecureRouteOpenerRejectsIncompleteProductionComposition(t *testing.T) {
	if _, err := NewSecureRouteOpener(SecureRouteOpenerConfig{}); !errors.Is(err, session.ErrInvalidSession) {
		t.Fatalf("incomplete composition error = %v", err)
	}
}

func TestWireConnectorRejectsProofBWithoutDialing(t *testing.T) {
	owner, err := NewTSProofOwner(ed25519.NewKeyFromSeed(make([]byte, ed25519.SeedSize)), 2)
	if err != nil {
		t.Fatal(err)
	}
	connector := &wireConnector{proof: owner}
	attempt := session.TransportSessionAttempt{Generation: corestate.TSGeneration(2), ProofKey: owner.KeyRef()}
	attempt.ProofKey.ID[0] ^= 1
	if _, err := connector.Connect(context.Background(), attempt); !errors.Is(err, session.ErrProofBinding) {
		t.Fatalf("proof substitution error = %v", err)
	}
}
