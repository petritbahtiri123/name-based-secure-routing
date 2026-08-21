package authority

import (
	"context"
	"errors"
	"path/filepath"
	"sync"
	"sync/atomic"
	"testing"

	"nbsr.local/client/nbsr-go-client/internal/identity"
)

func TestClientRuntimeRequiresFreshnessBeforeReadyAndAfterRestart(t *testing.T) {
	device := runtimeTestIdentity()
	store := NewMemoryEnrollmentStateStore()
	if err := store.Store(context.Background(), device); err != nil {
		t.Fatal(err)
	}
	provider := &runtimeRecordingProvider{freshness: ProviderFreshness{SourceOperator: "source.operator", Profile: "profile", Evidence: []byte("fresh")}}
	gate, err := NewRestartGate(NewMemoryGenerationFloorStore(1024), runtimeCheckpointVerifier{}, testClock{now: 100}, noopObserver{})
	if err != nil {
		t.Fatal(err)
	}
	runtime, err := NewClientRuntime(ClientRuntimeConfig{
		SourceOperator: "source.operator", Profile: "profile", EnrollmentStore: store,
		ProviderFactory: func(got identity.DeviceIdentity) (AuthorityProvider, error) {
			if got != device {
				t.Fatal("provider constructed with wrong identity")
			}
			return provider, nil
		},
		RestartGate: gate, NowUnix: func() uint64 { return 100 },
	})
	if err != nil {
		t.Fatal(err)
	}
	if runtime.Ready() {
		t.Fatal("new runtime was ready before startup freshness")
	}
	freshness := runtimeFreshnessRequest(device, 100)
	if err := runtime.StartPersisted(context.Background(), freshness); err != nil {
		t.Fatal(err)
	}
	if !runtime.Ready() || provider.operations()[0] != "freshness" {
		t.Fatalf("startup ready=%v operations=%v", runtime.Ready(), provider.operations())
	}
	request := AcquireRequest{Device: device, Key: AuthorityKey{DeviceID: device.ID, DeviceGeneration: device.CredentialGeneration}}
	if _, err := runtime.Acquire(context.Background(), request); err != nil {
		t.Fatal(err)
	}
	if _, err := runtime.Renew(context.Background(), RenewRequest{AcquireRequest: request}); err != nil {
		t.Fatal(err)
	}
	if err := runtime.Restart(context.Background(), freshness); err != nil {
		t.Fatal(err)
	}
	if !runtime.Ready() {
		t.Fatal("runtime did not become ready after restart freshness")
	}
	want := []string{"freshness", "acquire", "renew", "freshness"}
	if got := provider.operations(); len(got) != len(want) {
		t.Fatalf("operations=%v", got)
	} else {
		for index := range want {
			if got[index] != want[index] {
				t.Fatalf("operations=%v", got)
			}
		}
	}
}

func TestClientRuntimeRealHTTP2EnrollmentFreshnessAcquireRenewAndRestart(t *testing.T) {
	fixture := newSourceOperatorRuntimeFixture(t, filepath.Join(t.TempDir(), "idempotency.cbor"), nil)
	device := copyDeviceIdentity(fixture.request.Device)
	device.CredentialGeneration = fixture.requestSigner.KeyRef().Generation
	fixture.request.Device = device
	fixture.request.Key.DeviceGeneration = device.CredentialGeneration
	fixture.requestKey.CredentialGeneration = device.CredentialGeneration
	fixture.signed, _ = SignACPAcquireRequest(context.Background(), fixture.request, fixture.requestSigner, fixture.now.Load())
	fixture.enrollment.decision = EnrollmentDecision{Status: EnrollmentStatusAccepted, DeviceIdentity: &device}
	server := newHTTP2TLSServer(t, fixture.runtime.ServeHTTP)
	server.StartTLS()
	defer server.Close()
	enrollmentRequest := fixture.enrollmentRequest()
	enrollmentPurpose, _ := EnrollmentResultSigningPurpose()
	enrollmentIssuers, err := NewStaticIssuerResolver([]IssuerRecord{{
		KID: fixture.enrollmentSigner.kid, PublicKey: fixture.enrollmentSigner.public, Purpose: enrollmentPurpose,
		Profile: enrollmentRequest.Profile, SourceOperator: enrollmentRequest.SourceOperator, Generation: 1,
		NotBefore: fixture.now.Load() - 1, ExpiresAt: fixture.now.Load() + 600,
	}})
	if err != nil {
		t.Fatal(err)
	}
	enrollment, err := NewEnrollmentHTTPClient(EnrollmentHTTPClientConfig{
		Endpoint: server.URL, TLSConfig: testTLSConfig(t, server), SourceOperator: enrollmentRequest.SourceOperator,
		Profile: enrollmentRequest.Profile, Signer: fixture.requestSigner,
		ResultIssuers: enrollmentIssuers,
		Options:       HTTPProviderOptions{MaxAttempts: 1}, NowUnix: func() uint64 { return fixture.now.Load() },
	})
	if err != nil {
		t.Fatal(err)
	}
	requestIDs := &runtimeRequestIDs{}
	providerFactory := func(identity.DeviceIdentity) (AuthorityProvider, error) {
		purpose, _ := ACPResultSigningPurpose()
		return NewHTTPProvider(HTTPProviderConfig{
			Endpoint: server.URL, TLSConfig: testTLSConfig(t, server), SourceOperator: fixture.request.Key.SourceOperator,
			Profile: fixture.request.Key.Profile, Signer: fixture.requestSigner,
			ResultIssuers: mustACPResultResolver(t, fixture.signed, purpose, fixture.acpSigner.public, fixture.acpSigner.kid),
			RequestIDs:    requestIDs, Options: HTTPProviderOptions{MaxAttempts: 1}, NowUnix: func() uint64 { return fixture.now.Load() },
		})
	}
	store := NewMemoryEnrollmentStateStore()
	gate, _ := NewRestartGate(NewMemoryGenerationFloorStore(1024), runtimeCheckpointVerifier{}, testClock{now: fixture.now.Load()}, noopObserver{})
	client, err := NewClientRuntime(ClientRuntimeConfig{
		SourceOperator: fixture.request.Key.SourceOperator, Profile: fixture.request.Key.Profile,
		EnrollmentStore: store, Enrollment: enrollment, ProviderFactory: providerFactory,
		RestartGate: gate, NowUnix: func() uint64 { return fixture.now.Load() },
	})
	if err != nil {
		t.Fatal(err)
	}
	freshness := FreshnessRequest{SourceOperator: fixture.request.Key.SourceOperator, Profile: fixture.request.Key.Profile,
		DeviceID: device.ID, DeviceGeneration: device.CredentialGeneration, DeadlineUnix: fixture.now.Load() + 30}
	if err := client.StartInitial(context.Background(), enrollmentRequest, freshness); err != nil {
		t.Fatalf("start initial: %#v", err)
	}
	if !client.Ready() {
		t.Fatal("initial enrollment freshness did not establish readiness")
	}
	if _, err := client.Acquire(context.Background(), fixture.request); err != nil {
		t.Fatal(err)
	}
	renew := RenewRequest{AcquireRequest: cloneACPRequest(fixture.request), PreviousGrant: RouteGrantDigest{1}}
	renew.RequestID[0] = 42
	if _, err := client.Renew(context.Background(), renew); err != nil {
		t.Fatal(err)
	}
	if err := client.Refresh(context.Background(), freshness); err != nil {
		t.Fatal(err)
	}
	if err := client.Restart(context.Background(), freshness); err != nil {
		t.Fatal(err)
	}
	if !client.Ready() {
		t.Fatal("restart freshness did not restore readiness")
	}
	operations := fixture.authority.operations()
	want := []ACPOperation{ACPOperationFreshness, ACPOperationAcquire, ACPOperationRenew, ACPOperationFreshness, ACPOperationFreshness}
	if len(operations) != len(want) {
		t.Fatalf("real operations=%v", operations)
	}
	for index := range want {
		if operations[index] != want[index] {
			t.Fatalf("real operations=%v", operations)
		}
	}
}

func TestClientRuntimeInitialEnrollmentPersistsExactlyOnceAndFailsClosed(t *testing.T) {
	request := validEnrollmentRequestPayload()
	payload, err := EncodeEnrollmentRequestPayload(request)
	if err != nil {
		t.Fatal(err)
	}
	result := validEnrollmentResultPayloadBoundToRequest(request, payload, EnrollmentStatusAccepted)
	device := *result.DeviceIdentity
	store := NewMemoryEnrollmentStateStore()
	enrollment := &runtimeEnrollmentClient{result: result}
	provider := &runtimeRecordingProvider{freshness: ProviderFreshness{SourceOperator: "source.operator", Profile: "profile", Evidence: []byte("fresh")}}
	provider.freshness.Profile = request.Profile
	gate, _ := NewRestartGate(NewMemoryGenerationFloorStore(1024), runtimeCheckpointVerifier{}, testClock{now: 1_893_456_010}, noopObserver{})
	runtime, err := NewClientRuntime(ClientRuntimeConfig{
		SourceOperator: "source.operator", Profile: request.Profile, EnrollmentStore: store, Enrollment: enrollment,
		ProviderFactory: func(identity.DeviceIdentity) (AuthorityProvider, error) { return provider, nil },
		RestartGate:     gate, NowUnix: func() uint64 { return 1_893_456_010 },
	})
	if err != nil {
		t.Fatal(err)
	}
	freshness := runtimeFreshnessRequest(device, 1_893_456_010)
	freshness.Profile = request.Profile
	if err := runtime.StartInitial(context.Background(), request, freshness); err != nil {
		t.Fatal(err)
	}
	if !runtime.Ready() || enrollment.calls != 1 {
		t.Fatalf("ready=%v enrollment calls=%d", runtime.Ready(), enrollment.calls)
	}
	if err := runtime.StartInitial(context.Background(), request, freshness); !errors.Is(err, ErrTerminalEnrollment) {
		t.Fatalf("reenrollment error=%v", err)
	}
	if enrollment.calls != 1 {
		t.Fatalf("reenrollment performed %d outbound calls, want exactly 1", enrollment.calls)
	}
	if runtime.Ready() {
		t.Fatal("failed reenrollment left runtime ready")
	}
}

func TestClientRuntimeConcurrentInitialEnrollmentHasOneOutboundWinner(t *testing.T) {
	request := validEnrollmentRequestPayload()
	payload, err := EncodeEnrollmentRequestPayload(request)
	if err != nil {
		t.Fatal(err)
	}
	result := validEnrollmentResultPayloadBoundToRequest(request, payload, EnrollmentStatusAccepted)
	device := *result.DeviceIdentity
	store := NewMemoryEnrollmentStateStore()
	entered := make(chan struct{})
	release := make(chan struct{})
	firstEnrollment := &runtimeBlockingEnrollmentClient{result: result, entered: entered, release: release}
	secondEnrollment := &runtimeEnrollmentClient{result: result}
	newRuntime := func(enrollment EnrollmentClient) *ClientRuntime {
		gate, gateErr := NewRestartGate(NewMemoryGenerationFloorStore(1024), runtimeCheckpointVerifier{}, testClock{now: 1_893_456_010}, noopObserver{})
		if gateErr != nil {
			t.Fatal(gateErr)
		}
		client, runtimeErr := NewClientRuntime(ClientRuntimeConfig{
			SourceOperator: "source.operator", Profile: request.Profile, EnrollmentStore: store, Enrollment: enrollment,
			ProviderFactory: func(identity.DeviceIdentity) (AuthorityProvider, error) {
				return &runtimeRecordingProvider{freshness: ProviderFreshness{SourceOperator: "source.operator", Profile: request.Profile, Evidence: []byte("fresh")}}, nil
			},
			RestartGate: gate, NowUnix: func() uint64 { return 1_893_456_010 },
		})
		if runtimeErr != nil {
			t.Fatal(runtimeErr)
		}
		return client
	}
	freshness := runtimeFreshnessRequest(device, 1_893_456_010)
	freshness.Profile = request.Profile
	first := newRuntime(firstEnrollment)
	second := newRuntime(secondEnrollment)
	firstResult := make(chan error, 1)
	secondResult := make(chan error, 1)
	go func() { firstResult <- first.StartInitial(context.Background(), request, freshness) }()
	<-entered
	go func() { secondResult <- second.StartInitial(context.Background(), request, freshness) }()
	if secondEnrollment.calls != 0 {
		t.Fatalf("competing runtime made %d outbound calls while initialization was reserved", secondEnrollment.calls)
	}
	close(release)
	if err := <-firstResult; err != nil {
		t.Fatalf("first enrollment: %v", err)
	}
	if err := <-secondResult; !errors.Is(err, ErrTerminalEnrollment) {
		t.Fatalf("competing enrollment error=%v", err)
	}
	if firstEnrollment.calls.Load() != 1 || secondEnrollment.calls != 0 {
		t.Fatalf("outbound calls first=%d second=%d", firstEnrollment.calls.Load(), secondEnrollment.calls)
	}
}

type runtimeEnrollmentClient struct {
	result EnrollmentResultPayload
	err    error
	calls  int
}

type runtimeBlockingEnrollmentClient struct {
	result  EnrollmentResultPayload
	entered chan struct{}
	release chan struct{}
	calls   atomic.Uint32
}

func (client *runtimeBlockingEnrollmentClient) Enroll(context.Context, EnrollmentRequestPayload) (EnrollmentResultPayload, error) {
	client.calls.Add(1)
	close(client.entered)
	<-client.release
	return client.result, nil
}
func (*runtimeBlockingEnrollmentClient) Close() error { return nil }

func (client *runtimeEnrollmentClient) Enroll(context.Context, EnrollmentRequestPayload) (EnrollmentResultPayload, error) {
	client.calls++
	return client.result, client.err
}
func (*runtimeEnrollmentClient) Close() error { return nil }

type runtimeRecordingProvider struct {
	mu            sync.Mutex
	freshness     ProviderFreshness
	operationsLog []string
}

func (provider *runtimeRecordingProvider) record(operation string) {
	provider.mu.Lock()
	provider.operationsLog = append(provider.operationsLog, operation)
	provider.mu.Unlock()
}
func (provider *runtimeRecordingProvider) Acquire(context.Context, AcquireRequest) (ProviderGrant, error) {
	provider.record("acquire")
	return ProviderGrant{}, nil
}
func (provider *runtimeRecordingProvider) Renew(context.Context, RenewRequest) (ProviderGrant, error) {
	provider.record("renew")
	return ProviderGrant{}, nil
}
func (provider *runtimeRecordingProvider) Freshness(context.Context, FreshnessRequest) (ProviderFreshness, error) {
	provider.record("freshness")
	return provider.freshness, nil
}
func (*runtimeRecordingProvider) Close() error { return nil }
func (provider *runtimeRecordingProvider) operations() []string {
	provider.mu.Lock()
	defer provider.mu.Unlock()
	return append([]string(nil), provider.operationsLog...)
}

type runtimeCheckpointVerifier struct{}

func (runtimeCheckpointVerifier) VerifyFreshnessEvidence(_ context.Context, _ ProviderFreshness, request FreshnessRequest, _ uint64) (CheckpointClaims, error) {
	issued := request.DeadlineUnix - 30
	return CheckpointClaims{SourceOperator: request.SourceOperator, Profile: request.Profile, Generation: request.AfterGeneration + 1, IssuedAt: issued, FreshUntil: issued + 100, Digest: CheckpointDigest{9}}, nil
}

type runtimeRequestIDs struct{ next atomic.Uint32 }

func (source *runtimeRequestIDs) NewRequestID() (RequestID, error) {
	value := source.next.Add(1)
	return RequestID{byte(value), byte(value >> 8), 1}, nil
}

func runtimeTestIdentity() identity.DeviceIdentity {
	return identity.DeviceIdentity{ID: [32]byte{1}, SourceOperatorID: "source.operator", CredentialGeneration: 1,
		CredentialNotBefore: 90, CredentialExpiresAt: 200,
		SigningKey: identity.KeyRef{ID: [32]byte{2}, Purpose: identity.PurposeDeviceACPRequest, Generation: 1, Thumbprint: [32]byte{3}}}
}

func runtimeFreshnessRequest(device identity.DeviceIdentity, now uint64) FreshnessRequest {
	return FreshnessRequest{SourceOperator: device.SourceOperatorID, Profile: "profile", DeviceID: device.ID,
		DeviceGeneration: device.CredentialGeneration, AfterGeneration: 0, DeadlineUnix: now + 30}
}
