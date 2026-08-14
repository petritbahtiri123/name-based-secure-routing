package authority

import (
	"bytes"
	"context"
	"crypto/sha256"
	"errors"
	"io"
	"reflect"
	"testing"

	"nbsr.local/client/nbsr-go-client/internal/identity"
)

func TestProviderResultCannotBeUsedAsVerifiedAuthority(t *testing.T) {
	providerType := reflect.TypeOf(ProviderGrant{})
	verifiedType := reflect.TypeOf(VerifiedAuthority{})
	if providerType.AssignableTo(verifiedType) || providerType.ConvertibleTo(verifiedType) {
		t.Fatal("provider grant bypasses verified authority boundary")
	}
	for i := range providerType.NumField() {
		if providerType.Field(i).Name == "Verified" {
			t.Fatal("provider grant must not carry a verification boolean")
		}
	}
}

func TestProviderMethodSignatures(t *testing.T) {
	var _ AuthorityProvider = fakeProvider{}
}

func TestAuthorityErrorSentinels(t *testing.T) {
	for _, sentinel := range []error{
		ErrUnknownIdentity, ErrInvalidKeyPurpose, ErrInvalidAuthority, ErrSignatureFailure,
		ErrBindingMismatch, ErrExpired, ErrRevoked, ErrStaleFreshness, ErrStaleGeneration,
		ErrGenerationRollback, ErrCacheCapacity, ErrPendingCapacity, ErrWaiterCapacity,
		ErrRequestConflict, ErrRequestAmbiguous, ErrProviderUnavailable, ErrPolicyDenied,
		ErrTerminalEnrollment, ErrInvalidLimits, ErrInvalidTransition, ErrClosed, ErrNotReady,
		ErrAccountingOverflow,
	} {
		if !errors.Is(sentinel, sentinel) {
			t.Fatalf("sentinel %v does not match itself", sentinel)
		}
	}
}

func TestEveryAuthorityLimitRequired(t *testing.T) {
	tests := []struct {
		name string
		zero func(*Limits)
	}{
		{"cache entries", func(l *Limits) { l.MaxCacheEntries = 0 }},
		{"pending", func(l *Limits) { l.MaxPending = 0 }},
		{"waiters", func(l *Limits) { l.MaxWaitersPerPending = 0 }},
		{"request records", func(l *Limits) { l.MaxRequestRecords = 0 }},
		{"cache bytes", func(l *Limits) { l.MaxCacheBytes = 0 }},
		{"pending bytes", func(l *Limits) { l.MaxPendingBytes = 0 }},
		{"request bytes", func(l *Limits) { l.MaxRequestBytes = 0 }},
		{"grant bytes", func(l *Limits) { l.MaxGrantBytes = 0 }},
		{"checkpoint evidence bytes", func(l *Limits) { l.MaxCheckpointEvidenceBytes = 0 }},
		{"service identity bytes", func(l *Limits) { l.MaxServiceIdentityBytes = 0 }},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			l := validLimits()
			tt.zero(&l)
			if !errors.Is(l.Validate(), ErrInvalidLimits) {
				t.Fatal("zero limit accepted")
			}
		})
	}
}

func TestRequestIDRequiresSixteenNonZeroBytes(t *testing.T) {
	source, err := NewCryptoRequestIDSource(bytes.NewReader(bytes.Repeat([]byte{7}, 16)))
	if err != nil {
		t.Fatalf("NewCryptoRequestIDSource: %v", err)
	}
	id, err := source.NewRequestID()
	if err != nil {
		t.Fatalf("NewRequestID: %v", err)
	}
	if id[0] != 7 || id[15] != 7 {
		t.Fatalf("request ID = %x, want injected bytes", id)
	}

	zeroSource, err := NewCryptoRequestIDSource(bytes.NewReader(make([]byte, 16)))
	if err != nil {
		t.Fatalf("NewCryptoRequestIDSource zero: %v", err)
	}
	if _, err := zeroSource.NewRequestID(); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("zero request ID error = %v, want ErrInvalidAuthority", err)
	}

	shortSource, err := NewCryptoRequestIDSource(bytes.NewReader([]byte{1}))
	if err != nil {
		t.Fatalf("NewCryptoRequestIDSource short: %v", err)
	}
	if _, err := shortSource.NewRequestID(); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("short request ID error = %v, want ErrInvalidAuthority", err)
	}
}

func TestAuthorityValidationCanonicalizesIntentAndCopiesMutableInput(t *testing.T) {
	limits := validLimits()
	req := validAcquireRequest()
	req.Intent.TargetEdges = []string{"edge-z", "edge-a"}
	req.Key.TargetEdgeSetDigest = targetEdgeSetDigest([]string{"edge-a", "edge-z"})

	normalized, err := validateAcquireRequest(req, limits)
	if err != nil {
		t.Fatalf("validateAcquireRequest: %v", err)
	}
	if got, want := normalized.Intent.TargetEdges, []string{"edge-a", "edge-z"}; !reflect.DeepEqual(got, want) {
		t.Fatalf("target edges = %q, want %q", got, want)
	}
	req.Intent.Canonical[0] ^= 0xff
	req.Intent.TargetEdges[0] = "mutated"
	if normalized.Intent.Canonical[0] == req.Intent.Canonical[0] {
		t.Fatal("canonical bytes were not copied")
	}
	if normalized.Intent.TargetEdges[0] == "mutated" {
		t.Fatal("target edges were not copied")
	}
}

func TestAuthorityValidationRejectsDigestMismatchAndOversizedInputs(t *testing.T) {
	limits := validLimits()
	req := validAcquireRequest()
	req.Intent.Digest[0] ^= 0xff
	if _, err := validateAcquireRequest(req, limits); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("canonical digest mismatch error = %v, want ErrInvalidAuthority", err)
	}

	req = validAcquireRequest()
	req.Intent.ServiceIdentity = string(bytes.Repeat([]byte{'s'}, limits.MaxServiceIdentityBytes+1))
	if _, err := validateAcquireRequest(req, limits); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("oversized service identity error = %v, want ErrInvalidAuthority", err)
	}

	req = validAcquireRequest()
	req.Intent.Canonical = bytes.Repeat([]byte{'c'}, int(limits.MaxRequestBytes)+1)
	req.Intent.Digest = sha256.Sum256(req.Intent.Canonical)
	if _, err := validateAcquireRequest(req, limits); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("oversized request error = %v, want ErrInvalidAuthority", err)
	}
}

func TestAuthorityValidationAcceptsNilWorkloadAndBindsPresentWorkload(t *testing.T) {
	req := validAcquireRequest()
	if _, err := validateAcquireRequest(req, validLimits()); err != nil {
		t.Fatalf("nil workload rejected: %v", err)
	}

	workload := identity.WorkloadPolicyContext{SubjectDigest: nonZero32(17), PolicyGeneration: 3}
	req.Workload = &workload
	req.Key.WorkloadDigest = workload.SubjectDigest
	req.Key.WorkloadGeneration = workload.PolicyGeneration
	if _, err := validateAcquireRequest(req, validLimits()); err != nil {
		t.Fatalf("matching workload rejected: %v", err)
	}
	req.Key.WorkloadGeneration++
	if _, err := validateAcquireRequest(req, validLimits()); !errors.Is(err, ErrBindingMismatch) {
		t.Fatalf("mismatched workload error = %v, want ErrBindingMismatch", err)
	}
}

func TestAuthorityProviderCandidateIsBoundedAndCopied(t *testing.T) {
	grant := ProviderGrant{ExactRouteGrant: []byte{1, 2, 3}, Profile: "profile", AuthorityGeneration: 1, Checkpoint: nonZeroCheckpoint()}
	copy, err := copyProviderGrant(grant, validLimits())
	if err != nil {
		t.Fatalf("copyProviderGrant: %v", err)
	}
	grant.ExactRouteGrant[0] = 9
	if copy.ExactRouteGrant[0] != 1 {
		t.Fatal("provider grant bytes were not copied")
	}
	grant.ExactRouteGrant = bytes.Repeat([]byte{1}, validLimits().MaxGrantBytes+1)
	if _, err := copyProviderGrant(grant, validLimits()); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("oversized provider grant error = %v, want ErrInvalidAuthority", err)
	}
}

func TestAuthorityConstructorRejectsNilDependencies(t *testing.T) {
	clock := fakeClock{}
	provider := fakeProvider{}
	verifier := &Verifier{}
	checkpointVerifier := fakeCheckpointVerifier{}
	floorStore := fakeFloorStore{}
	observer := noopObserver{}
	type dependencyCase struct {
		name       string
		clock      Clock
		provider   AuthorityProvider
		verifier   *Verifier
		checkpoint CheckpointEvidenceVerifier
		store      GenerationFloorStore
		observer   Observer
	}
	cases := []dependencyCase{
		{"clock", nil, provider, verifier, checkpointVerifier, floorStore, observer},
		{"provider", clock, nil, verifier, checkpointVerifier, floorStore, observer},
		{"verifier", clock, provider, nil, checkpointVerifier, floorStore, observer},
		{"checkpoint verifier", clock, provider, verifier, nil, floorStore, observer},
		{"floor store", clock, provider, verifier, checkpointVerifier, nil, observer},
		{"observer", clock, provider, verifier, checkpointVerifier, floorStore, nil},
	}
	var typedNilClock *fakeClock
	var typedNilProvider *fakeProvider
	var typedNilCheckpointVerifier *fakeCheckpointVerifier
	var typedNilFloorStore *fakeFloorStore
	var typedNilObserver *noopObserver
	cases = append(cases,
		dependencyCase{"typed nil clock", typedNilClock, provider, verifier, checkpointVerifier, floorStore, observer},
		dependencyCase{"typed nil provider", clock, typedNilProvider, verifier, checkpointVerifier, floorStore, observer},
		dependencyCase{"typed nil checkpoint verifier", clock, provider, verifier, typedNilCheckpointVerifier, floorStore, observer},
		dependencyCase{"typed nil floor store", clock, provider, verifier, checkpointVerifier, typedNilFloorStore, observer},
		dependencyCase{"typed nil observer", clock, provider, verifier, checkpointVerifier, floorStore, typedNilObserver},
	)
	for _, tt := range cases {
		t.Run(tt.name, func(t *testing.T) {
			_, err := NewManager(validLimits(), tt.clock, tt.provider, tt.verifier, tt.checkpoint, tt.store, tt.observer)
			if !errors.Is(err, ErrInvalidAuthority) {
				t.Fatalf("NewManager error = %v, want ErrInvalidAuthority", err)
			}
		})
	}
}

func TestObserverRunsAfterMutationUnlock(t *testing.T) {
	var manager *Manager
	observer := observerFunc(func(Event) {
		if !manager.mu.TryLock() {
			t.Error("observer called while manager mutation lock is held")
			return
		}
		manager.mu.Unlock()
	})
	var err error
	manager, err = NewManager(validLimits(), fakeClock{}, fakeProvider{}, &Verifier{}, fakeCheckpointVerifier{}, fakeFloorStore{}, observer)
	if err != nil {
		t.Fatalf("NewManager: %v", err)
	}
	if err := manager.mutate(func() ([]Event, error) {
		return []Event{{Kind: EventAcquireRequested}}, nil
	}); err != nil {
		t.Fatalf("mutate: %v", err)
	}
}

func TestProviderFreshnessCandidateIsBoundedAndCopied(t *testing.T) {
	freshness := ProviderFreshness{SourceOperator: "source-operator", Profile: "profile", Evidence: []byte{1, 2, 3}}
	copy, err := copyProviderFreshness(freshness, validLimits())
	if err != nil {
		t.Fatalf("copyProviderFreshness: %v", err)
	}
	freshness.Evidence[0] = 9
	if copy.Evidence[0] != 1 {
		t.Fatal("provider freshness evidence was not copied")
	}
	freshness.Evidence = bytes.Repeat([]byte{1}, validLimits().MaxCheckpointEvidenceBytes+1)
	if _, err := copyProviderFreshness(freshness, validLimits()); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("oversized provider freshness error = %v, want ErrInvalidAuthority", err)
	}
}

func validLimits() Limits {
	return Limits{
		MaxCacheEntries:            2,
		MaxPending:                 2,
		MaxWaitersPerPending:       2,
		MaxRequestRecords:          2,
		MaxCacheBytes:              64,
		MaxPendingBytes:            64,
		MaxRequestBytes:            64,
		MaxGrantBytes:              64,
		MaxCheckpointEvidenceBytes: 64,
		MaxServiceIdentityBytes:    32,
	}
}

func validAcquireRequest() AcquireRequest {
	canonical := []byte("canonical route intent")
	intent := RouteIntent{
		Canonical:       canonical,
		Digest:          sha256.Sum256(canonical),
		ServiceIdentity: "service.example",
		SourceOperator:  "source-operator",
		SourceEdge:      "source-edge",
		TargetOperator:  "target-operator",
		TargetEdges:     []string{"target-edge"},
		Transport:       "quic",
		Port:            443,
		RecordSequence:  1,
		PolicyHash:      nonZeroPolicy(),
		RouteID:         [16]byte{1},
		LeaseID:         [16]byte{2},
		ExpiresAt:       1,
	}
	device := identity.DeviceIdentity{ID: nonZero32(3), SourceOperatorID: intent.SourceOperator, CredentialGeneration: 1}
	return AcquireRequest{
		Key: AuthorityKey{
			IntentDigest:        intent.Digest,
			ServiceDigest:       nonZero32(4),
			SourceOperator:      intent.SourceOperator,
			SourceEdge:          intent.SourceEdge,
			TargetOperator:      intent.TargetOperator,
			TargetEdgeSetDigest: targetEdgeSetDigest(intent.TargetEdges),
			Profile:             "profile",
			Transport:           intent.Transport,
			Port:                intent.Port,
			DeviceID:            device.ID,
			DeviceGeneration:    device.CredentialGeneration,
			TSGeneration:        1,
			ProofThumbprint:     nonZero32(5),
			PolicyHash:          intent.PolicyHash,
			PolicyGeneration:    1,
			AuthorityGeneration: 1,
		},
		Intent:       intent,
		Device:       device,
		RequestID:    RequestID{1},
		DeadlineUnix: 1,
	}
}

func nonZero32(value byte) [32]byte       { return [32]byte{value} }
func nonZeroPolicy() PolicyDigest         { return PolicyDigest(nonZero32(6)) }
func nonZeroCheckpoint() CheckpointDigest { return CheckpointDigest(nonZero32(7)) }

type fakeProvider struct{}

func (fakeProvider) Acquire(context.Context, AcquireRequest) (ProviderGrant, error) {
	return ProviderGrant{}, io.EOF
}
func (fakeProvider) Renew(context.Context, RenewRequest) (ProviderGrant, error) {
	return ProviderGrant{}, io.EOF
}
func (fakeProvider) Freshness(context.Context, FreshnessRequest) (ProviderFreshness, error) {
	return ProviderFreshness{}, io.EOF
}
func (fakeProvider) Close() error { return nil }

type fakeClock struct{}

func (fakeClock) NowUnix() uint64 { return 1 }

type fakeCheckpointVerifier struct{}

func (fakeCheckpointVerifier) VerifyFreshnessEvidence(context.Context, ProviderFreshness, FreshnessRequest, uint64) (CheckpointClaims, error) {
	return CheckpointClaims{}, io.EOF
}

type fakeFloorStore struct{}

func (fakeFloorStore) Load(context.Context, string, string) (SignedGenerationFloor, error) {
	return SignedGenerationFloor{}, io.EOF
}
func (fakeFloorStore) StoreHigher(context.Context, SignedGenerationFloor) error { return nil }

type observerFunc func(Event)

func (f observerFunc) Observe(event Event) { f(event) }
