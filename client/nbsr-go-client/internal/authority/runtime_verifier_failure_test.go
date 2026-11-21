package authority

import (
	"context"
	"errors"
	"testing"

	"nbsr.local/client/nbsr-go-client/internal/identity"
)

type runtimeTestFreshnessVerifierFunc func(context.Context, ProviderFreshness, FreshnessRequest, uint64) (CheckpointClaims, error)

func (verify runtimeTestFreshnessVerifierFunc) VerifyFreshnessEvidence(ctx context.Context, freshness ProviderFreshness, request FreshnessRequest, now uint64) (CheckpointClaims, error) {
	return verify(ctx, freshness, request, now)
}

func TestClientRuntimeRefreshInternalVerifierFailureRejectsNewAuthorityWork(t *testing.T) {
	ctx := context.Background()
	const now = uint64(100)
	device := runtimeTestIdentity()
	store := NewMemoryEnrollmentStateStore()
	if err := store.Store(ctx, device); err != nil {
		t.Fatal(err)
	}
	freshness := runtimeFreshnessRequest(device, now)
	provider := &runtimeRecordingProvider{freshness: ProviderFreshness{
		SourceOperator: freshness.SourceOperator,
		Profile:        freshness.Profile,
		Evidence:       []byte("fresh"),
	}}
	internalErr := errors.New("test: internal verifier failure")
	verifyCalls := 0
	verify := runtimeTestFreshnessVerifierFunc(func(ctx context.Context, supplied ProviderFreshness, request FreshnessRequest, now uint64) (CheckpointClaims, error) {
		verifyCalls++
		if verifyCalls == 2 {
			return CheckpointClaims{}, internalErr
		}
		return (runtimeCheckpointVerifier{}).VerifyFreshnessEvidence(ctx, supplied, request, now)
	})
	gate, err := NewRestartGate(NewMemoryGenerationFloorStore(1024), verify, testClock{now: now}, noopObserver{})
	if err != nil {
		t.Fatal(err)
	}
	runtime, err := NewClientRuntime(ClientRuntimeConfig{
		SourceOperator: freshness.SourceOperator, Profile: freshness.Profile, EnrollmentStore: store,
		ProviderFactory: func(identity.DeviceIdentity) (AuthorityProvider, error) { return provider, nil },
		RestartGate:     gate, NowUnix: func() uint64 { return now },
	})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := runtime.Close(); err != nil {
			t.Error(err)
		}
	})
	if err := runtime.StartPersisted(ctx, freshness); err != nil {
		t.Fatal(err)
	}
	if !runtime.Ready() {
		t.Fatal("runtime not ready after verified startup")
	}

	freshness.AfterGeneration = 1
	if err := runtime.Refresh(ctx, freshness); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("Refresh: got %v; want ErrInvalidAuthority", err)
	}
	if verifyCalls != 2 || runtime.Ready() {
		t.Errorf("after refresh: verifier calls=%d ready=%v; want 2 and false", verifyCalls, runtime.Ready())
	}
	request := AcquireRequest{Device: device, Key: AuthorityKey{DeviceID: device.ID, DeviceGeneration: device.CredentialGeneration}}
	if _, err := runtime.Acquire(ctx, request); !errors.Is(err, ErrNotReady) {
		t.Errorf("Acquire: got %v; want ErrNotReady", err)
	}
	if _, err := runtime.Renew(ctx, RenewRequest{AcquireRequest: request}); !errors.Is(err, ErrNotReady) {
		t.Errorf("Renew: got %v; want ErrNotReady", err)
	}
	if got := provider.operations(); len(got) != 2 || got[0] != "freshness" || got[1] != "freshness" {
		t.Errorf("provider operations: got %v; want [freshness freshness]", got)
	}
}
