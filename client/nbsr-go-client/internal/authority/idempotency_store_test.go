package authority

import (
	"bytes"
	"context"
	"errors"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestFileIdempotencyStoreReplaysExactTerminalBytesAndRejectsConflict(t *testing.T) {
	store := newTestFileIdempotencyStore(t, filepath.Join(t.TempDir(), "acp-idempotency.cbor"), 8, 2<<20)
	request := testIdempotencyRequest(10, 20, 128*1024)

	claim, err := store.Begin(context.Background(), request)
	if err != nil {
		t.Fatal(err)
	}
	if claim.Status != IdempotencyOwner {
		t.Fatalf("first claim status = %v, want owner", claim.Status)
	}
	terminal := []byte{0xd2, 0x84, 0x01, 0x02, 0x03}
	if err := store.Complete(context.Background(), request.Key, request.Digest, terminal); err != nil {
		t.Fatal(err)
	}

	replay, err := store.Begin(context.Background(), request)
	if err != nil {
		t.Fatal(err)
	}
	if replay.Status != IdempotencyReplay || !bytes.Equal(replay.Terminal, terminal) {
		t.Fatalf("replay = (%v, %x), want exact terminal %x", replay.Status, replay.Terminal, terminal)
	}
	replay.Terminal[0] ^= 0xff
	replayAgain, err := store.Begin(context.Background(), request)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(replayAgain.Terminal, terminal) {
		t.Fatal("caller mutation changed durable terminal bytes")
	}

	conflicting := request
	conflicting.Digest[0] ^= 0xff
	conflict, err := store.Begin(context.Background(), conflicting)
	if err != nil {
		t.Fatal(err)
	}
	if conflict.Status != IdempotencyConflict || conflict.Terminal != nil {
		t.Fatalf("conflict = (%v, %x), want conflict without overwritten terminal", conflict.Status, conflict.Terminal)
	}
}

func TestFileIdempotencyStorePersistsTerminalAndPendingFenceAcrossRestart(t *testing.T) {
	path := filepath.Join(t.TempDir(), "acp-idempotency.cbor")
	store := newTestFileIdempotencyStore(t, path, 8, 2<<20)
	terminalRequest := testIdempotencyRequest(10, 20, 128*1024)
	pendingRequest := testIdempotencyRequest(11, 20, 128*1024)
	pendingRequest.Key.RequestID[0]++
	pendingRequest.Digest[0]++

	if claim, err := store.Begin(context.Background(), terminalRequest); err != nil || claim.Status != IdempotencyOwner {
		t.Fatalf("terminal begin = (%v, %v)", claim.Status, err)
	}
	terminal := []byte("exact-signed-terminal")
	if err := store.Complete(context.Background(), terminalRequest.Key, terminalRequest.Digest, terminal); err != nil {
		t.Fatal(err)
	}
	if claim, err := store.Begin(context.Background(), pendingRequest); err != nil || claim.Status != IdempotencyOwner {
		t.Fatalf("pending begin = (%v, %v)", claim.Status, err)
	}
	if err := store.Close(); err != nil {
		t.Fatal(err)
	}

	reopened := newTestFileIdempotencyStore(t, path, 8, 2<<20)
	if reopened.Scope() != IdempotencyStoreSingleNode {
		t.Fatalf("scope = %v, want explicit single-node", reopened.Scope())
	}
	replay, err := reopened.Begin(context.Background(), terminalRequest)
	if err != nil || replay.Status != IdempotencyReplay || !bytes.Equal(replay.Terminal, terminal) {
		t.Fatalf("restart replay = (%v, %x, %v)", replay.Status, replay.Terminal, err)
	}
	pending, err := reopened.Begin(context.Background(), pendingRequest)
	if err != nil || pending.Status != IdempotencyPending {
		t.Fatalf("restart pending = (%v, %v), want fenced pending", pending.Status, err)
	}
}

func TestFileIdempotencyStoreExpiresWithinConfiguredGraceAndReclaimsBounds(t *testing.T) {
	store := newTestFileIdempotencyStore(t, filepath.Join(t.TempDir(), "acp-idempotency.cbor"), 1, 256*1024)
	first := testIdempotencyRequest(10, 20, 128*1024)
	if claim, err := store.Begin(context.Background(), first); err != nil || claim.Status != IdempotencyOwner {
		t.Fatalf("first begin = (%v, %v)", claim.Status, err)
	}

	second := testIdempotencyRequest(10, 20, 128*1024)
	second.Key.RequestID[0]++
	second.Digest[0]++
	if _, err := store.Begin(context.Background(), second); !errors.Is(err, ErrCacheCapacity) {
		t.Fatalf("bounded-entry error = %v, want ErrCacheCapacity", err)
	}

	second.NowUnix = first.DeadlineUnix + 60
	second.DeadlineUnix = second.NowUnix + 10
	claim, err := store.Begin(context.Background(), second)
	if err != nil || claim.Status != IdempotencyOwner {
		t.Fatalf("post-grace begin = (%v, %v), want reclaimed owner", claim.Status, err)
	}
	old := first
	old.NowUnix = second.NowUnix
	old.DeadlineUnix = old.NowUnix + 10
	claim, err = store.Begin(context.Background(), old)
	if err != nil || claim.Status != IdempotencyConflict {
		// The original key was reclaimed, but second currently consumes the sole
		// entry. Capacity, not stale replay, is the acceptable bounded result.
		if !errors.Is(err, ErrCacheCapacity) {
			t.Fatalf("expired original = (%v, %v), want no stale replay", claim.Status, err)
		}
	}
}

func TestFileIdempotencyStoreReservesTerminalBytesBeforeEvaluation(t *testing.T) {
	store := newTestFileIdempotencyStore(t, filepath.Join(t.TempDir(), "acp-idempotency.cbor"), 4, 1024)
	tooLarge := testIdempotencyRequest(10, 20, 2048)
	if _, err := store.Begin(context.Background(), tooLarge); !errors.Is(err, ErrCacheCapacity) {
		t.Fatalf("reservation error = %v, want ErrCacheCapacity", err)
	}

	fits := testIdempotencyRequest(10, 20, 256)
	claim, err := store.Begin(context.Background(), fits)
	if err != nil || claim.Status != IdempotencyOwner {
		t.Fatalf("bounded reservation = (%v, %v)", claim.Status, err)
	}
	if err := store.Complete(context.Background(), fits.Key, fits.Digest, make([]byte, 257)); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("oversized completion error = %v, want ErrInvalidAuthority", err)
	}
}

func TestFileIdempotencyStoreFailsClosedForReplicaAndLockMisconfiguration(t *testing.T) {
	path := filepath.Join(t.TempDir(), "acp-idempotency.cbor")
	base := FileIdempotencyStoreConfig{
		Path: path, DeploymentMode: IdempotencyDeploymentSingleNode, ReplicaCount: 1,
		MaxEntries: 8, MaxBytes: 2 << 20, CleanupGraceSeconds: 60,
	}
	for name, mutate := range map[string]func(*FileIdempotencyStoreConfig){
		"multi-replica": func(config *FileIdempotencyStoreConfig) { config.ReplicaCount = 2 },
		"implicit-mode": func(config *FileIdempotencyStoreConfig) { config.DeploymentMode = "" },
		"excess-grace":  func(config *FileIdempotencyStoreConfig) { config.CleanupGraceSeconds = 61 },
	} {
		t.Run(name, func(t *testing.T) {
			config := base
			mutate(&config)
			if _, err := NewFileIdempotencyStore(config); !errors.Is(err, ErrInvalidLimits) {
				t.Fatalf("error = %v, want ErrInvalidLimits", err)
			}
		})
	}

	first, err := NewFileIdempotencyStore(base)
	if err != nil {
		t.Fatal(err)
	}
	defer first.Close()
	if _, err := NewFileIdempotencyStore(base); !errors.Is(err, ErrStorageBusy) {
		t.Fatalf("second-process lock error = %v, want ErrStorageBusy", err)
	}
}

func TestFileIdempotencyStoreFailsClosedOnCorruptRestartState(t *testing.T) {
	path := filepath.Join(t.TempDir(), "acp-idempotency.cbor")
	store := newTestFileIdempotencyStore(t, path, 8, 2<<20)
	if err := store.Close(); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte{0xff, 0x00, 0x01}, 0o600); err != nil {
		t.Fatal(err)
	}
	config := testFileIdempotencyStoreConfig(path, 8, 2<<20)
	if _, err := NewFileIdempotencyStore(config); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("corrupt restart error = %v, want ErrInvalidAuthority", err)
	}
}

func TestFileIdempotencyStoreNilReceiverFailsClosed(t *testing.T) {
	var store *FileIdempotencyStore
	request := testIdempotencyRequest(10, 20, 128*1024)
	if _, err := store.Begin(context.Background(), request); !errors.Is(err, ErrClosed) {
		t.Fatalf("nil Begin error = %v, want ErrClosed", err)
	}
	if err := store.Complete(context.Background(), request.Key, request.Digest, []byte("terminal")); !errors.Is(err, ErrClosed) {
		t.Fatalf("nil Complete error = %v, want ErrClosed", err)
	}
}

func TestFileIdempotencyStoreSweepsExpiredRecordsWhileIdleAndOnOpen(t *testing.T) {
	for _, test := range []struct {
		name      string
		closeIdle bool
	}{
		{name: "scheduled idle sweep"},
		{name: "open sweep", closeIdle: true},
	} {
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			path := filepath.Join(t.TempDir(), "acp-idempotency.cbor")
			config := testFileIdempotencyStoreConfig(path, 8, 2<<20)
			config.CleanupGraceSeconds = 1
			config.NowUnix = func() uint64 { return uint64(time.Now().Unix()) }
			store, err := NewFileIdempotencyStore(config)
			if err != nil {
				t.Fatal(err)
			}
			defer store.Close()
			now := uint64(time.Now().Unix())
			request := testIdempotencyRequest(now, now+1, 128*1024)
			if claim, err := store.Begin(context.Background(), request); err != nil || claim.Status != IdempotencyOwner {
				t.Fatalf("begin = (%v, %v)", claim.Status, err)
			}
			if err := store.Complete(context.Background(), request.Key, request.Digest, []byte("signed-terminal")); err != nil {
				t.Fatal(err)
			}
			if test.closeIdle {
				if err := store.Close(); err != nil {
					t.Fatal(err)
				}
			}

			waitUntilUnix(t, request.DeadlineUnix+config.CleanupGraceSeconds)
			if !test.closeIdle {
				waitForIdempotencyRecordCount(t, store, 0)
				if err := store.Close(); err != nil {
					t.Fatal(err)
				}
			}
			reopened, err := NewFileIdempotencyStore(config)
			if err != nil {
				t.Fatal(err)
			}
			defer reopened.Close()
			reopened.mu.Lock()
			got := len(reopened.records)
			reopened.mu.Unlock()
			if got != 0 {
				t.Fatalf("restart retained %d expired records, want zero", got)
			}
		})
	}
}

func waitUntilUnix(t *testing.T, want uint64) {
	t.Helper()
	for uint64(time.Now().Unix()) < want {
		time.Sleep(10 * time.Millisecond)
	}
}

func waitForIdempotencyRecordCount(t *testing.T, store *FileIdempotencyStore, want int) {
	t.Helper()
	deadline := time.Now().Add(1500 * time.Millisecond)
	for time.Now().Before(deadline) {
		store.mu.Lock()
		got := len(store.records)
		store.mu.Unlock()
		if got == want {
			return
		}
		time.Sleep(10 * time.Millisecond)
	}
	store.mu.Lock()
	got := len(store.records)
	store.mu.Unlock()
	t.Fatalf("idle record count = %d, want %d", got, want)
}

func testIdempotencyRequest(now, deadline uint64, maximum uint64) IdempotencyRequest {
	return IdempotencyRequest{
		Key: IdempotencyKey{
			Namespace: "authority", SourceOperator: "source.operator", Profile: "nbsr-federation-dev-v1",
			ActorID: bytes32ForSeed(0x21), ActorGeneration: 3, Operation: string(ACPOperationAcquire),
			RequestID: RequestID{1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16},
		},
		Digest: bytes32ForSeed(0x22), DeadlineUnix: deadline, NowUnix: now, MaxTerminalBytes: maximum,
	}
}

func newTestFileIdempotencyStore(t *testing.T, path string, entries int, maximum uint64) *FileIdempotencyStore {
	t.Helper()
	store, err := NewFileIdempotencyStore(testFileIdempotencyStoreConfig(path, entries, maximum))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = store.Close() })
	return store
}

func testFileIdempotencyStoreConfig(path string, entries int, maximum uint64) FileIdempotencyStoreConfig {
	return FileIdempotencyStoreConfig{
		Path: path, DeploymentMode: IdempotencyDeploymentSingleNode, ReplicaCount: 1,
		MaxEntries: entries, MaxBytes: maximum, CleanupGraceSeconds: 60,
		NowUnix: func() uint64 { return 10 },
	}
}
