package authority

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/tls"
	"crypto/x509"
	"errors"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"nbsr.local/client/nbsr-go-client/internal/identity"
)

func TestHTTPProviderUsesTLS13HTTP2ExactPathAndReusesConnection(t *testing.T) {
	fixture := newHTTPACPFixture(t)
	var newConnections atomic.Int32
	var calls atomic.Int32
	server := newHTTP2TLSServer(t, func(writer http.ResponseWriter, request *http.Request) {
		if request.Method != http.MethodPost || request.URL.Path != "/acp/authority" || request.URL.RawQuery != "" {
			t.Errorf("unexpected request target: %s %s", request.Method, request.URL.String())
		}
		if request.ProtoMajor != 2 || request.TLS == nil || request.TLS.Version != tls.VersionTLS13 || request.TLS.NegotiatedProtocol != "h2" {
			t.Errorf("transport = %s TLS=%#v", request.Proto, request.TLS)
		}
		body, err := io.ReadAll(request.Body)
		if err != nil {
			t.Error(err)
			return
		}
		if !bytes.Equal(body, fixture.signed.Body()) {
			t.Error("authority request bytes changed in transport")
		}
		calls.Add(1)
		writer.Header().Set("Content-Type", "application/cose")
		_, _ = writer.Write(fixture.successWire)
	})
	server.Config.ConnState = func(_ net.Conn, state http.ConnState) {
		if state == http.StateNew {
			newConnections.Add(1)
		}
	}
	server.StartTLS()
	t.Cleanup(server.Close)

	provider := newTestHTTPProvider(t, server, fixture, HTTPProviderOptions{})
	t.Cleanup(func() { _ = provider.Close() })
	for range 2 {
		grant, err := provider.Acquire(context.Background(), fixture.request)
		if err != nil {
			t.Fatal(err)
		}
		if !bytes.Equal(grant.ExactRouteGrant, fixture.artifact) || grant.Profile != fixture.request.Key.Profile || grant.AuthorityGeneration != fixture.request.Key.AuthorityGeneration {
			t.Fatalf("unexpected untrusted grant candidate: %#v", grant)
		}
	}
	if calls.Load() != 2 || newConnections.Load() != 1 {
		t.Fatalf("calls=%d new connections=%d, want 2 and 1", calls.Load(), newConnections.Load())
	}
}

func TestHTTPProviderRetriesExactSignedBytesOnlyForTransportAmbiguity(t *testing.T) {
	fixture := newHTTPACPFixture(t)
	var mu sync.Mutex
	var bodies [][]byte
	server := newHTTP2TLSServer(t, func(writer http.ResponseWriter, request *http.Request) {
		body, _ := io.ReadAll(request.Body)
		mu.Lock()
		bodies = append(bodies, append([]byte(nil), body...))
		attempt := len(bodies)
		mu.Unlock()
		if attempt == 1 {
			panic(http.ErrAbortHandler)
		}
		_, _ = writer.Write(fixture.successWire)
	})
	server.StartTLS()
	t.Cleanup(server.Close)

	provider := newTestHTTPProvider(t, server, fixture, HTTPProviderOptions{MaxAttempts: 2, RetryBackoff: time.Millisecond})
	t.Cleanup(func() { _ = provider.Close() })
	if _, err := provider.Acquire(context.Background(), fixture.request); err != nil {
		t.Fatal(err)
	}
	mu.Lock()
	defer mu.Unlock()
	if len(bodies) != 2 || !bytes.Equal(bodies[0], bodies[1]) || !bytes.Equal(bodies[0], fixture.signed.Body()) {
		t.Fatalf("retry did not preserve exact signed bytes: attempts=%d", len(bodies))
	}
}

func TestHTTPProviderDoesNotRetryAfterSignedDeadline(t *testing.T) {
	fixture := newHTTPACPFixture(t)
	var calls atomic.Int32
	var now atomic.Uint64
	now.Store(acpTestNow)
	server := newHTTP2TLSServer(t, func(http.ResponseWriter, *http.Request) {
		calls.Add(1)
		now.Store(fixture.request.DeadlineUnix)
		panic(http.ErrAbortHandler)
	})
	server.StartTLS()
	defer server.Close()
	config := testHTTPProviderConfig(t, server, fixture, HTTPProviderOptions{MaxAttempts: 3})
	config.NowUnix = now.Load
	provider, err := NewHTTPProvider(config)
	if err != nil {
		t.Fatal(err)
	}
	defer provider.Close()
	if _, err := provider.Acquire(context.Background(), fixture.request); !errors.Is(err, ErrRequestAmbiguous) {
		t.Fatalf("deadline ambiguity error=%v", err)
	}
	if calls.Load() != 1 {
		t.Fatalf("request replayed %d times after signed deadline", calls.Load())
	}
}

func TestHTTPProviderSemaphoreAdmissionExpiresBeforeAnyNetworkSend(t *testing.T) {
	fixture := newHTTPACPFixture(t)
	now := uint64(time.Now().Unix())
	request := cloneACPRequest(fixture.request)
	request.DeadlineUnix = now + 1
	request.Device.CredentialNotBefore = now - 10
	request.Device.CredentialExpiresAt = now + 100
	request.Intent.ExpiresAt = now + 100
	var calls atomic.Int32
	server := newHTTP2TLSServer(t, func(http.ResponseWriter, *http.Request) { calls.Add(1) })
	server.StartTLS()
	defer server.Close()
	config := testHTTPProviderConfig(t, server, fixture, HTTPProviderOptions{MaxAttempts: 1, MaxConcurrent: 1})
	config.NowUnix = func() uint64 { return uint64(time.Now().Unix()) }
	provider, err := NewHTTPProvider(config)
	if err != nil {
		t.Fatal(err)
	}
	defer provider.Close()
	provider.http.semaphore <- struct{}{}
	result := make(chan error, 1)
	started := time.Now()
	go func() {
		_, err := provider.Acquire(context.Background(), request)
		result <- err
	}()
	select {
	case err := <-result:
		if !errors.Is(err, ErrExpired) {
			t.Fatalf("queued deadline error=%v, want ErrExpired", err)
		}
		if elapsed := time.Since(started); elapsed > 1500*time.Millisecond {
			t.Fatalf("queued request exceeded signed deadline: %v", elapsed)
		}
	case <-time.After(1500 * time.Millisecond):
		<-provider.http.semaphore
		select {
		case <-result:
		case <-time.After(time.Second):
		}
		t.Fatal("queued request remained live beyond signed deadline")
	}
	<-provider.http.semaphore
	if calls.Load() != 0 {
		t.Fatalf("expired queued request reached server %d times", calls.Load())
	}
}

func TestHTTPProviderMaxAttemptsIncludesHTTP2RetryableStreamReplay(t *testing.T) {
	fixture := newHTTPACPFixture(t)
	server := newHTTP2TLSServer(t, func(http.ResponseWriter, *http.Request) {})
	server.StartTLS()
	defer server.Close()
	provider := newTestHTTPProvider(t, server, fixture, HTTPProviderOptions{MaxAttempts: 1})
	defer provider.Close()
	probe := &retryableHTTP2ReplayProbeTransport{response: fixture.successWire}
	provider.http.client.Transport = probe
	if _, err := provider.Acquire(context.Background(), fixture.request); err != nil {
		t.Fatal(err)
	}
	if probe.bodyAttempts.Load() != 1 {
		t.Fatalf("MaxAttempts=1 allowed %d body-bearing HTTP/2 attempts", probe.bodyAttempts.Load())
	}
}

func TestHTTPProviderCallerTimeoutAfterSendIsAmbiguous(t *testing.T) {
	fixture := newHTTPACPFixture(t)
	server := newHTTP2TLSServer(t, func(_ http.ResponseWriter, request *http.Request) { <-request.Context().Done() })
	server.StartTLS()
	defer server.Close()
	provider := newTestHTTPProvider(t, server, fixture, HTTPProviderOptions{MaxAttempts: 1, AttemptTimeout: time.Second})
	defer provider.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Millisecond)
	defer cancel()
	if _, err := provider.Acquire(ctx, fixture.request); !errors.Is(err, ErrRequestAmbiguous) {
		t.Fatalf("post-send caller timeout error=%v", err)
	}
}

func TestHTTPProviderRefusesRedirectHTTP1AndWrongIdentityWithoutRetry(t *testing.T) {
	fixture := newHTTPACPFixture(t)
	t.Run("redirect", func(t *testing.T) {
		var calls atomic.Int32
		server := newHTTP2TLSServer(t, func(writer http.ResponseWriter, request *http.Request) {
			calls.Add(1)
			http.Redirect(writer, request, "/acp/authority", http.StatusTemporaryRedirect)
		})
		server.StartTLS()
		defer server.Close()
		provider := newTestHTTPProvider(t, server, fixture, HTTPProviderOptions{MaxAttempts: 3})
		defer provider.Close()
		if _, err := provider.Acquire(context.Background(), fixture.request); !errors.Is(err, ErrProviderUnavailable) {
			t.Fatalf("redirect error = %v", err)
		}
		if calls.Load() != 1 {
			t.Fatalf("redirect retried %d times", calls.Load())
		}
	})

	t.Run("http1", func(t *testing.T) {
		server := httptest.NewUnstartedServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
			t.Fatal("HTTP/1.1 request reached handler")
		}))
		server.EnableHTTP2 = false
		server.StartTLS()
		defer server.Close()
		provider := newTestHTTPProvider(t, server, fixture, HTTPProviderOptions{MaxAttempts: 1})
		defer provider.Close()
		if _, err := provider.Acquire(context.Background(), fixture.request); !errors.Is(err, ErrProviderUnavailable) {
			t.Fatalf("HTTP/1.1 fallback error = %v", err)
		}
	})

	t.Run("wrong identity", func(t *testing.T) {
		var calls atomic.Int32
		server := newHTTP2TLSServer(t, func(http.ResponseWriter, *http.Request) { calls.Add(1) })
		server.StartTLS()
		defer server.Close()
		options := HTTPProviderOptions{MaxAttempts: 3}
		config := testHTTPProviderConfig(t, server, fixture, options)
		config.TLSConfig.ServerName = "wrong.invalid"
		provider, err := NewHTTPProvider(config)
		if err != nil {
			t.Fatal(err)
		}
		defer provider.Close()
		if _, err := provider.Acquire(context.Background(), fixture.request); !errors.Is(err, ErrProviderUnavailable) {
			t.Fatalf("wrong identity error = %v", err)
		}
		if calls.Load() != 0 {
			t.Fatalf("wrong identity reached handler %d times", calls.Load())
		}
	})
}

func TestHTTPProviderEnforcesDeadlineResponseBoundAndSemanticStatus(t *testing.T) {
	fixture := newHTTPACPFixture(t)
	t.Run("timeout", func(t *testing.T) {
		server := newHTTP2TLSServer(t, func(writer http.ResponseWriter, request *http.Request) {
			<-request.Context().Done()
		})
		server.StartTLS()
		defer server.Close()
		provider := newTestHTTPProvider(t, server, fixture, HTTPProviderOptions{MaxAttempts: 1, AttemptTimeout: 20 * time.Millisecond})
		defer provider.Close()
		if _, err := provider.Acquire(context.Background(), fixture.request); !errors.Is(err, ErrRequestAmbiguous) {
			t.Fatalf("timeout error = %v", err)
		}
	})

	t.Run("oversized response", func(t *testing.T) {
		server := newHTTP2TLSServer(t, func(writer http.ResponseWriter, _ *http.Request) {
			writer.Header().Set("Content-Length", "131073")
			_, _ = writer.Write(bytes.Repeat([]byte{0}, maxACPAcquireResultBodySize+1))
		})
		server.StartTLS()
		defer server.Close()
		provider := newTestHTTPProvider(t, server, fixture, HTTPProviderOptions{MaxAttempts: 1})
		defer provider.Close()
		if _, err := provider.Acquire(context.Background(), fixture.request); !errors.Is(err, ErrInvalidAuthority) {
			t.Fatalf("oversized response error = %v", err)
		}
	})

	t.Run("signed deny", func(t *testing.T) {
		var calls atomic.Int32
		deny := validACPResult(fixture.signed, ACPResultStatusPolicyDenied)
		wire := mustSignACPResult(t, deny, fixture.resultPrivate, fixture.resultKID)
		server := newHTTP2TLSServer(t, func(writer http.ResponseWriter, _ *http.Request) {
			calls.Add(1)
			_, _ = writer.Write(wire)
		})
		server.StartTLS()
		defer server.Close()
		provider := newTestHTTPProvider(t, server, fixture, HTTPProviderOptions{MaxAttempts: 3})
		defer provider.Close()
		if _, err := provider.Acquire(context.Background(), fixture.request); !errors.Is(err, ErrPolicyDenied) {
			t.Fatalf("signed deny error = %v", err)
		}
		if calls.Load() != 1 {
			t.Fatalf("signed semantic result retried %d times", calls.Load())
		}
	})
}

func TestHTTPProviderRenewAndFreshnessReturnUntrustedArtifacts(t *testing.T) {
	fixture := newHTTPACPFixture(t)
	renewRequest := RenewRequest{AcquireRequest: fixture.request, PreviousGrant: RouteGrantDigest(bytes32ForSeed(0x91))}
	renewSigned, err := SignACPRenewRequest(context.Background(), renewRequest, fixture.signer, acpTestNow)
	if err != nil {
		t.Fatal(err)
	}
	freshnessRequest := FreshnessRequest{
		SourceOperator: fixture.request.Key.SourceOperator, Profile: fixture.request.Key.Profile,
		DeviceID: fixture.request.Device.ID, DeviceGeneration: fixture.request.Device.CredentialGeneration,
		AfterGeneration: fixture.request.Key.AuthorityGeneration, AfterCheckpoint: CheckpointDigest(bytes32ForSeed(0x92)),
		DeadlineUnix: fixture.request.DeadlineUnix,
	}
	freshnessID := RequestID{9, 8, 7, 6, 5, 4, 3, 2, 1, 2, 3, 4, 5, 6, 7, 8}
	freshnessSigned, err := SignACPFreshnessRequest(context.Background(), freshnessRequest, freshnessID, fixture.signer, acpTestNow)
	if err != nil {
		t.Fatal(err)
	}
	renewArtifact := []byte("renewed-route-grant-candidate")
	freshnessArtifact := []byte("freshness-evidence-candidate")
	renewResult := validACPResult(renewSigned, ACPResultStatusSuccess)
	renewResult.Artifact = renewArtifact
	freshnessResult := validACPResult(freshnessSigned, ACPResultStatusSuccess)
	freshnessResult.AuthorityGeneration++
	freshnessResult.Artifact = freshnessArtifact
	renewWire := mustSignACPResult(t, renewResult, fixture.resultPrivate, fixture.resultKID)
	freshnessWire := mustSignACPResult(t, freshnessResult, fixture.resultPrivate, fixture.resultKID)
	server := newHTTP2TLSServer(t, func(writer http.ResponseWriter, request *http.Request) {
		body, _ := io.ReadAll(request.Body)
		switch {
		case bytes.Equal(body, renewSigned.Body()):
			_, _ = writer.Write(renewWire)
		case bytes.Equal(body, freshnessSigned.Body()):
			_, _ = writer.Write(freshnessWire)
		default:
			http.Error(writer, "unexpected request", http.StatusBadRequest)
		}
	})
	server.StartTLS()
	defer server.Close()
	provider := newTestHTTPProvider(t, server, fixture, HTTPProviderOptions{MaxAttempts: 1})
	defer provider.Close()
	grant, err := provider.Renew(context.Background(), renewRequest)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(grant.ExactRouteGrant, renewArtifact) {
		t.Fatal("renew artifact changed")
	}
	freshness, err := provider.Freshness(context.Background(), freshnessRequest)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(freshness.Evidence, freshnessArtifact) || freshness.SourceOperator != fixture.request.Key.SourceOperator || freshness.Profile != fixture.request.Key.Profile {
		t.Fatalf("unexpected freshness candidate: %#v", freshness)
	}
}

func TestHTTPProviderRejectsMalformedAndMisbindingResults(t *testing.T) {
	fixture := newHTTPACPFixture(t)
	tests := []struct {
		name string
		wire []byte
		want error
	}{
		{name: "malformed COSE", wire: []byte{0xd2, 0xff}, want: ErrInvalidAuthority},
		{name: "wrong request ID", wire: func() []byte {
			result := validACPResult(fixture.signed, ACPResultStatusSuccess)
			result.RequestID[0] ^= 0xff
			return mustSignACPResult(t, result, fixture.resultPrivate, fixture.resultKID)
		}(), want: ErrBindingMismatch},
		{name: "wrong request digest", wire: func() []byte {
			result := validACPResult(fixture.signed, ACPResultStatusSuccess)
			result.RequestDigest[0] ^= 0xff
			return mustSignACPResult(t, result, fixture.resultPrivate, fixture.resultKID)
		}(), want: ErrBindingMismatch},
		{name: "wrong operator", wire: func() []byte {
			result := validACPResult(fixture.signed, ACPResultStatusSuccess)
			result.SourceOperator = "other.operator"
			return mustSignACPResult(t, result, fixture.resultPrivate, fixture.resultKID)
		}(), want: ErrBindingMismatch},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			server := newHTTP2TLSServer(t, func(writer http.ResponseWriter, _ *http.Request) { _, _ = writer.Write(test.wire) })
			server.StartTLS()
			defer server.Close()
			provider := newTestHTTPProvider(t, server, fixture, HTTPProviderOptions{MaxAttempts: 1})
			defer provider.Close()
			if _, err := provider.Acquire(context.Background(), fixture.request); !errors.Is(err, test.want) {
				t.Fatalf("error=%v, want %v", err, test.want)
			}
		})
	}

	t.Run("wrong kid", func(t *testing.T) {
		result := validACPResult(fixture.signed, ACPResultStatusSuccess)
		wire := mustSignACPResult(t, result, fixture.resultPrivate, []byte("unknown-kid"))
		server := newHTTP2TLSServer(t, func(writer http.ResponseWriter, _ *http.Request) { _, _ = writer.Write(wire) })
		server.StartTLS()
		defer server.Close()
		provider := newTestHTTPProvider(t, server, fixture, HTTPProviderOptions{MaxAttempts: 1})
		defer provider.Close()
		if _, err := provider.Acquire(context.Background(), fixture.request); !errors.Is(err, ErrUnknownIdentity) {
			t.Fatalf("wrong kid error=%v", err)
		}
	})
}

func TestHTTPProviderPreservesEveryVerifiedSemanticStatusWithoutRetry(t *testing.T) {
	if (&VerifiedACPSemanticError{}).Verified() {
		t.Fatal("zero-value semantic error claimed verified provenance")
	}
	fixture := newHTTPACPFixture(t)
	tests := []struct {
		status        ACPResultStatus
		compatibility error
	}{
		{ACPResultStatusInvalidRequest, ErrInvalidAuthority},
		{ACPResultStatusUnsupportedVersion, ErrInvalidAuthority},
		{ACPResultStatusUnsupportedProfile, ErrInvalidAuthority},
		{ACPResultStatusRequestIDConflict, ErrRequestConflict},
		{ACPResultStatusRequestExpired, ErrExpired},
		{ACPResultStatusResourceExhausted, ErrPendingCapacity},
		{ACPResultStatusStaleGeneration, ErrStaleGeneration},
		{ACPResultStatusStaleFreshness, ErrStaleFreshness},
		{ACPResultStatusPolicyDenied, ErrPolicyDenied},
		{ACPResultStatusRevoked, ErrRevoked},
		{ACPResultStatusBindingError, ErrBindingMismatch},
		{ACPResultStatusSignatureError, ErrSignatureFailure},
		{ACPResultStatusInternalError, ErrProviderUnavailable},
	}
	for _, test := range tests {
		t.Run(string(test.status), func(t *testing.T) {
			var calls atomic.Int32
			wire := mustSignACPResult(t, validACPResult(fixture.signed, test.status), fixture.resultPrivate, fixture.resultKID)
			server := newHTTP2TLSServer(t, func(writer http.ResponseWriter, _ *http.Request) {
				calls.Add(1)
				_, _ = writer.Write(wire)
			})
			server.StartTLS()
			defer server.Close()
			provider := newTestHTTPProvider(t, server, fixture, HTTPProviderOptions{MaxAttempts: 3})
			defer provider.Close()
			_, err := provider.Acquire(context.Background(), fixture.request)
			var semantic *VerifiedACPSemanticError
			if !errors.As(err, &semantic) {
				t.Fatalf("error=%T %v, want verified ACP semantic provenance", err, err)
			}
			if semantic.Status() != test.status || !semantic.Verified() {
				t.Fatalf("semantic status=%q verified=%v, want %q true", semantic.Status(), semantic.Verified(), test.status)
			}
			if err == test.compatibility || !errors.Is(err, test.compatibility) {
				t.Fatalf("semantic error lost distinct provenance or compatibility: %T %v", err, err)
			}
			if calls.Load() != 1 {
				t.Fatalf("signed status retried %d times", calls.Load())
			}
		})
	}

	t.Run("unsigned transport error is not semantic", func(t *testing.T) {
		server := newHTTP2TLSServer(t, func(http.ResponseWriter, *http.Request) { panic(http.ErrAbortHandler) })
		server.StartTLS()
		defer server.Close()
		provider := newTestHTTPProvider(t, server, fixture, HTTPProviderOptions{MaxAttempts: 1})
		defer provider.Close()
		_, err := provider.Acquire(context.Background(), fixture.request)
		var semantic *VerifiedACPSemanticError
		if errors.As(err, &semantic) {
			t.Fatalf("unsigned transport error gained semantic provenance: %#v", semantic)
		}
	})
}

func TestHTTPProviderBoundsConcurrentCalls(t *testing.T) {
	fixture := newHTTPACPFixture(t)
	entered := make(chan struct{}, 2)
	release := make(chan struct{})
	server := newHTTP2TLSServer(t, func(writer http.ResponseWriter, _ *http.Request) {
		entered <- struct{}{}
		<-release
		_, _ = writer.Write(fixture.successWire)
	})
	server.StartTLS()
	defer server.Close()
	provider := newTestHTTPProvider(t, server, fixture, HTTPProviderOptions{MaxConcurrent: 2, MaxAttempts: 1})
	defer provider.Close()

	errorsCh := make(chan error, 3)
	for range 3 {
		go func() {
			_, err := provider.Acquire(context.Background(), fixture.request)
			errorsCh <- err
		}()
	}
	for range 2 {
		select {
		case <-entered:
		case <-time.After(time.Second):
			t.Fatal("two calls did not enter")
		}
	}
	select {
	case <-entered:
		t.Fatal("third call exceeded concurrency bound")
	case <-time.After(30 * time.Millisecond):
	}
	close(release)
	for range 3 {
		if err := <-errorsCh; err != nil {
			t.Fatal(err)
		}
	}
}

func TestManagerBindsWireProviderGrantToSealedLocalCheckpoint(t *testing.T) {
	provider, manager, request := coalesceFixture(t)
	provider.grant.Checkpoint = CheckpointDigest{}
	result := make(chan acquireResult, 1)
	go func() {
		reservation, err := manager.Acquire(context.Background(), request)
		result <- acquireResult{reservation: reservation, err: err}
	}()
	awaitCoalesce(t, provider.started)
	provider.releaseOnce()
	select {
	case got := <-result:
		if got.err != nil {
			t.Fatalf("wire provider candidate rejected before local checkpoint binding: %v", got.err)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("manager did not complete wire provider candidate")
	}
}

type httpACPFixture struct {
	request       AcquireRequest
	signed        SignedACPRequest
	signer        identity.Signer
	resolver      ACPResultIssuerResolver
	resultPrivate ed25519.PrivateKey
	resultKID     []byte
	artifact      []byte
	successWire   []byte
}

func newHTTPACPFixture(t *testing.T) httpACPFixture {
	t.Helper()
	signer, _, _ := mustEnrollmentSigner(t, identity.PurposeDeviceACPRequest, 0x71, 4)
	request := validACPRequest(signer.KeyRef())
	signed, err := SignACPAcquireRequest(context.Background(), request, signer, acpTestNow)
	if err != nil {
		t.Fatal(err)
	}
	private, public, kid := mustRawResultSigner(t, 0x72)
	purpose, _ := ACPResultSigningPurpose()
	resolver := mustACPResultResolver(t, signed, purpose, public, kid)
	artifact := []byte("untrusted-route-grant-candidate")
	result := validACPResult(signed, ACPResultStatusSuccess)
	result.Artifact = artifact
	return httpACPFixture{request: request, signed: signed, signer: signer, resolver: resolver, resultPrivate: private, resultKID: kid, artifact: artifact, successWire: mustSignACPResult(t, result, private, kid)}
}

func newHTTP2TLSServer(t *testing.T, handler http.HandlerFunc) *httptest.Server {
	t.Helper()
	server := httptest.NewUnstartedServer(handler)
	server.EnableHTTP2 = true
	server.TLS = &tls.Config{MinVersion: tls.VersionTLS13, MaxVersion: tls.VersionTLS13}
	return server
}

func testTLSConfig(t *testing.T, server *httptest.Server) *tls.Config {
	t.Helper()
	certificate := server.Certificate()
	roots := x509.NewCertPool()
	roots.AddCert(certificate)
	return &tls.Config{RootCAs: roots, ServerName: certificate.DNSNames[0], MinVersion: tls.VersionTLS13, MaxVersion: tls.VersionTLS13}
}

func testHTTPProviderConfig(t *testing.T, server *httptest.Server, fixture httpACPFixture, options HTTPProviderOptions) HTTPProviderConfig {
	t.Helper()
	return HTTPProviderConfig{
		Endpoint: server.URL, TLSConfig: testTLSConfig(t, server), SourceOperator: fixture.request.Key.SourceOperator,
		Profile: fixture.request.Key.Profile, Signer: fixture.signer, ResultIssuers: fixture.resolver,
		RequestIDs: fixedRequestIDSource{value: RequestID{9, 8, 7, 6, 5, 4, 3, 2, 1, 2, 3, 4, 5, 6, 7, 8}},
		Options:    options, NowUnix: func() uint64 { return acpTestNow },
	}
}

func newTestHTTPProvider(t *testing.T, server *httptest.Server, fixture httpACPFixture, options HTTPProviderOptions) *HTTPProvider {
	t.Helper()
	provider, err := NewHTTPProvider(testHTTPProviderConfig(t, server, fixture, options))
	if err != nil {
		t.Fatal(err)
	}
	return provider
}

type fixedRequestIDSource struct{ value RequestID }

func (source fixedRequestIDSource) NewRequestID() (RequestID, error) { return source.value, nil }

// retryableHTTP2ReplayProbeTransport models the standard HTTP/2 transport's
// body replay hook after a retryable REFUSED_STREAM/qualifying GOAWAY. If
// GetBody is exposed, the hidden replay consumes a second body attempt before
// the explicit controller sees a response.
type retryableHTTP2ReplayProbeTransport struct {
	response     []byte
	bodyAttempts atomic.Int32
}

func (transport *retryableHTTP2ReplayProbeTransport) RoundTrip(request *http.Request) (*http.Response, error) {
	if _, err := io.ReadAll(request.Body); err != nil {
		return nil, err
	}
	transport.bodyAttempts.Add(1)
	if request.GetBody != nil {
		replayed, err := request.GetBody()
		if err != nil {
			return nil, err
		}
		if _, err := io.ReadAll(replayed); err != nil {
			_ = replayed.Close()
			return nil, err
		}
		_ = replayed.Close()
		transport.bodyAttempts.Add(1)
	}
	return &http.Response{
		StatusCode: http.StatusOK,
		ProtoMajor: 2,
		ProtoMinor: 0,
		TLS:        &tls.ConnectionState{Version: tls.VersionTLS13, NegotiatedProtocol: "h2"},
		Body:       io.NopCloser(bytes.NewReader(transport.response)),
		Header:     make(http.Header),
		Request:    request,
	}, nil
}
