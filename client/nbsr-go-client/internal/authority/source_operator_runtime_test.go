package authority

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"crypto/tls"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"nbsr.local/client/nbsr-go-client/internal/identity"
)

func TestSourceOperatorRuntimeServesAuthorityAndInitialEnrollmentOverTLS13HTTP2(t *testing.T) {
	fixture := newSourceOperatorRuntimeFixture(t, filepath.Join(t.TempDir(), "idempotency.cbor"), nil)
	server := newHTTP2TLSServer(t, fixture.runtime.ServeHTTP)
	server.StartTLS()
	defer server.Close()

	acpPurpose, _ := ACPResultSigningPurpose()
	provider, err := NewHTTPProvider(HTTPProviderConfig{
		Endpoint: server.URL, TLSConfig: testTLSConfig(t, server), SourceOperator: fixture.request.Key.SourceOperator,
		Profile: fixture.request.Key.Profile, Signer: fixture.requestSigner,
		ResultIssuers: mustACPResultResolver(t, fixture.signed, acpPurpose, fixture.acpSigner.public, fixture.acpSigner.kid),
		RequestIDs:    fixedRequestIDSource{value: RequestID{9, 8, 7, 6, 5, 4, 3, 2, 1, 2, 3, 4, 5, 6, 7, 8}},
		Options:       HTTPProviderOptions{MaxAttempts: 1}, NowUnix: func() uint64 { return fixture.now.Load() },
	})
	if err != nil {
		t.Fatal(err)
	}
	defer provider.Close()

	grant, err := provider.Acquire(context.Background(), fixture.request)
	if err != nil {
		t.Fatal(err)
	}
	if string(grant.ExactRouteGrant) != "artifact:acquire_route_grant" || grant.AuthorityGeneration != fixture.request.Key.AuthorityGeneration {
		t.Fatalf("acquire result = (%q, %d)", grant.ExactRouteGrant, grant.AuthorityGeneration)
	}
	renew := RenewRequest{AcquireRequest: fixture.request, PreviousGrant: RouteGrantDigest(bytes32ForSeed(0x81))}
	grant, err = provider.Renew(context.Background(), renew)
	if err != nil {
		t.Fatal(err)
	}
	if string(grant.ExactRouteGrant) != "artifact:renew_route_grant" {
		t.Fatalf("renew artifact = %q", grant.ExactRouteGrant)
	}
	freshnessRequest := FreshnessRequest{
		SourceOperator: fixture.request.Key.SourceOperator, Profile: fixture.request.Key.Profile,
		DeviceID: fixture.request.Device.ID, DeviceGeneration: fixture.request.Device.CredentialGeneration,
		AfterGeneration: fixture.request.Key.AuthorityGeneration, AfterCheckpoint: CheckpointDigest(bytes32ForSeed(0x82)),
		DeadlineUnix: fixture.now.Load() + 30,
	}
	freshness, err := provider.Freshness(context.Background(), freshnessRequest)
	if err != nil {
		t.Fatal(err)
	}
	if string(freshness.Evidence) != "artifact:freshness" {
		t.Fatalf("freshness artifact = %q", freshness.Evidence)
	}

	enrollmentRequest := fixture.enrollmentRequest()
	enrollmentPurpose, err := EnrollmentResultSigningPurpose()
	if err != nil {
		t.Fatal(err)
	}
	enrollmentClient, err := NewEnrollmentHTTPClient(EnrollmentHTTPClientConfig{
		Endpoint: server.URL, TLSConfig: testTLSConfig(t, server), SourceOperator: enrollmentRequest.SourceOperator,
		Profile: enrollmentRequest.Profile, Signer: fixture.requestSigner,
		ResultIssuers: runtimeEnrollmentResultResolver(enrollmentRequest, enrollmentPurpose, fixture.enrollmentSigner.public, fixture.enrollmentSigner.kid, fixture.now.Load()),
		Options:       HTTPProviderOptions{MaxAttempts: 1}, NowUnix: func() uint64 { return fixture.now.Load() },
	})
	if err != nil {
		t.Fatal(err)
	}
	defer enrollmentClient.Close()
	result, err := enrollmentClient.Enroll(context.Background(), enrollmentRequest)
	if err != nil {
		t.Fatal(err)
	}
	if result.Status != EnrollmentStatusAccepted || result.DeviceIdentity == nil || result.DeviceIdentity.SigningKey.ID != enrollmentRequest.DeviceSigningKey.KeyID {
		t.Fatalf("enrollment result = %#v", result)
	}

	if got := fixture.authority.operations(); !equalOperations(got, []ACPOperation{ACPOperationAcquire, ACPOperationRenew, ACPOperationFreshness}) {
		t.Fatalf("authority operations = %v", got)
	}
	if fixture.bootstrap.calls.Load() != 1 || fixture.enrollment.calls.Load() != 1 {
		t.Fatalf("bootstrap/enrollment calls = %d/%d", fixture.bootstrap.calls.Load(), fixture.enrollment.calls.Load())
	}
	if !fixture.acpSigner.onlyPurpose(15) || !fixture.enrollmentSigner.onlyPurpose(16) {
		t.Fatalf("signer purposes = %v / %v", fixture.acpSigner.purposes(), fixture.enrollmentSigner.purposes())
	}
}

func TestSourceOperatorRuntimeRejectsMalformedAuthenticationAndUnsignedBypassBeforeDecision(t *testing.T) {
	fixture := newSourceOperatorRuntimeFixture(t, filepath.Join(t.TempDir(), "idempotency.cbor"), nil)
	otherSigner, _, _ := mustEnrollmentSigner(t, identity.PurposeDeviceACPRequest, 0x95, 4)
	otherRequest := validACPRequest(otherSigner.KeyRef())
	otherSigned, err := SignACPAcquireRequest(context.Background(), otherRequest, otherSigner, fixture.now.Load())
	if err != nil {
		t.Fatal(err)
	}
	wrongPurposeRecord := fixture.requestKey
	wrongPurposeRecord.Purpose = identity.PurposeTSProof
	wrongPurposeRuntime := fixture.runtimeWithResolver(t, deviceACPRequestKeyResolverFunc(func(context.Context, []byte, uint64) (DeviceACPRequestKey, error) {
		return wrongPurposeRecord, nil
	}))

	cases := []struct {
		name    string
		runtime *SourceOperatorRuntime
		body    []byte
		status  int
	}{
		{name: "malformed cose", runtime: fixture.runtime, body: []byte{0x01, 0x02}, status: http.StatusBadRequest},
		{name: "unsigned payload", runtime: fixture.runtime, body: fixture.signed.Payload(), status: http.StatusBadRequest},
		{name: "unknown kid", runtime: fixture.runtime, body: otherSigned.Body(), status: http.StatusUnauthorized},
		{name: "wrong purpose", runtime: wrongPurposeRuntime, body: fixture.signed.Body(), status: http.StatusUnauthorized},
		{name: "oversized complete body", runtime: fixture.runtime, body: make([]byte, maxACPAcquireRequestBodySize+1), status: http.StatusRequestEntityTooLarge},
	}
	badSignature := fixture.signed.Body()
	badSignature[len(badSignature)-1] ^= 0xff
	cases = append(cases, struct {
		name    string
		runtime *SourceOperatorRuntime
		body    []byte
		status  int
	}{name: "bad signature", runtime: fixture.runtime, body: badSignature, status: http.StatusUnauthorized})

	for _, test := range cases {
		t.Run(test.name, func(t *testing.T) {
			response := performRuntimeRequest(test.runtime, "/acp/authority", test.body, nil)
			if response.Code != test.status {
				t.Fatalf("status = %d, want %d; body=%q", response.Code, test.status, response.Body.Bytes())
			}
			if response.Header().Get("Content-Type") == "application/cose" {
				t.Fatal("unauthenticated failure was encoded as a signed semantic result")
			}
		})
	}
	if fixture.authority.callCount() != 0 {
		t.Fatalf("authority decision calls = %d, want zero", fixture.authority.callCount())
	}
}

func TestSourceOperatorRuntimeAuthenticatesBeforeSignedVersionProfileAndBindingFailures(t *testing.T) {
	fixture := newSourceOperatorRuntimeFixture(t, filepath.Join(t.TempDir(), "idempotency.cbor"), nil)

	versionFields := mustDecodeMap(t, fixture.signed.Payload())
	versionFields[0] = uint64(2)
	versionFields[2] = []byte{0x21, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16}
	wrongVersion := mustSignRawACPRequest(t, versionFields, fixture.requestSigner)
	nestedProfileFields := mustDecodeMap(t, fixture.signed.Payload())
	operationFields := nestedProfileFields[6].(map[uint64]any)
	keyFields := operationFields[0].(map[uint64]any)
	keyFields[6] = "other-nested-profile"
	nestedProfileFields[2] = []byte{0x22, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16}
	wrongNestedProfile := mustSignRawACPRequest(t, nestedProfileFields, fixture.requestSigner)
	malformedFields := mustDecodeMap(t, fixture.signed.Payload())
	malformedFields[2] = []byte{0x25, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16}
	malformedOperationFields := malformedFields[6].(map[uint64]any)
	malformedOperationFields[99] = uint64(1)
	malformedSigned := mustSignRawACPRequest(t, malformedFields, fixture.requestSigner)

	wrongProfileRequest := cloneACPRequest(fixture.request)
	wrongProfileRequest.Key.Profile = "unsupported-profile"
	wrongProfileRequest.RequestID[0] = 0x23
	wrongProfile, err := SignACPAcquireRequest(context.Background(), wrongProfileRequest, fixture.requestSigner, fixture.now.Load())
	if err != nil {
		t.Fatal(err)
	}
	wrongOperatorRequest := cloneACPRequest(fixture.request)
	wrongOperatorRequest.Key.SourceOperator = "other.operator"
	wrongOperatorRequest.Intent.SourceOperator = "other.operator"
	wrongOperatorRequest.Device.SourceOperatorID = "other.operator"
	wrongOperatorRequest.RequestID[0] = 0x24
	wrongOperator, err := SignACPAcquireRequest(context.Background(), wrongOperatorRequest, fixture.requestSigner, fixture.now.Load())
	if err != nil {
		t.Fatal(err)
	}

	misboundRecord := fixture.requestKey
	misboundRecord.DeviceID[0] ^= 0xff
	misboundRuntime := fixture.runtimeWithResolver(t, deviceACPRequestKeyResolverFunc(func(context.Context, []byte, uint64) (DeviceACPRequestKey, error) {
		return misboundRecord, nil
	}))

	cases := []struct {
		name    string
		runtime *SourceOperatorRuntime
		body    []byte
		want    ACPResultStatus
	}{
		{name: "version", runtime: fixture.runtime, body: wrongVersion, want: ACPResultStatusUnsupportedVersion},
		{name: "profile", runtime: fixture.runtime, body: wrongProfile.Body(), want: ACPResultStatusUnsupportedProfile},
		{name: "nested profile binding", runtime: fixture.runtime, body: wrongNestedProfile, want: ACPResultStatusBindingError},
		{name: "malformed signed request", runtime: fixture.runtime, body: malformedSigned, want: ACPResultStatusInvalidRequest},
		{name: "operator", runtime: fixture.runtime, body: wrongOperator.Body(), want: ACPResultStatusBindingError},
		{name: "device binding", runtime: misboundRuntime, body: fixture.signed.Body(), want: ACPResultStatusBindingError},
	}
	for _, test := range cases {
		t.Run(test.name, func(t *testing.T) {
			response := performRuntimeRequest(test.runtime, "/acp/authority", test.body, nil)
			if response.Code != http.StatusOK {
				t.Fatalf("status = %d; body=%q", response.Code, response.Body.Bytes())
			}
			result := parseAndVerifyRuntimeACPResult(t, response.Body.Bytes(), fixture.acpSigner.public)
			if result.Status != test.want {
				t.Fatalf("semantic status = %q, want %q", result.Status, test.want)
			}
		})
	}
	if fixture.authority.callCount() != 0 {
		t.Fatalf("authority decision calls = %d, want zero", fixture.authority.callCount())
	}
}

func TestSourceOperatorRuntimeSignsExpiryWhenEvaluationCompletesAtDeadline(t *testing.T) {
	var fixture *sourceOperatorRuntimeFixture
	fixture = newSourceOperatorRuntimeFixture(t, filepath.Join(t.TempDir(), "idempotency.cbor"), func(_ context.Context, request VerifiedACPRequest) (ACPDecision, error) {
		fixture.now.Store(request.DeadlineUnix())
		return testSuccessACPDecision(request), nil
	})
	response := performRuntimeRequest(fixture.runtime, "/acp/authority", fixture.signed.Body(), nil)
	result := parseAndVerifyRuntimeACPResult(t, response.Body.Bytes(), fixture.acpSigner.public)
	if result.Status != ACPResultStatusRequestExpired || result.Artifact != nil {
		t.Fatalf("ACP completion-at-deadline result = %#v", result)
	}

	fixture.now.Store(acpTestNow)
	request := fixture.enrollmentRequest()
	wire, err := SignEnrollmentRequest(context.Background(), request, fixture.requestSigner)
	if err != nil {
		t.Fatal(err)
	}
	fixture.enrollment.decide = func(_ context.Context, _ BootstrapAuthorization, verified VerifiedEnrollmentRequest) (EnrollmentDecision, error) {
		fixture.now.Store(verified.Payload().DeadlineUnix)
		return EnrollmentDecision{Status: EnrollmentStatusRejected}, nil
	}
	response = performRuntimeRequest(fixture.runtime, "/acp/enroll", wire, nil)
	enrollmentResult := parseAndVerifyRuntimeEnrollmentResult(t, response.Body.Bytes(), fixture.enrollmentSigner.public)
	if enrollmentResult.Status != EnrollmentStatusExpired || enrollmentResult.DeviceIdentity != nil {
		t.Fatalf("enrollment completion-at-deadline result = %#v", enrollmentResult)
	}
}

func TestSourceOperatorRuntimeReturnsSignedPolicyStalenessAndExpiryDecisions(t *testing.T) {
	statuses := map[ACPOperation]ACPResultStatus{
		ACPOperationAcquire: ACPResultStatusPolicyDenied, ACPOperationRenew: ACPResultStatusStaleGeneration,
		ACPOperationFreshness: ACPResultStatusStaleFreshness,
	}
	fixture := newSourceOperatorRuntimeFixture(t, filepath.Join(t.TempDir(), "idempotency.cbor"), func(_ context.Context, request VerifiedACPRequest) (ACPDecision, error) {
		return ACPDecision{Status: statuses[request.Operation()], AuthorityGeneration: request.AuthorityGeneration()}, nil
	})

	renew, err := SignACPRenewRequest(context.Background(), RenewRequest{AcquireRequest: fixture.request, PreviousGrant: RouteGrantDigest(bytes32ForSeed(0xa1))}, fixture.requestSigner, fixture.now.Load())
	if err != nil {
		t.Fatal(err)
	}
	freshnessRequest := FreshnessRequest{
		SourceOperator: fixture.request.Key.SourceOperator, Profile: fixture.request.Key.Profile,
		DeviceID: fixture.request.Device.ID, DeviceGeneration: fixture.request.Device.CredentialGeneration,
		AfterGeneration: fixture.request.Key.AuthorityGeneration, AfterCheckpoint: CheckpointDigest(bytes32ForSeed(0xa2)),
		DeadlineUnix: fixture.now.Load() + 30,
	}
	freshness, err := SignACPFreshnessRequest(context.Background(), freshnessRequest, RequestID{8, 7, 6, 5, 4, 3, 2, 1, 1, 2, 3, 4, 5, 6, 7, 8}, fixture.requestSigner, fixture.now.Load())
	if err != nil {
		t.Fatal(err)
	}
	for _, signed := range []SignedACPRequest{fixture.signed, renew, freshness} {
		response := performRuntimeRequest(fixture.runtime, "/acp/authority", signed.Body(), nil)
		result := parseAndVerifyRuntimeACPResult(t, response.Body.Bytes(), fixture.acpSigner.public)
		if result.Status != statuses[signed.Operation()] {
			t.Fatalf("%s status = %q", signed.Operation(), result.Status)
		}
	}

	expiredRequest := cloneACPRequest(fixture.request)
	expiredRequest.RequestID[0]++
	expired, err := SignACPAcquireRequest(context.Background(), expiredRequest, fixture.requestSigner, fixture.now.Load())
	if err != nil {
		t.Fatal(err)
	}
	fixture.now.Store(expired.DeadlineUnix())
	response := performRuntimeRequest(fixture.runtime, "/acp/authority", expired.Body(), nil)
	result := parseAndVerifyRuntimeACPResult(t, response.Body.Bytes(), fixture.acpSigner.public)
	if result.Status != ACPResultStatusRequestExpired {
		t.Fatalf("expired status = %q", result.Status)
	}
	if fixture.authority.callCount() != 3 {
		t.Fatalf("authority decisions = %d, want 3 without expired evaluation", fixture.authority.callCount())
	}
}

func TestSourceOperatorRuntimeAuthorizesBootstrapBeforeEnrollmentAndRejectsReenrollment(t *testing.T) {
	fixture := newSourceOperatorRuntimeFixture(t, filepath.Join(t.TempDir(), "idempotency.cbor"), nil)
	enrollmentRequest := fixture.enrollmentRequest()
	wire, err := SignEnrollmentRequest(context.Background(), enrollmentRequest, fixture.requestSigner)
	if err != nil {
		t.Fatal(err)
	}

	fixture.bootstrap.authorized = BootstrapAuthorization{}
	fixture.bootstrap.err = ErrBootstrapUnauthorized
	response := performRuntimeRequest(fixture.runtime, "/acp/enroll", wire, nil)
	if response.Code != http.StatusForbidden || response.Header().Get("Content-Type") == "application/cose" {
		t.Fatalf("bootstrap rejection = %d %q", response.Code, response.Header().Get("Content-Type"))
	}
	if fixture.enrollment.calls.Load() != 0 {
		t.Fatal("generic enrollment ran before bootstrap authorization")
	}

	fixture.bootstrap.err = nil
	fixture.bootstrap.authorized = BootstrapAuthorization{Subject: "bootstrap-subject"}
	response = performRuntimeRequest(fixture.runtime, "/acp/enroll", make([]byte, maxEnrollmentRequestBodySize+1), nil)
	if response.Code != http.StatusRequestEntityTooLarge || fixture.enrollment.calls.Load() != 0 {
		t.Fatalf("oversized enrollment rejection = status %d, calls %d", response.Code, fixture.enrollment.calls.Load())
	}
	requestPayload, err := EncodeEnrollmentRequestPayload(enrollmentRequest)
	if err != nil {
		t.Fatal(err)
	}
	fields := mustDecodeMap(t, requestPayload)
	fields[6] = uint64(1) // forbidden reenrollment/replacement field
	reenrollWire := mustSignRawEnrollmentRequest(t, fields, fixture.requestSigner)
	response = performRuntimeRequest(fixture.runtime, "/acp/enroll", reenrollWire, nil)
	if response.Code != http.StatusBadRequest || fixture.enrollment.calls.Load() != 0 {
		t.Fatalf("reenrollment rejection = status %d, calls %d", response.Code, fixture.enrollment.calls.Load())
	}

	fixture.enrollment.decision = EnrollmentDecision{Status: EnrollmentStatusRejected}
	response = performRuntimeRequest(fixture.runtime, "/acp/enroll", wire, nil)
	if response.Code != http.StatusOK {
		t.Fatalf("replacement rejection HTTP status = %d", response.Code)
	}
	result := parseAndVerifyRuntimeEnrollmentResult(t, response.Body.Bytes(), fixture.enrollmentSigner.public)
	if result.Status != EnrollmentStatusRejected || result.DeviceIdentity != nil {
		t.Fatalf("replacement result = %#v", result)
	}
	if fixture.enrollment.calls.Load() != 1 {
		t.Fatalf("initial-only decision calls = %d", fixture.enrollment.calls.Load())
	}
}

func TestSourceOperatorRuntimeDoesNotReplayEnrollmentAcrossBootstrapSubjects(t *testing.T) {
	fixture := newSourceOperatorRuntimeFixture(t, filepath.Join(t.TempDir(), "idempotency.cbor"), nil)
	request := fixture.enrollmentRequest()
	wire, err := SignEnrollmentRequest(context.Background(), request, fixture.requestSigner)
	if err != nil {
		t.Fatal(err)
	}
	first := performRuntimeRequest(fixture.runtime, "/acp/enroll", wire, nil)
	if result := parseAndVerifyRuntimeEnrollmentResult(t, first.Body.Bytes(), fixture.enrollmentSigner.public); result.Status != EnrollmentStatusAccepted {
		t.Fatalf("first status = %q", result.Status)
	}

	fixture.bootstrap.authorized = BootstrapAuthorization{Subject: "different-bootstrap-subject"}
	fixture.enrollment.decision = EnrollmentDecision{Status: EnrollmentStatusRejected}
	second := performRuntimeRequest(fixture.runtime, "/acp/enroll", wire, nil)
	result := parseAndVerifyRuntimeEnrollmentResult(t, second.Body.Bytes(), fixture.enrollmentSigner.public)
	if result.Status != EnrollmentStatusRejected || fixture.enrollment.calls.Load() != 2 {
		t.Fatalf("cross-subject result = %q, decisions=%d; prior subject replay bypassed authorization", result.Status, fixture.enrollment.calls.Load())
	}
}

func TestSourceOperatorRuntimeReplaysAndPersistsExactEnrollmentTerminal(t *testing.T) {
	path := filepath.Join(t.TempDir(), "idempotency.cbor")
	fixture := newSourceOperatorRuntimeFixture(t, path, nil)
	request := fixture.enrollmentRequest()
	wire, err := SignEnrollmentRequest(context.Background(), request, fixture.requestSigner)
	if err != nil {
		t.Fatal(err)
	}
	first := performRuntimeRequest(fixture.runtime, "/acp/enroll", wire, nil)
	second := performRuntimeRequest(fixture.runtime, "/acp/enroll", wire, nil)
	if first.Code != http.StatusOK || second.Code != http.StatusOK || !bytes.Equal(first.Body.Bytes(), second.Body.Bytes()) {
		t.Fatalf("enrollment duplicate replay differed: %d/%d %x/%x", first.Code, second.Code, first.Body.Bytes(), second.Body.Bytes())
	}
	if fixture.enrollment.calls.Load() != 1 || fixture.enrollmentSigner.callCount() != 1 {
		t.Fatalf("enrollment decision/sign calls = %d/%d, want one", fixture.enrollment.calls.Load(), fixture.enrollmentSigner.callCount())
	}

	conflictingRequest := request
	conflictingRequest.DeadlineUnix--
	conflicting, err := SignEnrollmentRequest(context.Background(), conflictingRequest, fixture.requestSigner)
	if err != nil {
		t.Fatal(err)
	}
	conflictResponse := performRuntimeRequest(fixture.runtime, "/acp/enroll", conflicting, nil)
	conflict := parseAndVerifyRuntimeEnrollmentResult(t, conflictResponse.Body.Bytes(), fixture.enrollmentSigner.public)
	if conflict.Status != EnrollmentStatusRequestConflict || fixture.enrollment.calls.Load() != 1 {
		t.Fatalf("enrollment conflict = %q, decisions=%d", conflict.Status, fixture.enrollment.calls.Load())
	}
	otherSigner, otherPublic, otherKID := mustEnrollmentSigner(t, identity.PurposeDeviceACPRequest, 0xa7, request.DeviceSigningKey.Generation+1)
	otherRequest := request
	otherRequest.DeviceSigningKey = EnrollmentDeviceSigningKey{
		PublicKey: otherPublic, KeyID: otherKID, Purpose: identity.PurposeDeviceACPRequest,
		Generation: otherSigner.KeyRef().Generation, Thumbprint: otherSigner.KeyRef().Thumbprint,
	}
	otherWire, err := SignEnrollmentRequest(context.Background(), otherRequest, otherSigner)
	if err != nil {
		t.Fatal(err)
	}
	keyConflictResponse := performRuntimeRequest(fixture.runtime, "/acp/enroll", otherWire, nil)
	keyConflict := parseAndVerifyRuntimeEnrollmentResult(t, keyConflictResponse.Body.Bytes(), fixture.enrollmentSigner.public)
	if keyConflict.Status != EnrollmentStatusRequestConflict || fixture.enrollment.calls.Load() != 1 {
		t.Fatalf("proposed-key conflict = %q, decisions=%d; self-asserted key changed idempotency actor", keyConflict.Status, fixture.enrollment.calls.Load())
	}

	exact := append([]byte(nil), first.Body.Bytes()...)
	if err := fixture.runtime.Close(); err != nil {
		t.Fatal(err)
	}
	restarted := fixture.reopen(t, path)
	replay := performRuntimeRequest(restarted, "/acp/enroll", wire, nil)
	if replay.Code != http.StatusOK || !bytes.Equal(replay.Body.Bytes(), exact) {
		t.Fatalf("enrollment restart replay = %d %x, want %x", replay.Code, replay.Body.Bytes(), exact)
	}
	if fixture.enrollment.calls.Load() != 1 || fixture.enrollmentSigner.callCount() != 3 {
		t.Fatalf("post-restart enrollment decision/sign calls = %d/%d", fixture.enrollment.calls.Load(), fixture.enrollmentSigner.callCount())
	}
}

func TestSourceOperatorRuntimeReplaysExactSignedBytesConflictsAndRestarts(t *testing.T) {
	path := filepath.Join(t.TempDir(), "idempotency.cbor")
	fixture := newSourceOperatorRuntimeFixture(t, path, nil)
	first := performRuntimeRequest(fixture.runtime, "/acp/authority", fixture.signed.Body(), nil)
	second := performRuntimeRequest(fixture.runtime, "/acp/authority", fixture.signed.Body(), nil)
	if first.Code != http.StatusOK || second.Code != http.StatusOK || !bytes.Equal(first.Body.Bytes(), second.Body.Bytes()) {
		t.Fatalf("duplicate replay differed: %d/%d %x/%x", first.Code, second.Code, first.Body.Bytes(), second.Body.Bytes())
	}
	if fixture.authority.callCount() != 1 || fixture.acpSigner.callCount() != 1 {
		t.Fatalf("decision/sign calls = %d/%d, want one", fixture.authority.callCount(), fixture.acpSigner.callCount())
	}

	conflictingRequest := cloneACPRequest(fixture.request)
	conflictingRequest.DeadlineUnix--
	conflicting, err := SignACPAcquireRequest(context.Background(), conflictingRequest, fixture.requestSigner, fixture.now.Load())
	if err != nil {
		t.Fatal(err)
	}
	conflictResponse := performRuntimeRequest(fixture.runtime, "/acp/authority", conflicting.Body(), nil)
	conflict := parseAndVerifyRuntimeACPResult(t, conflictResponse.Body.Bytes(), fixture.acpSigner.public)
	if conflict.Status != ACPResultStatusRequestIDConflict || fixture.authority.callCount() != 1 {
		t.Fatalf("conflict = %q, decisions %d", conflict.Status, fixture.authority.callCount())
	}

	exact := append([]byte(nil), first.Body.Bytes()...)
	if err := fixture.runtime.Close(); err != nil {
		t.Fatal(err)
	}
	restarted := fixture.reopen(t, path)
	replay := performRuntimeRequest(restarted, "/acp/authority", fixture.signed.Body(), nil)
	if replay.Code != http.StatusOK || !bytes.Equal(replay.Body.Bytes(), exact) {
		t.Fatalf("restart replay = %d %x, want %x", replay.Code, replay.Body.Bytes(), exact)
	}
	if fixture.authority.callCount() != 1 || fixture.acpSigner.callCount() != 2 {
		// The conflict result is newly signed; restart replay must add neither a
		// decision nor a signature.
		t.Fatalf("post-restart decision/sign calls = %d/%d", fixture.authority.callCount(), fixture.acpSigner.callCount())
	}
}

func TestSourceOperatorRuntimeCollapsesFourDuplicateWaitersAndBoundsTheFifth(t *testing.T) {
	started := make(chan struct{})
	release := make(chan struct{})
	var startOnce sync.Once
	fixture := newSourceOperatorRuntimeFixture(t, filepath.Join(t.TempDir(), "idempotency.cbor"), func(ctx context.Context, request VerifiedACPRequest) (ACPDecision, error) {
		startOnce.Do(func() { close(started) })
		select {
		case <-release:
			return testSuccessACPDecision(request), nil
		case <-ctx.Done():
			return ACPDecision{}, ctx.Err()
		}
	})

	type outcome struct {
		code int
		body []byte
	}
	results := make(chan outcome, 5)
	go func() {
		response := performRuntimeRequest(fixture.runtime, "/acp/authority", fixture.signed.Body(), nil)
		results <- outcome{code: response.Code, body: append([]byte(nil), response.Body.Bytes()...)}
	}()
	<-started
	for index := 0; index < 4; index++ {
		go func() {
			response := performRuntimeRequest(fixture.runtime, "/acp/authority", fixture.signed.Body(), nil)
			results <- outcome{code: response.Code, body: append([]byte(nil), response.Body.Bytes()...)}
		}()
		waitForRuntimeWaiters(t, fixture.runtime, index+1)
	}
	overflow := performRuntimeRequest(fixture.runtime, "/acp/authority", fixture.signed.Body(), nil)
	if overflow.Code != http.StatusTooManyRequests || overflow.Header().Get("Content-Type") == "application/cose" {
		t.Fatalf("fifth waiter = %d %q, want unsigned bounded admission", overflow.Code, overflow.Header().Get("Content-Type"))
	}
	close(release)
	var exact []byte
	for index := 0; index < 5; index++ {
		result := <-results
		if result.code != http.StatusOK {
			t.Fatalf("collapsed response status = %d", result.code)
		}
		if exact == nil {
			exact = result.body
		} else if !bytes.Equal(exact, result.body) {
			t.Fatal("collapsed duplicate did not receive exact terminal bytes")
		}
	}
	if fixture.authority.callCount() != 1 || fixture.acpSigner.callCount() != 1 {
		t.Fatalf("collapse decision/sign calls = %d/%d", fixture.authority.callCount(), fixture.acpSigner.callCount())
	}
}

func TestSourceOperatorRuntimeBoundsSixteenConcurrentOperationsPerDeviceProfile(t *testing.T) {
	started := make(chan struct{}, 16)
	release := make(chan struct{})
	fixture := newSourceOperatorRuntimeFixture(t, filepath.Join(t.TempDir(), "idempotency.cbor"), func(ctx context.Context, request VerifiedACPRequest) (ACPDecision, error) {
		started <- struct{}{}
		select {
		case <-release:
			return testSuccessACPDecision(request), nil
		case <-ctx.Done():
			return ACPDecision{}, ctx.Err()
		}
	})

	responses := make(chan *httptest.ResponseRecorder, 16)
	for index := 0; index < 16; index++ {
		request := cloneACPRequest(fixture.request)
		request.RequestID[0] = byte(index + 1)
		request.RequestID[1] = 0xee
		signed, err := SignACPAcquireRequest(context.Background(), request, fixture.requestSigner, fixture.now.Load())
		if err != nil {
			t.Fatal(err)
		}
		go func(body []byte) { responses <- performRuntimeRequest(fixture.runtime, "/acp/authority", body, nil) }(signed.Body())
	}
	for index := 0; index < 16; index++ {
		<-started
	}
	seventeenthRequest := cloneACPRequest(fixture.request)
	seventeenthRequest.RequestID[0] = 17
	seventeenthRequest.RequestID[1] = 0xee
	seventeenth, err := SignACPAcquireRequest(context.Background(), seventeenthRequest, fixture.requestSigner, fixture.now.Load())
	if err != nil {
		t.Fatal(err)
	}
	overflow := performRuntimeRequest(fixture.runtime, "/acp/authority", seventeenth.Body(), nil)
	result := parseAndVerifyRuntimeACPResult(t, overflow.Body.Bytes(), fixture.acpSigner.public)
	if result.Status != ACPResultStatusResourceExhausted || fixture.authority.callCount() != 16 {
		t.Fatalf("17th result = %q, decisions=%d", result.Status, fixture.authority.callCount())
	}
	close(release)
	for index := 0; index < 16; index++ {
		if response := <-responses; response.Code != http.StatusOK {
			t.Fatalf("admitted response status = %d", response.Code)
		}
	}
}

func TestSourceOperatorRuntimeKeepsInfrastructureAndTransportErrorsUnsignedAndFenced(t *testing.T) {
	fixture := newSourceOperatorRuntimeFixture(t, filepath.Join(t.TempDir(), "idempotency.cbor"), func(context.Context, VerifiedACPRequest) (ACPDecision, error) {
		return ACPDecision{}, errors.New("authority database unavailable")
	})
	first := performRuntimeRequest(fixture.runtime, "/acp/authority", fixture.signed.Body(), nil)
	second := performRuntimeRequest(fixture.runtime, "/acp/authority", fixture.signed.Body(), nil)
	for _, response := range []*httptest.ResponseRecorder{first, second} {
		if response.Code != http.StatusServiceUnavailable || response.Header().Get("Content-Type") == "application/cose" {
			t.Fatalf("infrastructure result = %d %q", response.Code, response.Header().Get("Content-Type"))
		}
	}
	if fixture.authority.callCount() != 1 || fixture.acpSigner.callCount() != 0 {
		t.Fatalf("fenced failure decision/sign calls = %d/%d", fixture.authority.callCount(), fixture.acpSigner.callCount())
	}

	request := httptest.NewRequest(http.MethodPost, "https://source.operator/acp/authority", nil)
	request.Proto = "HTTP/2.0"
	request.ProtoMajor = 2
	request.TLS = &tls.ConnectionState{Version: tls.VersionTLS13, NegotiatedProtocol: "h2"}
	request.Header.Set("Content-Type", "application/cose")
	request.Body = io.NopCloser(failingReader{})
	recorder := httptest.NewRecorder()
	fixture.runtime.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusBadRequest || recorder.Header().Get("Content-Type") == "application/cose" {
		t.Fatalf("body transport error = %d %q", recorder.Code, recorder.Header().Get("Content-Type"))
	}
}

func TestSourceOperatorRuntimePinsServerTLSAndRefusesExtraEndpointsOrReplicaMisconfiguration(t *testing.T) {
	fixture := newSourceOperatorRuntimeFixture(t, filepath.Join(t.TempDir(), "idempotency.cbor"), nil)
	server, err := NewSourceOperatorHTTPServer("127.0.0.1:0", fixture.runtime, &tls.Config{Certificates: []tls.Certificate{{}}})
	if err != nil {
		t.Fatal(err)
	}
	if server.TLSConfig.MinVersion != tls.VersionTLS13 || server.TLSConfig.MaxVersion != tls.VersionTLS13 ||
		len(server.TLSConfig.NextProtos) != 1 || server.TLSConfig.NextProtos[0] != "h2" {
		t.Fatalf("server TLS profile = min %x max %x ALPN %v", server.TLSConfig.MinVersion, server.TLSConfig.MaxVersion, server.TLSConfig.NextProtos)
	}

	for _, path := range []string{"/", "/health", "/acp/authority/", "/acp/enroll/"} {
		response := performRuntimeRequest(fixture.runtime, path, fixture.signed.Body(), nil)
		if response.Code != http.StatusNotFound {
			t.Fatalf("extra endpoint %q status = %d", path, response.Code)
		}
	}
	http1 := performRuntimeRequest(fixture.runtime, "/acp/authority", fixture.signed.Body(), func(request *http.Request) {
		request.Proto = "HTTP/1.1"
		request.ProtoMajor = 1
	})
	if http1.Code != http.StatusUpgradeRequired || http1.Header().Get("Content-Type") == "application/cose" {
		t.Fatalf("HTTP/1.1 response = %d %q", http1.Code, http1.Header().Get("Content-Type"))
	}
	query := performRuntimeRequest(fixture.runtime, "/acp/authority?profile=x", fixture.signed.Body(), nil)
	if query.Code != http.StatusBadRequest {
		t.Fatalf("security query response = %d", query.Code)
	}

	store := newTestFileIdempotencyStore(t, filepath.Join(t.TempDir(), "multi.cbor"), 8, 2<<20)
	config := fixture.config(store)
	config.ReplicaCount = 2
	if _, err := NewSourceOperatorRuntime(config); !errors.Is(err, ErrInvalidLimits) {
		t.Fatalf("multi-replica local-store error = %v, want ErrInvalidLimits", err)
	}
	config.ReplicaCount = 1
	config.ACPResultSigner = fixture.enrollmentSigner
	if _, err := NewSourceOperatorRuntime(config); !errors.Is(err, ErrInvalidKeyPurpose) {
		t.Fatalf("cross-purpose signer error = %v, want ErrInvalidKeyPurpose", err)
	}
}

type sourceOperatorRuntimeFixture struct {
	t                *testing.T
	now              atomic.Uint64
	request          AcquireRequest
	signed           SignedACPRequest
	requestSigner    identity.Signer
	requestKey       DeviceACPRequestKey
	resolver         ACPRequestKeyResolver
	acpSigner        *recordingOperatorSigner
	enrollmentSigner *recordingOperatorSigner
	authority        *testAuthorityService
	bootstrap        *testBootstrapAuthorizer
	enrollment       *testEnrollmentService
	store            *FileIdempotencyStore
	runtime          *SourceOperatorRuntime
}

func newSourceOperatorRuntimeFixture(t *testing.T, path string, decide func(context.Context, VerifiedACPRequest) (ACPDecision, error)) *sourceOperatorRuntimeFixture {
	t.Helper()
	fixture := &sourceOperatorRuntimeFixture{t: t}
	fixture.now.Store(acpTestNow)
	fixture.requestSigner, fixture.requestKey.PublicKey, fixture.requestKey.KID = mustEnrollmentSigner(t, identity.PurposeDeviceACPRequest, 0x91, 4)
	fixture.request = validACPRequest(fixture.requestSigner.KeyRef())
	fixture.request.DeadlineUnix = fixture.now.Load() + 30
	var err error
	fixture.signed, err = SignACPAcquireRequest(context.Background(), fixture.request, fixture.requestSigner, fixture.now.Load())
	if err != nil {
		t.Fatal(err)
	}
	fixture.requestKey.Purpose = identity.PurposeDeviceACPRequest
	fixture.requestKey.KeyGeneration = fixture.requestSigner.KeyRef().Generation
	fixture.requestKey.DeviceID = fixture.request.Device.ID
	fixture.requestKey.CredentialGeneration = fixture.request.Device.CredentialGeneration
	fixture.requestKey.CredentialNotBefore = fixture.request.Device.CredentialNotBefore
	fixture.requestKey.CredentialExpiresAt = fixture.request.Device.CredentialExpiresAt
	fixture.requestKey.SourceOperator = fixture.request.Key.SourceOperator
	fixture.requestKey.Thumbprint = fixture.requestSigner.KeyRef().Thumbprint
	fixture.requestKey.NotBefore = fixture.now.Load() - 1
	fixture.requestKey.ExpiresAt = fixture.now.Load() + 600
	fixture.resolver = deviceACPRequestKeyResolverFunc(func(_ context.Context, kid []byte, _ uint64) (DeviceACPRequestKey, error) {
		if !bytes.Equal(kid, fixture.requestKey.KID[:]) {
			return DeviceACPRequestKey{}, ErrUnknownIdentity
		}
		return fixture.requestKey, nil
	})
	fixture.acpSigner = newRecordingOperatorSigner(t, 15, 0x92)
	fixture.enrollmentSigner = newRecordingOperatorSigner(t, 16, 0x93)
	fixture.authority = &testAuthorityService{generation: fixture.request.Key.AuthorityGeneration, decide: decide}
	fixture.bootstrap = &testBootstrapAuthorizer{authorized: BootstrapAuthorization{Subject: "bootstrap-subject"}}
	fixture.enrollment = &testEnrollmentService{}
	fixture.store = newTestFileIdempotencyStore(t, path, 128, 64<<20)
	fixture.runtime, err = NewSourceOperatorRuntime(fixture.config(fixture.store))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = fixture.runtime.Close() })
	return fixture
}

func (fixture *sourceOperatorRuntimeFixture) config(store TransactionalIdempotencyStore) SourceOperatorRuntimeConfig {
	return SourceOperatorRuntimeConfig{
		SourceOperator: fixture.request.Key.SourceOperator, Profile: fixture.request.Key.Profile, ReplicaCount: 1,
		RequestKeys: fixture.resolver, Authority: fixture.authority, Bootstrap: fixture.bootstrap,
		Enrollment: fixture.enrollment, ACPResultSigner: fixture.acpSigner,
		EnrollmentResultSigner: fixture.enrollmentSigner, Idempotency: store,
		NowUnix: func() uint64 { return fixture.now.Load() },
	}
}

func (fixture *sourceOperatorRuntimeFixture) runtimeWithResolver(t *testing.T, resolver ACPRequestKeyResolver) *SourceOperatorRuntime {
	t.Helper()
	store := newTestFileIdempotencyStore(t, filepath.Join(t.TempDir(), "idempotency.cbor"), 32, 8<<20)
	config := fixture.config(store)
	config.RequestKeys = resolver
	runtime, err := NewSourceOperatorRuntime(config)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = runtime.Close() })
	return runtime
}

func (fixture *sourceOperatorRuntimeFixture) reopen(t *testing.T, path string) *SourceOperatorRuntime {
	t.Helper()
	store := newTestFileIdempotencyStore(t, path, 128, 64<<20)
	config := fixture.config(store)
	runtime, err := NewSourceOperatorRuntime(config)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = runtime.Close() })
	return runtime
}

func (fixture *sourceOperatorRuntimeFixture) enrollmentRequest() EnrollmentRequestPayload {
	ref := fixture.requestSigner.KeyRef()
	return EnrollmentRequestPayload{
		ProtocolVersion: 1, RequestID: RequestID{4, 3, 2, 1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12},
		DeadlineUnix: fixture.now.Load() + 30, SourceOperator: fixture.request.Key.SourceOperator, Profile: fixture.request.Key.Profile,
		DeviceSigningKey: EnrollmentDeviceSigningKey{
			PublicKey: fixture.requestKey.PublicKey, KeyID: ref.ID, Purpose: ref.Purpose,
			Generation: ref.Generation, Thumbprint: ref.Thumbprint,
		},
	}
}

type deviceACPRequestKeyResolverFunc func(context.Context, []byte, uint64) (DeviceACPRequestKey, error)

func (function deviceACPRequestKeyResolverFunc) ResolveDeviceACPRequestKey(ctx context.Context, kid []byte, now uint64) (DeviceACPRequestKey, error) {
	return function(ctx, kid, now)
}

type recordingOperatorSigner struct {
	mu      sync.Mutex
	purpose uint16
	kid     []byte
	private ed25519.PrivateKey
	public  [32]byte
	calls   []uint16
	err     error
}

func newRecordingOperatorSigner(t *testing.T, purpose uint16, seedByte byte) *recordingOperatorSigner {
	t.Helper()
	private, public, kid := mustRawResultSigner(t, seedByte)
	return &recordingOperatorSigner{purpose: purpose, kid: kid, private: private, public: public}
}

func (signer *recordingOperatorSigner) KID() []byte     { return append([]byte(nil), signer.kid...) }
func (signer *recordingOperatorSigner) Purpose() uint16 { return signer.purpose }
func (signer *recordingOperatorSigner) Sign(ctx context.Context, message []byte) ([]byte, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	signer.mu.Lock()
	defer signer.mu.Unlock()
	if signer.err != nil {
		return nil, signer.err
	}
	signer.calls = append(signer.calls, signer.purpose)
	return ed25519.Sign(signer.private, message), nil
}
func (signer *recordingOperatorSigner) purposes() []uint16 {
	signer.mu.Lock()
	defer signer.mu.Unlock()
	return append([]uint16(nil), signer.calls...)
}
func (signer *recordingOperatorSigner) onlyPurpose(purpose uint16) bool {
	calls := signer.purposes()
	if len(calls) == 0 {
		return false
	}
	for _, got := range calls {
		if got != purpose {
			return false
		}
	}
	return true
}
func (signer *recordingOperatorSigner) callCount() int { return len(signer.purposes()) }

type testAuthorityService struct {
	mu         sync.Mutex
	generation AuthorityGeneration
	decide     func(context.Context, VerifiedACPRequest) (ACPDecision, error)
	calls      []ACPOperation
}

func (service *testAuthorityService) CurrentAuthorityGeneration(context.Context, string, string) (AuthorityGeneration, error) {
	return service.generation, nil
}
func (service *testAuthorityService) DecideAuthority(ctx context.Context, request VerifiedACPRequest) (ACPDecision, error) {
	service.mu.Lock()
	service.calls = append(service.calls, request.Operation())
	decide := service.decide
	service.mu.Unlock()
	if decide != nil {
		return decide(ctx, request)
	}
	return testSuccessACPDecision(request), nil
}
func (service *testAuthorityService) operations() []ACPOperation {
	service.mu.Lock()
	defer service.mu.Unlock()
	return append([]ACPOperation(nil), service.calls...)
}
func (service *testAuthorityService) callCount() int { return len(service.operations()) }

func testSuccessACPDecision(request VerifiedACPRequest) ACPDecision {
	generation := request.AuthorityGeneration()
	if request.Operation() == ACPOperationFreshness {
		generation++
	}
	return ACPDecision{Status: ACPResultStatusSuccess, AuthorityGeneration: generation, Artifact: []byte("artifact:" + request.Operation())}
}

type testBootstrapAuthorizer struct {
	calls      atomic.Int32
	authorized BootstrapAuthorization
	err        error
}

func (authorizer *testBootstrapAuthorizer) AuthorizeInitialEnrollment(context.Context, *http.Request) (BootstrapAuthorization, error) {
	authorizer.calls.Add(1)
	return authorizer.authorized, authorizer.err
}

type testEnrollmentService struct {
	calls    atomic.Int32
	decision EnrollmentDecision
	decide   func(context.Context, BootstrapAuthorization, VerifiedEnrollmentRequest) (EnrollmentDecision, error)
}

func (service *testEnrollmentService) DecideInitialEnrollment(ctx context.Context, authorization BootstrapAuthorization, request VerifiedEnrollmentRequest) (EnrollmentDecision, error) {
	service.calls.Add(1)
	if service.decide != nil {
		return service.decide(ctx, authorization, request)
	}
	if service.decision.Status != "" {
		return service.decision, nil
	}
	payload := request.Payload()
	device := identity.DeviceIdentity{
		ID: sha256.Sum256(payload.DeviceSigningKey.PublicKey[:]), SourceOperatorID: payload.SourceOperator,
		CredentialGeneration: payload.DeviceSigningKey.Generation, CredentialNotBefore: payload.DeadlineUnix - 1,
		CredentialExpiresAt: payload.DeadlineUnix + 600,
		SigningKey: identity.KeyRef{
			ID: payload.DeviceSigningKey.KeyID, Purpose: payload.DeviceSigningKey.Purpose,
			Generation: payload.DeviceSigningKey.Generation, Thumbprint: payload.DeviceSigningKey.Thumbprint,
		},
	}
	return EnrollmentDecision{Status: EnrollmentStatusAccepted, DeviceIdentity: &device}, nil
}

func performRuntimeRequest(runtime *SourceOperatorRuntime, path string, body []byte, mutate func(*http.Request)) *httptest.ResponseRecorder {
	request := httptest.NewRequest(http.MethodPost, "https://source.operator"+path, bytes.NewReader(body))
	request.Proto = "HTTP/2.0"
	request.ProtoMajor = 2
	request.TLS = &tls.ConnectionState{Version: tls.VersionTLS13, NegotiatedProtocol: "h2"}
	request.Header.Set("Content-Type", "application/cose")
	request.Header.Set("Accept", "application/cose")
	if mutate != nil {
		mutate(request)
	}
	response := httptest.NewRecorder()
	runtime.ServeHTTP(response, request)
	return response
}

func parseAndVerifyRuntimeACPResult(t *testing.T, wire []byte, public [32]byte) ACPResultPayload {
	t.Helper()
	sign1, err := parseRouteGrantSign1(wire)
	if err != nil {
		t.Fatal(err)
	}
	if err := sign1.verify(public); err != nil {
		t.Fatal(err)
	}
	value, err := decodeCBORExact(sign1.payload, defaultCBORLimits())
	if err != nil {
		t.Fatal(err)
	}
	result, err := decodeACPResultPayload(value)
	if err != nil {
		t.Fatal(err)
	}
	return result
}

func parseAndVerifyRuntimeEnrollmentResult(t *testing.T, wire []byte, public [32]byte) EnrollmentResultPayload {
	t.Helper()
	sign1, err := parseRouteGrantSign1(wire)
	if err != nil {
		t.Fatal(err)
	}
	if err := sign1.verify(public); err != nil {
		t.Fatal(err)
	}
	value, err := decodeCBORExact(sign1.payload, defaultCBORLimits())
	if err != nil {
		t.Fatal(err)
	}
	result, err := decodeEnrollmentResultPayload(value)
	if err != nil {
		t.Fatal(err)
	}
	return result
}

func mustDecodeMap(t *testing.T, wire []byte) map[uint64]any {
	t.Helper()
	value, err := decodeCBORExact(wire, defaultCBORLimits())
	if err != nil {
		t.Fatal(err)
	}
	fields, ok := value.(map[uint64]any)
	if !ok {
		t.Fatalf("decoded %T, want map", value)
	}
	return fields
}

func mustSignRawACPRequest(t *testing.T, fields map[uint64]any, signer identity.Signer) []byte {
	t.Helper()
	payload, err := encodeCBOR(fields)
	if err != nil {
		t.Fatal(err)
	}
	return mustSignPurposeBoundRequest(t, payload, signer)
}

func mustSignRawEnrollmentRequest(t *testing.T, fields map[uint64]any, signer identity.Signer) []byte {
	t.Helper()
	payload, err := encodeCBOR(fields)
	if err != nil {
		t.Fatal(err)
	}
	return mustSignPurposeBoundRequest(t, payload, signer)
}

func mustSignPurposeBoundRequest(t *testing.T, payload []byte, signer identity.Signer) []byte {
	t.Helper()
	ref := signer.KeyRef()
	protected := mustEncodeCBOR(map[uint64]any{1: int64(-8), 4: ref.ID[:]})
	structure, err := encodeCBOR([]any{"Signature1", protected, []byte{}, payload})
	if err != nil {
		t.Fatal(err)
	}
	signature, err := signer.SignPurposeBound(context.Background(), identity.PurposeDeviceACPRequest, structure)
	if err != nil {
		t.Fatal(err)
	}
	wire, err := buildSign1Envelope(protected, payload, signature)
	if err != nil {
		t.Fatal(err)
	}
	return wire
}

func equalOperations(left, right []ACPOperation) bool {
	if len(left) != len(right) {
		return false
	}
	for index := range left {
		if left[index] != right[index] {
			return false
		}
	}
	return true
}

func waitForRuntimeWaiters(t *testing.T, runtime *SourceOperatorRuntime, want int) {
	t.Helper()
	deadline := time.Now().Add(time.Second)
	for time.Now().Before(deadline) {
		runtime.mu.Lock()
		got := 0
		for _, pending := range runtime.pending {
			got += pending.waiters
		}
		runtime.mu.Unlock()
		if got == want {
			return
		}
		time.Sleep(time.Millisecond)
	}
	t.Fatalf("pending waiter count did not reach %d", want)
}

func runtimeEnrollmentResultResolver(request EnrollmentRequestPayload, purpose uint16, public [32]byte, kid []byte, now uint64) EnrollmentResultIssuerResolver {
	return enrollmentResultIssuerResolverFunc(func(context.Context, []byte, string, string, uint64) (IssuerRecord, error) {
		return IssuerRecord{
			KID: append([]byte(nil), kid...), PublicKey: public, Purpose: purpose,
			Profile: request.Profile, SourceOperator: request.SourceOperator,
			Generation: 1, NotBefore: now - 1, ExpiresAt: now + 600,
		}, nil
	})
}

type failingReader struct{}

func (failingReader) Read([]byte) (int, error) { return 0, errors.New("read failure") }
