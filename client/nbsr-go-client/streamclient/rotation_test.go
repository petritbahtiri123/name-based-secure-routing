package streamclient

import (
	"context"
	"errors"
	"io"
	"testing"
	"time"

	"nbsr.local/client/nbsr-go-client/internal/session"
)

func TestRotationClientUsesDistinctGenerationSessionsAndDrainsA(t *testing.T) {
	a := &fakeGenerationSession{id: "real-a"}
	b := &fakeGenerationSession{id: "real-b"}
	client, err := NewRotationClient(context.Background(), rotationFixture(a, b))
	if err != nil {
		t.Fatal(err)
	}
	streamA, err := client.Open(context.Background(), 1)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := streamA.Write([]byte("A")); err != nil {
		t.Fatal(err)
	}
	result, err := client.Rotate(context.Background(), 2, session.RotationExplicit)
	if err != nil {
		t.Fatal(err)
	}
	if result.Previous.State != session.TransportDraining || result.Current.State != session.TransportCurrent {
		t.Fatalf("handoff=%+v", result)
	}
	if a.id == b.id || client.TransportIdentity(1) != "real-a" || client.TransportIdentity(2) != "real-b" {
		t.Fatal("transport identity collapsed")
	}
	if _, err := client.Open(context.Background(), 1); !errors.Is(err, session.ErrStreamClosed) {
		t.Fatalf("new A stream=%v", err)
	}
	streamB, err := client.Open(context.Background(), 2)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := streamB.Write([]byte("B")); err != nil {
		t.Fatal(err)
	}
	if len(b.payloads) != 1 || string(b.payloads[0]) != "B" {
		t.Fatalf("B payloads=%q", b.payloads)
	}
	if _, err := client.Rotate(context.Background(), 3, session.RotationExplicit); !errors.Is(err, session.ErrGenerationCapacity) {
		t.Fatalf("C=%v", err)
	}
	if err := streamA.Close(); err != nil {
		t.Fatal(err)
	}
	if err := client.CloseGeneration(1); err != nil {
		t.Fatal(err)
	}
	if !a.closed {
		t.Fatal("A transport open")
	}
	if identity := client.TransportIdentity(1); identity != "" {
		t.Fatalf("closed A retained identity %q", identity)
	}
	if current, err := client.Current(); err != nil || current.Generation != 2 {
		t.Fatalf("current=%+v %v", current, err)
	}
	if streamA.State() != session.ApplicationStreamClosed {
		t.Fatalf("A stream state=%v", streamA.State())
	}
	if streamB.State() != session.ApplicationStreamAccepted {
		t.Fatalf("B stream state=%v", streamB.State())
	}
}

func TestRotationClientDrainDeadlineRemovesCachedGenerationState(t *testing.T) {
	a := &fakeGenerationSession{id: "real-a"}
	b := &fakeGenerationSession{id: "real-b"}
	config := rotationFixture(a, b)
	config.DrainTimeout = 20 * time.Millisecond
	client, err := NewRotationClient(context.Background(), config)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = client.Rotate(context.Background(), 2, session.RotationExplicit); err != nil {
		t.Fatal(err)
	}
	deadline := time.Now().Add(time.Second)
	for client.TransportIdentity(1) != "" && time.Now().Before(deadline) {
		time.Sleep(time.Millisecond)
	}
	client.mu.RLock()
	_, retained := client.handles[1]
	client.mu.RUnlock()
	if retained || client.TransportIdentity(1) != "" {
		t.Fatal("deadline teardown retained A generation-local state")
	}
}

type fakeGenerationSession struct {
	id       string
	closed   bool
	next     uint64
	payloads [][]byte
}

func (s *fakeGenerationSession) Close() error     { s.closed = true; return nil }
func (s *fakeGenerationSession) Identity() string { return s.id }
func (s *fakeGenerationSession) Open(context.Context) (Wire, uint64, error) {
	s.next += 4
	return &fakeWire{owner: s}, s.next, nil
}
func (s *fakeGenerationSession) Refill(context.Context, [16]byte, uint64) error { return nil }

type fakeWire struct {
	owner *fakeGenerationSession
	read  bool
}

func (w *fakeWire) Write(p []byte) (int, error) {
	if len(p) > 20 {
		return len(p), nil
	}
	w.owner.payloads = append(w.owner.payloads, append([]byte(nil), p...))
	return len(p), nil
}
func (w *fakeWire) Read(p []byte) (int, error) {
	if !w.read {
		w.read = true
		p[0] = 0
		return 1, nil
	}
	return 0, io.EOF
}
func (w *fakeWire) Close() error { return nil }

func rotationFixture(a, b GenerationSession) RotationClientConfig {
	return RotationClientConfig{Now: 1_900_000_000, ExpiresAt: 1_900_001_000, AuthorityGeneration: 1, DeviceID: filled(9), PolicyDigest: filled(10), ServiceDigest: filled(11), RouteGrantDigest: filled(12), SourceOperator: "source", Gateway: "gateway", ServiceIdentity: "svc.example", Profile: ProfileID, Transport: "quic", DrainTimeout: time.Second, Generations: []GenerationConfig{{Generation: 1, ChannelGeneration: 1, ChannelID: [16]byte{1}, ProofThumbprint: filled(21), Factory: func(context.Context) (GenerationSession, error) { return a, nil }}, {Generation: 2, ChannelGeneration: 1, ChannelID: [16]byte{2}, ProofThumbprint: filled(22), Factory: func(context.Context) (GenerationSession, error) { return b, nil }}, {Generation: 3, ChannelGeneration: 1, ChannelID: [16]byte{3}, ProofThumbprint: filled(23), Factory: func(context.Context) (GenerationSession, error) { return &fakeGenerationSession{id: "real-c"}, nil }}}}
}
