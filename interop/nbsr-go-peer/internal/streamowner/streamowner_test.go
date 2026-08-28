package streamowner

import (
	"bytes"
	"context"
	"errors"
	"io"
	"testing"
)

type fakeWire struct {
	bytes.Buffer
	id       uint64
	accepted bool
	closed   bool
}

func (wire *fakeWire) Read(target []byte) (int, error) {
	if !wire.accepted {
		wire.accepted = true
		return copy(target, []byte{0}), nil
	}
	return wire.Buffer.Read(target)
}

func (wire *fakeWire) Close() error { wire.closed = true; return nil }

func TestOwnedChannelWaitsForAcceptAndRefillsAfterFortyEightCredits(t *testing.T) {
	var opened, refilled int
	owner, err := NewOwnedChannel(context.Background(), OwnedChannelConfig{
		ChannelID: [16]byte{1}, ChannelGeneration: 1, Profile: ProfileID,
		Open: func(context.Context) (Wire, uint64, error) {
			opened++
			return &fakeWire{id: uint64(opened * 4)}, uint64(opened * 4), nil
		},
		Refill: func(context.Context, uint64) error { refilled++; return nil },
	})
	if err != nil {
		t.Fatal(err)
	}
	for index := 0; index < 49; index++ {
		stream, openErr := owner.Open(context.Background())
		if openErr != nil {
			t.Fatalf("open %d: %v", index, openErr)
		}
		if stream.State() != ApplicationStreamAccepted {
			t.Fatalf("stream %d not accepted", index)
		}
	}
	if opened != 49 || refilled != 1 {
		t.Fatalf("opened=%d refilled=%d", opened, refilled)
	}
}

func TestOwnedChannelRetriesTheSameEpochAfterRefillFailure(t *testing.T) {
	var epochs []uint64
	owner, err := NewOwnedChannel(context.Background(), OwnedChannelConfig{
		ChannelID: [16]byte{1}, ChannelGeneration: 1, Profile: ProfileID,
		Open: func(context.Context) (Wire, uint64, error) {
			return &fakeWire{id: 4}, 4, nil
		},
		Refill: func(_ context.Context, epoch uint64) error {
			epochs = append(epochs, epoch)
			if len(epochs) == 1 {
				return errors.New("transient refill failure")
			}
			return nil
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	for index := 0; index < 48; index++ {
		if _, err = owner.Open(context.Background()); err != nil {
			t.Fatal(err)
		}
	}
	if _, err = owner.Open(context.Background()); err == nil {
		t.Fatal("failed refill unexpectedly opened a stream")
	}
	if _, err = owner.Open(context.Background()); err != nil {
		t.Fatalf("retry: %v", err)
	}
	if len(epochs) != 2 || epochs[0] != 2 || epochs[1] != 2 {
		t.Fatalf("refill epochs=%v, want [2 2]", epochs)
	}
}

func TestRejectedCreditExposesNoApplicationStream(t *testing.T) {
	wire := &fakeWire{id: 4}
	wire.accepted = true
	wire.Buffer.WriteByte(1)
	_, err := Admit(context.Background(), ProfileID, func(context.Context) (Wire, uint64, error) {
		return wire, wire.id, nil
	}, [16]byte{1}, 1, 1, 0)
	if err == nil {
		t.Fatal("rejected credit returned an application stream")
	}
}

func TestRotationBoundsTwoGenerationsAndPinsAcceptedDescendant(t *testing.T) {
	factory := func(id string) func(context.Context) (GenerationSession, error) {
		return func(context.Context) (GenerationSession, error) { return &fakeGeneration{id: id}, nil }
	}
	client, err := NewRotationClient(context.Background(), RotationClientConfig{Generations: []GenerationConfig{
		{Generation: 1, ChannelGeneration: 1, ChannelID: [16]byte{1}, Factory: factory("a")},
		{Generation: 2, ChannelGeneration: 1, ChannelID: [16]byte{1}, Factory: factory("b")},
		{Generation: 3, ChannelGeneration: 1, ChannelID: [16]byte{1}, Factory: func(context.Context) (GenerationSession, error) { return nil, errors.New("must not run") }},
	}})
	if err != nil {
		t.Fatal(err)
	}
	streamA, err := client.Open(context.Background(), 1)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = client.Rotate(context.Background(), 2, RotationExplicit); err != nil {
		t.Fatal(err)
	}
	if streamA.State() != ApplicationStreamAccepted {
		t.Fatal("accepted A descendant was not pinned")
	}
	if _, err = client.Open(context.Background(), 1); err == nil {
		t.Fatal("draining A accepted new work")
	}
	if _, err = client.Rotate(context.Background(), 3, RotationExplicit); !errors.Is(err, ErrGenerationCapacity) {
		t.Fatalf("third generation error=%v", err)
	}
}

func TestRotationClientRetriesTheSameEpochAfterRefillFailure(t *testing.T) {
	var epochs []uint64
	session := &fakeGeneration{id: "a", refill: func(epoch uint64) error {
		epochs = append(epochs, epoch)
		if len(epochs) == 1 {
			return errors.New("transient refill failure")
		}
		return nil
	}}
	client, err := NewRotationClient(context.Background(), RotationClientConfig{Generations: []GenerationConfig{
		{Generation: 1, ChannelGeneration: 1, ChannelID: [16]byte{1}, Factory: func(context.Context) (GenerationSession, error) { return session, nil }},
		{Generation: 2, ChannelGeneration: 1, ChannelID: [16]byte{1}, Factory: func(context.Context) (GenerationSession, error) { return &fakeGeneration{id: "b"}, nil }},
	}})
	if err != nil {
		t.Fatal(err)
	}
	for index := 0; index < 48; index++ {
		if _, err = client.Open(context.Background(), 1); err != nil {
			t.Fatal(err)
		}
	}
	if _, err = client.Open(context.Background(), 1); err == nil {
		t.Fatal("failed refill unexpectedly opened a stream")
	}
	if _, err = client.Open(context.Background(), 1); err != nil {
		t.Fatalf("retry: %v", err)
	}
	if len(epochs) != 2 || epochs[0] != 2 || epochs[1] != 2 {
		t.Fatalf("refill epochs=%v, want [2 2]", epochs)
	}
}

type fakeGeneration struct {
	id     string
	refill func(uint64) error
}

func (generation *fakeGeneration) Close() error     { return nil }
func (generation *fakeGeneration) Identity() string { return generation.id }
func (generation *fakeGeneration) Refill(_ context.Context, _ [16]byte, epoch uint64) error {
	if generation.refill != nil {
		return generation.refill(epoch)
	}
	return nil
}
func (generation *fakeGeneration) Open(context.Context) (Wire, uint64, error) {
	wire := &fakeWire{id: 4}
	wire.Buffer.Write([]byte("payload"))
	return wire, wire.id, nil
}

var _ io.ReadWriter = (*fakeWire)(nil)
