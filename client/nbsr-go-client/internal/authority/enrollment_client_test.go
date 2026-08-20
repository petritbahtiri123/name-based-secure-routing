package authority

import (
	"bytes"
	"context"
	"crypto/sha256"
	"errors"
	"io"
	"net/http"
	"sync"
	"testing"
	"time"

	"nbsr.local/client/nbsr-go-client/internal/identity"
)

type enrollmentResultIssuerResolverFunc func(context.Context, []byte, string, string, uint64) (IssuerRecord, error)

func (function enrollmentResultIssuerResolverFunc) ResolveEnrollmentResultIssuer(ctx context.Context, kid []byte, profile, source string, now uint64) (IssuerRecord, error) {
	return function(ctx, kid, profile, source, now)
}

func TestEnrollmentHTTPClientReturnsOnlyVerifiedInitialEnrollment(t *testing.T) {
	request := validEnrollmentRequestPayload()
	signer, public, keyID := mustEnrollmentSigner(t, identity.PurposeDeviceACPRequest, 0x81, 1)
	request.DeviceSigningKey = EnrollmentDeviceSigningKey{PublicKey: public, KeyID: keyID, Purpose: identity.PurposeDeviceACPRequest, Generation: 1, Thumbprint: sha256.Sum256(public[:])}
	payload, err := EncodeEnrollmentRequestPayload(request)
	if err != nil {
		t.Fatal(err)
	}
	wire, err := SignEnrollmentRequest(context.Background(), request, signer)
	if err != nil {
		t.Fatal(err)
	}
	purpose, _ := EnrollmentResultSigningPurpose()
	private, resultPublic, resultKID := mustRawResultSigner(t, 0x82)
	resolver := mustEnrollmentResultResolver(t, request, purpose, resultPublic, resultKID)
	result := validEnrollmentResultPayload(EnrollmentStatusAccepted, payload)
	resultWire, err := signEnrollmentResultPayload(result, private, resultKID)
	if err != nil {
		t.Fatal(err)
	}
	server := newHTTP2TLSServer(t, func(writer http.ResponseWriter, incoming *http.Request) {
		if incoming.URL.Path != "/acp/enroll" || incoming.URL.RawQuery != "" {
			t.Errorf("unexpected enrollment target: %s", incoming.URL.String())
		}
		got, _ := io.ReadAll(incoming.Body)
		if !bytes.Equal(got, wire) {
			t.Error("enrollment request bytes changed")
		}
		_, _ = writer.Write(resultWire)
	})
	server.StartTLS()
	defer server.Close()

	client, err := NewEnrollmentHTTPClient(EnrollmentHTTPClientConfig{
		Endpoint: server.URL, TLSConfig: testTLSConfig(t, server), SourceOperator: request.SourceOperator, Profile: request.Profile,
		Signer: signer, ResultIssuers: resolver, Options: HTTPProviderOptions{MaxAttempts: 1}, NowUnix: func() uint64 { return request.DeadlineUnix - 1 },
	})
	if err != nil {
		t.Fatal(err)
	}
	defer client.Close()
	got, err := client.Enroll(context.Background(), request)
	if err != nil {
		t.Fatal(err)
	}
	if got.Status != EnrollmentStatusAccepted || got.DeviceIdentity == nil || result.DeviceIdentity == nil || *got.DeviceIdentity != *result.DeviceIdentity {
		t.Fatalf("unexpected enrollment result: %#v", got)
	}
}

func TestEnrollmentHTTPClientRetryIsByteStableAndSemanticDenyIsTerminal(t *testing.T) {
	request := validEnrollmentRequestPayload()
	signer, public, keyID := mustEnrollmentSigner(t, identity.PurposeDeviceACPRequest, 0x83, 1)
	request.DeviceSigningKey = EnrollmentDeviceSigningKey{PublicKey: public, KeyID: keyID, Purpose: identity.PurposeDeviceACPRequest, Generation: 1, Thumbprint: sha256.Sum256(public[:])}
	payload, _ := EncodeEnrollmentRequestPayload(request)
	purpose, _ := EnrollmentResultSigningPurpose()
	private, resultPublic, resultKID := mustRawResultSigner(t, 0x84)
	resolver := mustEnrollmentResultResolver(t, request, purpose, resultPublic, resultKID)
	deny := validEnrollmentResultPayload(EnrollmentStatusRejected, payload)
	denyWire, _ := signEnrollmentResultPayload(deny, private, resultKID)
	var mu sync.Mutex
	var bodies [][]byte
	server := newHTTP2TLSServer(t, func(writer http.ResponseWriter, incoming *http.Request) {
		body, _ := io.ReadAll(incoming.Body)
		mu.Lock()
		bodies = append(bodies, append([]byte(nil), body...))
		attempt := len(bodies)
		mu.Unlock()
		if attempt == 1 {
			panic(http.ErrAbortHandler)
		}
		_, _ = writer.Write(denyWire)
	})
	server.StartTLS()
	defer server.Close()
	client, err := NewEnrollmentHTTPClient(EnrollmentHTTPClientConfig{
		Endpoint: server.URL, TLSConfig: testTLSConfig(t, server), SourceOperator: request.SourceOperator, Profile: request.Profile,
		Signer: signer, ResultIssuers: resolver, Options: HTTPProviderOptions{MaxAttempts: 3, RetryBackoff: time.Millisecond}, NowUnix: func() uint64 { return request.DeadlineUnix - 1 },
	})
	if err != nil {
		t.Fatal(err)
	}
	defer client.Close()
	got, err := client.Enroll(context.Background(), request)
	if !errors.Is(err, ErrTerminalEnrollment) || got.Status != EnrollmentStatusRejected {
		t.Fatalf("signed deny result=%#v error=%v", got, err)
	}
	mu.Lock()
	defer mu.Unlock()
	if len(bodies) != 2 || !bytes.Equal(bodies[0], bodies[1]) {
		t.Fatalf("enrollment retry attempts=%d or bytes changed", len(bodies))
	}
}

func TestEnrollmentHTTPClientRejectsMalformedOversizedAndMisbindingResults(t *testing.T) {
	request := validEnrollmentRequestPayload()
	signer, public, keyID := mustEnrollmentSigner(t, identity.PurposeDeviceACPRequest, 0x85, 1)
	request.DeviceSigningKey = EnrollmentDeviceSigningKey{PublicKey: public, KeyID: keyID, Purpose: identity.PurposeDeviceACPRequest, Generation: 1, Thumbprint: sha256.Sum256(public[:])}
	payload, _ := EncodeEnrollmentRequestPayload(request)
	purpose, _ := EnrollmentResultSigningPurpose()
	private, resultPublic, resultKID := mustRawResultSigner(t, 0x86)
	resolver := mustEnrollmentResultResolver(t, request, purpose, resultPublic, resultKID)
	wrongBinding := validEnrollmentResultPayload(EnrollmentStatusAccepted, payload)
	wrongBinding.RequestDigest[0] ^= 0xff
	wrongBindingWire, _ := signEnrollmentResultPayload(wrongBinding, private, resultKID)
	tests := []struct {
		name string
		wire []byte
		want error
	}{
		{name: "malformed", wire: []byte{0xd2, 0xff}, want: ErrInvalidAuthority},
		{name: "oversized", wire: bytes.Repeat([]byte{0}, maxEnrollmentResultBodySize+1), want: ErrInvalidAuthority},
		{name: "request digest mismatch", wire: wrongBindingWire, want: ErrBindingMismatch},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			server := newHTTP2TLSServer(t, func(writer http.ResponseWriter, _ *http.Request) { _, _ = writer.Write(test.wire) })
			server.StartTLS()
			defer server.Close()
			client, err := NewEnrollmentHTTPClient(EnrollmentHTTPClientConfig{
				Endpoint: server.URL, TLSConfig: testTLSConfig(t, server), SourceOperator: request.SourceOperator, Profile: request.Profile,
				Signer: signer, ResultIssuers: resolver, Options: HTTPProviderOptions{MaxAttempts: 1}, NowUnix: func() uint64 { return request.DeadlineUnix - 1 },
			})
			if err != nil {
				t.Fatal(err)
			}
			defer client.Close()
			if _, err := client.Enroll(context.Background(), request); !errors.Is(err, test.want) {
				t.Fatalf("error=%v, want %v", err, test.want)
			}
		})
	}
}

func TestEnrollmentHTTPClientIndependentlyRejectsWrongIssuerPurposeAndKID(t *testing.T) {
	request := validEnrollmentRequestPayload()
	signer, public, keyID := mustEnrollmentSigner(t, identity.PurposeDeviceACPRequest, 0x87, 1)
	request.DeviceSigningKey = EnrollmentDeviceSigningKey{PublicKey: public, KeyID: keyID, Purpose: identity.PurposeDeviceACPRequest, Generation: 1, Thumbprint: sha256.Sum256(public[:])}
	payload, _ := EncodeEnrollmentRequestPayload(request)
	private, resultPublic, resultKID := mustRawResultSigner(t, 0x88)
	accepted := validEnrollmentResultPayload(EnrollmentStatusAccepted, payload)
	wire, _ := signEnrollmentResultPayload(accepted, private, resultKID)
	server := newHTTP2TLSServer(t, func(writer http.ResponseWriter, _ *http.Request) { _, _ = writer.Write(wire) })
	server.StartTLS()
	defer server.Close()
	purpose, _ := EnrollmentResultSigningPurpose()
	base := IssuerRecord{
		KID: resultKID, PublicKey: resultPublic, Purpose: purpose, Profile: request.Profile, SourceOperator: request.SourceOperator,
		Generation: 1, NotBefore: request.DeadlineUnix - 2, ExpiresAt: request.DeadlineUnix + 2,
	}
	tests := []struct {
		name string
		edit func(*IssuerRecord)
		want error
	}{
		{name: "wrong purpose", edit: func(record *IssuerRecord) { record.Purpose = acpResultSigningPurpose }, want: ErrInvalidKeyPurpose},
		{name: "wrong kid", edit: func(record *IssuerRecord) { record.KID = []byte("different-kid") }, want: ErrUnknownIdentity},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			record := base
			test.edit(&record)
			resolver := enrollmentResultIssuerResolverFunc(func(context.Context, []byte, string, string, uint64) (IssuerRecord, error) { return record, nil })
			client, err := NewEnrollmentHTTPClient(EnrollmentHTTPClientConfig{
				Endpoint: server.URL, TLSConfig: testTLSConfig(t, server), SourceOperator: request.SourceOperator, Profile: request.Profile,
				Signer: signer, ResultIssuers: resolver, Options: HTTPProviderOptions{MaxAttempts: 1}, NowUnix: func() uint64 { return request.DeadlineUnix - 1 },
			})
			if err != nil {
				t.Fatal(err)
			}
			defer client.Close()
			if _, err := client.Enroll(context.Background(), request); !errors.Is(err, test.want) {
				t.Fatalf("error=%v, want %v", err, test.want)
			}
		})
	}
}
