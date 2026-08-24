package transport

import (
	"bytes"
	"context"
	"errors"
	"testing"
)

func TestRefillStreamCreditsHonorsCancellationWhileWaitingForControlLock(t *testing.T) {
	peer := &Peer{controlLock: make(chan struct{}, 1)}
	peer.controlLock <- struct{}{}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if err := peer.RefillStreamCredits(ctx, [16]byte{1}, 2); !errors.Is(err, context.Canceled) {
		t.Fatalf("refill cancellation = %v", err)
	}
}

func TestStreamCreditRefillFramesMatchAcceptedP2DVectors(t *testing.T) {
	channel := [16]byte{0x40, 0x41, 0x42, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49, 0x4a, 0x4b, 0x4c, 0x4d, 0x4e, 0x4f}
	request, err := encodeStreamCreditRefill(1, channel, 2)
	if err != nil {
		t.Fatal(err)
	}
	want := []byte{0x1e, 0x4e, 0x53, 0x43, 0x52, 0x01, 0x01,
		0x40, 0x41, 0x42, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49, 0x4a, 0x4b, 0x4c, 0x4d, 0x4e, 0x4f,
		0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02}
	if !bytes.Equal(request, want) {
		t.Fatalf("request = %x, want %x", request, want)
	}
	grant := append([]byte(nil), want...)
	grant[6] = 2
	gotChannel, gotEpoch, err := decodeStreamCreditRefill(grant, 2)
	if err != nil || gotChannel != channel || gotEpoch != 2 {
		t.Fatalf("grant = %x, %d, %v", gotChannel, gotEpoch, err)
	}
}
