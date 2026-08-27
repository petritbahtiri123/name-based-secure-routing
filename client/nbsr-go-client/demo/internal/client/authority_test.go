package client

import (
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"crypto/tls"
	"errors"
	"runtime"
	"testing"
	"time"

	"nbsr.local/client/nbsr-go-client/demo/internal/fixture"
	"nbsr.local/client/nbsr-go-client/internal/authority"
	"nbsr.local/client/nbsr-go-client/internal/corestate"
	"nbsr.local/client/nbsr-go-client/internal/session"
)

func TestAcquireRouteUsesProductionHTTP2AndReturnsUsableReservation(t *testing.T) {
	server, client := testAuthorityClient(t)
	reservation, err := client.AcquireRoute(context.Background(), server.AcquireRequest())
	if err != nil {
		t.Fatal(err)
	}
	if reservation.TSGeneration() != server.AcquireRequest().Key.TSGeneration {
		t.Fatal("reservation lost TS binding")
	}
	if got := server.LastTLS(); got.Version != tls.VersionTLS13 || got.NegotiatedProtocol != "h2" {
		t.Fatalf("transport = TLS %x / %q", got.Version, got.NegotiatedProtocol)
	}
	snapshot, err := client.Manager().CaptureGeneration()
	if err != nil {
		t.Fatal(err)
	}
	if err := client.Manager().ValidateForNewWork(reservation, snapshot, server.NowUnix()); err != nil {
		t.Fatalf("reservation unusable: %v", err)
	}
}

func TestRuntimeRouteBindingUsesActualProofThroughHTTPManagerAndVerifier(t *testing.T) {
	defaults, err := fixture.Start(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	request := defaults.AcquireRequest()
	defaults.Close()
	seed := make([]byte, ed25519.SeedSize)
	for index := range seed {
		seed[index] = 0x44
	}
	public := ed25519.NewKeyFromSeed(seed).Public().(ed25519.PublicKey)
	thumbprint := sha256.Sum256(public)
	request.Key.TSGeneration, request.Key.ProofThumbprint = 5, thumbprint
	view := session.DestinationRouteView{ServiceIdentity: request.Intent.ServiceIdentity, ServiceDigest: corestate.ServiceDigest(request.Key.ServiceDigest), Intent: request.Intent, ProofThumbprint: thumbprint}
	copy(view.ProofPublicKey[:], public)
	server, err := fixture.Start(t.TempDir(), fixture.WithRouteInputs(request, view))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(server.Close)
	client, err := NewAuthorityClient(server)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = client.Close() })
	reservation, err := client.AcquireRoute(context.Background(), server.AcquireRequest())
	if err != nil {
		t.Fatal(err)
	}
	if reservation.TSGeneration() != 5 {
		t.Fatalf("reservation generation = %d", reservation.TSGeneration())
	}
	tampered := server.AcquireRequest()
	tampered.RequestID = authority.RequestID{9}
	tampered.Key.ProofThumbprint[0] ^= 1
	if _, err := client.AcquireRoute(context.Background(), tampered); !errors.Is(err, authority.ErrPolicyDenied) {
		t.Fatalf("tampered proof error = %v", err)
	}
}

func TestAuthorityClientCanUseProcessBootstrapWithoutFixtureServerReference(t *testing.T) {
	server, err := fixture.Start(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	defer server.Close()
	client, err := NewAuthorityClientFromConfig(AuthorityClientConfig{Endpoint: server.Endpoint(), TLSConfig: server.ClientTLSConfig(), SourceOperator: server.AcquireRequest().Key.SourceOperator, Profile: server.AcquireRequest().Key.Profile, DeviceID: server.AcquireRequest().Key.DeviceID, DeviceGeneration: server.AcquireRequest().Key.DeviceGeneration, DeviceSigner: server.DeviceSigner(), Issuers: server.Issuers(), Checkpoint: server.CheckpointClaims(), NowUnix: server.NowUnix()})
	if err != nil {
		t.Fatal(err)
	}
	defer client.Close()
	if _, err := client.AcquireRoute(context.Background(), server.AcquireRequest()); err != nil {
		t.Fatal(err)
	}
}

func TestAcquireRouteFailsClosedForAuthorityMutations(t *testing.T) {
	for _, tc := range []struct {
		name string
		mode fixture.Mutation
		want error
	}{
		{"service digest", fixture.MutateServiceDigest, authority.ErrBindingMismatch},
		{"service identity", fixture.MutateServiceIdentity, authority.ErrBindingMismatch},
		{"wrong signer", fixture.MutateSigner, authority.ErrSignatureFailure},
		{"wrong kid", fixture.MutateKID, authority.ErrUnknownIdentity},
		{"wrong purpose", fixture.MutateKIDPurpose, authority.ErrInvalidKeyPurpose},
		{"expired", fixture.MutateExpired, authority.ErrExpired},
		{"not yet valid", fixture.MutateNotYetValid, authority.ErrExpired},
		{"stale generation", fixture.MutateStaleGeneration, authority.ErrStaleGeneration},
		{"malformed response", fixture.MutateMalformedResponse, authority.ErrInvalidAuthority},
	} {
		t.Run(tc.name, func(t *testing.T) {
			server, client := testAuthorityClient(t, fixture.WithMutation(tc.mode))
			if _, err := client.AcquireRoute(context.Background(), server.AcquireRequest()); !errors.Is(err, tc.want) {
				t.Fatalf("error = %v, want %v", err, tc.want)
			}
			if usage := client.Manager().Usage(); usage.CacheEntries != 0 || usage.PendingCalls != 0 {
				t.Fatalf("invalid authority retained: %+v", usage)
			}
		})
	}
}

func TestAcquireRouteUnknownServiceIsPolicyDenied(t *testing.T) {
	server, client := testAuthorityClient(t)
	request := server.AcquireRequest()
	request.Intent.ServiceIdentity = "unknown.demo.service"
	if _, err := client.AcquireRoute(context.Background(), request); !errors.Is(err, authority.ErrPolicyDenied) {
		t.Fatalf("unknown service = %v", err)
	}
	if usage := client.Manager().Usage(); usage.CacheEntries != 0 || usage.PendingCalls != 0 {
		t.Fatalf("denied authority retained: %+v", usage)
	}
}

func TestAcquireRouteTLSIdentityTimeoutAndCancellationFailClosed(t *testing.T) {
	server, err := fixture.Start(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(server.Close)
	badTrust := server.ClientTLSConfig()
	badTrust.ServerName = "wrong.demo.invalid"
	if _, err := NewAuthorityClient(server, WithTLSConfig(badTrust)); err == nil {
		t.Fatal("wrong TLS identity accepted during freshness bootstrap")
	}

	delayed, client := testAuthorityClient(t, fixture.WithDecisionBlock())
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Millisecond)
	defer cancel()
	if _, err := client.AcquireRoute(ctx, delayed.AcquireRequest()); !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("timeout = %v", err)
	}
	assertAcquisitionIdle(t, client.Manager())
}

func assertAcquisitionIdle(t *testing.T, manager *authority.Manager) {
	t.Helper()
	deadline := time.Now().Add(time.Second)
	for {
		usage := manager.Usage()
		if usage.PendingCalls == 0 && usage.PendingWaiters == 0 {
			return
		}
		if time.Now().After(deadline) {
			t.Fatalf("acquisition did not return idle: %+v", usage)
		}
		runtime.Gosched()
	}
}

func TestDuplicateAcquireIsSingleConsumableAuthority(t *testing.T) {
	server, client := testAuthorityClient(t)
	request := server.AcquireRequest()
	first, err := client.AcquireRoute(context.Background(), request)
	if err != nil {
		t.Fatal(err)
	}
	second, err := client.AcquireRoute(context.Background(), request)
	if err != nil || second != first {
		t.Fatalf("idempotent duplicate = %#v, %v", second, err)
	}
	snapshot, err := client.Manager().CaptureGeneration()
	if err != nil {
		t.Fatal(err)
	}
	owner := authority.AdmissionOwner{TSGeneration: request.Key.TSGeneration, ChannelID: [16]byte{1}}
	if _, err := client.Manager().Consume(first, owner, snapshot, server.NowUnix()); err != nil {
		t.Fatal(err)
	}
	if _, err := client.Manager().Consume(second, owner, snapshot, server.NowUnix()); !errors.Is(err, authority.ErrInvalidTransition) {
		t.Fatalf("second consumption = %v", err)
	}
	if usage := client.Manager().Usage(); usage.PendingCalls != 0 || usage.PendingWaiters != 0 {
		t.Fatalf("release leaked acquisition: %+v", usage)
	}
}

func TestAuthorityAcquisitionChurnReturnsToBaseline(t *testing.T) {
	server, client := testAuthorityClient(t)
	baselineGoroutines := runtime.NumGoroutine()
	for iteration := 0; iteration < 20; iteration++ {
		request := server.AcquireRequest()
		request.RequestID[1] = byte(iteration + 1)
		reservation, err := client.AcquireRoute(context.Background(), request)
		if err != nil {
			t.Fatal(err)
		}
		if err := client.Manager().Release(reservation); err != nil {
			t.Fatal(err)
		}
		request.Intent.ServiceIdentity = "unknown.demo.service"
		request.RequestID[2] = byte(iteration + 1)
		if _, err := client.AcquireRoute(context.Background(), request); !errors.Is(err, authority.ErrBindingMismatch) {
			t.Fatalf("denial %d = %v", iteration, err)
		}
	}
	usage := client.Manager().Usage()
	if usage.CacheEntries != 1 || usage.PendingCalls != 0 || usage.PendingWaiters != 0 {
		t.Fatalf("churn usage = %+v", usage)
	}
	if got := runtime.NumGoroutine(); got > baselineGoroutines+4 {
		t.Fatalf("goroutines grew from %d to %d", baselineGoroutines, got)
	}
}

func testAuthorityClient(t *testing.T, options ...fixture.Option) (*fixture.Server, *AuthorityClient) {
	t.Helper()
	server, err := fixture.Start(t.TempDir(), options...)
	if err != nil {
		t.Fatal(err)
	}
	client, err := NewAuthorityClient(server)
	if err != nil {
		server.Close()
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = client.Close(); server.Close() })
	return server, client
}
