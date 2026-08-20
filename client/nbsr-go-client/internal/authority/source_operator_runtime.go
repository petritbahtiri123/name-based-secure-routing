package authority

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/sha256"
	"crypto/tls"
	"errors"
	"io"
	"mime"
	"net/http"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"nbsr.local/client/nbsr-go-client/internal/identity"
)

const (
	maxSourceOperatorConcurrentPerActor = 16
	maxSourceOperatorDuplicateWaiters   = 4
	defaultSourceOperatorHeaderTimeout  = 5 * time.Second
	defaultSourceOperatorIdleTimeout    = 90 * time.Second
)

type OperatorResultSigner interface {
	KID() []byte
	Purpose() uint16
	Sign(context.Context, []byte) ([]byte, error)
}

type ACPDecision struct {
	Status              ACPResultStatus
	AuthorityGeneration AuthorityGeneration
	Artifact            []byte
}

type SourceOperatorAuthority interface {
	CurrentAuthorityGeneration(context.Context, string, string) (AuthorityGeneration, error)
	DecideAuthority(context.Context, VerifiedACPRequest) (ACPDecision, error)
}

type BootstrapAuthorization struct {
	Subject string
}

type BootstrapAuthorizer interface {
	AuthorizeInitialEnrollment(context.Context, *http.Request) (BootstrapAuthorization, error)
}

type VerifiedEnrollmentRequest struct {
	payload   EnrollmentRequestPayload
	canonical []byte
	digest    [32]byte
}

func (request VerifiedEnrollmentRequest) Payload() EnrollmentRequestPayload { return request.payload }
func (request VerifiedEnrollmentRequest) Canonical() []byte {
	return append([]byte(nil), request.canonical...)
}
func (request VerifiedEnrollmentRequest) Digest() [32]byte { return request.digest }

type EnrollmentDecision struct {
	Status         EnrollmentStatus
	DeviceIdentity *identity.DeviceIdentity
}

type InitialEnrollmentService interface {
	// DecideInitialEnrollment is the deployment's transactional initial-only
	// decision boundary. Existing-subject credential replacement must return
	// EnrollmentStatusRejected; no reenrollment operation exists here.
	DecideInitialEnrollment(context.Context, BootstrapAuthorization, VerifiedEnrollmentRequest) (EnrollmentDecision, error)
}

type SourceOperatorRuntimeConfig struct {
	SourceOperator         string
	Profile                string
	ReplicaCount           int
	RequestKeys            ACPRequestKeyResolver
	Authority              SourceOperatorAuthority
	Bootstrap              BootstrapAuthorizer
	Enrollment             InitialEnrollmentService
	ACPResultSigner        OperatorResultSigner
	EnrollmentResultSigner OperatorResultSigner
	Idempotency            TransactionalIdempotencyStore
	NowUnix                func() uint64
}

type sourceOperatorActorScope struct {
	deviceID   [32]byte
	generation uint64
	profile    string
}

type sourceOperatorPending struct {
	digest   [32]byte
	waiters  int
	done     chan struct{}
	terminal []byte
	err      error
}

type SourceOperatorRuntime struct {
	sourceOperator         string
	profile                string
	requestKeys            ACPRequestKeyResolver
	authority              SourceOperatorAuthority
	bootstrap              BootstrapAuthorizer
	enrollment             InitialEnrollmentService
	acpResultSigner        OperatorResultSigner
	enrollmentResultSigner OperatorResultSigner
	idempotency            TransactionalIdempotencyStore
	nowUnix                func() uint64

	mu      sync.Mutex
	pending map[IdempotencyKey]*sourceOperatorPending
	active  map[sourceOperatorActorScope]int
	closed  atomic.Bool
}

func NewSourceOperatorRuntime(config SourceOperatorRuntimeConfig) (*SourceOperatorRuntime, error) {
	if !validTextID(config.SourceOperator) || !validTextID(config.Profile) || config.ReplicaCount < 1 ||
		isNilDependency(config.RequestKeys) || isNilDependency(config.Authority) || isNilDependency(config.Bootstrap) ||
		isNilDependency(config.Enrollment) || isNilDependency(config.ACPResultSigner) ||
		isNilDependency(config.EnrollmentResultSigner) || isNilDependency(config.Idempotency) {
		return nil, ErrInvalidAuthority
	}
	if config.ReplicaCount > 1 && config.Idempotency.Scope() != IdempotencyStoreShared {
		return nil, ErrInvalidLimits
	}
	acpPurpose, err := ACPResultSigningPurpose()
	if err != nil || config.ACPResultSigner.Purpose() != acpPurpose ||
		!validOperatorResultSigner(config.ACPResultSigner) {
		return nil, ErrInvalidKeyPurpose
	}
	enrollmentPurpose, err := EnrollmentResultSigningPurpose()
	if err != nil || config.EnrollmentResultSigner.Purpose() != enrollmentPurpose ||
		!validOperatorResultSigner(config.EnrollmentResultSigner) {
		return nil, ErrInvalidKeyPurpose
	}
	nowUnix := config.NowUnix
	if nowUnix == nil {
		nowUnix = func() uint64 { return uint64(time.Now().Unix()) }
	}
	return &SourceOperatorRuntime{
		sourceOperator: config.SourceOperator, profile: config.Profile, requestKeys: config.RequestKeys,
		authority: config.Authority, bootstrap: config.Bootstrap, enrollment: config.Enrollment,
		acpResultSigner: config.ACPResultSigner, enrollmentResultSigner: config.EnrollmentResultSigner,
		idempotency: config.Idempotency, nowUnix: nowUnix,
		pending: make(map[IdempotencyKey]*sourceOperatorPending), active: make(map[sourceOperatorActorScope]int),
	}, nil
}

func validOperatorResultSigner(signer OperatorResultSigner) bool {
	kid := signer.KID()
	return len(kid) >= 1 && len(kid) <= 64
}

func NewSourceOperatorHTTPServer(address string, runtime *SourceOperatorRuntime, tlsConfig *tls.Config) (*http.Server, error) {
	if strings.TrimSpace(address) == "" || runtime == nil || tlsConfig == nil {
		return nil, ErrInvalidAuthority
	}
	secureTLS := tlsConfig.Clone()
	secureTLS.MinVersion = tls.VersionTLS13
	secureTLS.MaxVersion = tls.VersionTLS13
	secureTLS.NextProtos = []string{"h2"}
	return &http.Server{
		Addr: address, Handler: runtime, TLSConfig: secureTLS,
		ReadHeaderTimeout: defaultSourceOperatorHeaderTimeout, IdleTimeout: defaultSourceOperatorIdleTimeout,
		MaxHeaderBytes: 16 * 1024,
	}, nil
}

func (runtime *SourceOperatorRuntime) ServeHTTP(response http.ResponseWriter, request *http.Request) {
	if runtime == nil || response == nil || request == nil {
		return
	}
	if runtime.closed.Load() {
		writeUnsignedHTTPError(response, http.StatusServiceUnavailable)
		return
	}
	switch request.URL.Path {
	case "/acp/authority", "/acp/enroll":
	default:
		writeUnsignedHTTPError(response, http.StatusNotFound)
		return
	}
	if request.Method != http.MethodPost {
		response.Header().Set("Allow", http.MethodPost)
		writeUnsignedHTTPError(response, http.StatusMethodNotAllowed)
		return
	}
	if request.URL.RawQuery != "" {
		writeUnsignedHTTPError(response, http.StatusBadRequest)
		return
	}
	if request.ProtoMajor != 2 || request.TLS == nil || request.TLS.Version != tls.VersionTLS13 || request.TLS.NegotiatedProtocol != "h2" {
		writeUnsignedHTTPError(response, http.StatusUpgradeRequired)
		return
	}
	mediaType, _, err := mime.ParseMediaType(request.Header.Get("Content-Type"))
	if err != nil || mediaType != "application/cose" {
		writeUnsignedHTTPError(response, http.StatusUnsupportedMediaType)
		return
	}
	if request.URL.Path == "/acp/authority" {
		runtime.handleAuthority(response, request)
		return
	}
	runtime.handleEnrollment(response, request)
}

func (runtime *SourceOperatorRuntime) handleAuthority(response http.ResponseWriter, request *http.Request) {
	wire, err := readBoundedRequestBody(request, maxACPAcquireRequestBodySize)
	if err != nil {
		if errors.Is(err, errACPRequestBodyTooLarge) {
			writeUnsignedHTTPError(response, http.StatusRequestEntityTooLarge)
		} else {
			writeUnsignedHTTPError(response, http.StatusBadRequest)
		}
		return
	}
	now := runtime.nowUnix()
	if now == 0 {
		writeUnsignedHTTPError(response, http.StatusServiceUnavailable)
		return
	}
	envelope, err := authenticateACPEnvelope(request.Context(), wire, runtime.requestKeys, now)
	if err != nil {
		switch {
		case errors.Is(err, errACPRequestBodyTooLarge):
			writeUnsignedHTTPError(response, http.StatusRequestEntityTooLarge)
		case errors.Is(err, errACPRequestUnauthorized):
			writeUnsignedHTTPError(response, http.StatusUnauthorized)
		default:
			writeUnsignedHTTPError(response, http.StatusBadRequest)
		}
		return
	}
	verified, validationStatus := verifyAuthenticatedACPEnvelope(envelope, runtime.sourceOperator, runtime.profile, now)
	if validationStatus == ACPResultStatusRequestExpired {
		terminal, err := runtime.signAuthorityStatus(context.Background(), envelope, validationStatus)
		if err != nil {
			writeUnsignedHTTPError(response, http.StatusServiceUnavailable)
			return
		}
		writeSignedHTTPResult(response, terminal)
		return
	}
	requestState := IdempotencyRequest{
		Key: IdempotencyKey{
			Namespace: "authority", SourceOperator: envelope.sourceOperator, Profile: envelope.profile,
			ActorID: envelope.key.DeviceID, ActorGeneration: envelope.key.CredentialGeneration,
			Operation: string(envelope.operation), RequestID: envelope.requestID,
		},
		Digest: envelope.digest, DeadlineUnix: envelope.deadlineUnix, NowUnix: now,
		MaxTerminalBytes: uint64(acpResultBodyLimit(envelope.operation)),
	}
	claim, pending, err := runtime.beginIdempotent(request.Context(), requestState)
	if err != nil {
		runtime.writeIdempotencyAdmissionError(response, err)
		return
	}
	switch claim.Status {
	case IdempotencyReplay:
		writeSignedHTTPResult(response, claim.Terminal)
		return
	case IdempotencyConflict:
		terminal, err := runtime.signAuthorityStatus(context.Background(), envelope, ACPResultStatusRequestIDConflict)
		if err != nil {
			writeUnsignedHTTPError(response, http.StatusServiceUnavailable)
			return
		}
		writeSignedHTTPResult(response, terminal)
		return
	case IdempotencyPending:
		terminal, err := runtime.waitForPending(request.Context(), requestState.Key, pending)
		if err != nil {
			runtime.writeIdempotencyAdmissionError(response, err)
			return
		}
		writeSignedHTTPResult(response, terminal)
		return
	case IdempotencyOwner:
	default:
		writeUnsignedHTTPError(response, http.StatusServiceUnavailable)
		return
	}

	if validationStatus != "" {
		terminal, err := runtime.signAuthorityStatus(context.Background(), envelope, validationStatus)
		runtime.finishIdempotent(requestState, pending, terminal, err)
		if err != nil {
			writeUnsignedHTTPError(response, http.StatusServiceUnavailable)
			return
		}
		writeSignedHTTPResult(response, terminal)
		return
	}
	scope := sourceOperatorActorScope{deviceID: verified.DeviceID(), generation: verified.DeviceGeneration(), profile: verified.Profile()}
	if !runtime.tryAcquireActor(scope) {
		terminal, err := runtime.signAuthorityDecision(context.Background(), envelope, ACPDecision{
			Status: ACPResultStatusResourceExhausted, AuthorityGeneration: runtime.mustCurrentGeneration(context.Background()),
		})
		runtime.finishIdempotent(requestState, pending, terminal, err)
		if err != nil {
			writeUnsignedHTTPError(response, http.StatusServiceUnavailable)
			return
		}
		writeSignedHTTPResult(response, terminal)
		return
	}
	defer runtime.releaseActor(scope)
	evaluationContext, cancel := context.WithTimeout(context.Background(), time.Duration(envelope.deadlineUnix-now)*time.Second)
	decision, err := runtime.authority.DecideAuthority(evaluationContext, verified)
	cancel()
	completionNow := runtime.nowUnix()
	if completionNow == 0 {
		err = ErrProviderUnavailable
	} else if completionNow >= envelope.deadlineUnix {
		terminal, signErr := runtime.signAuthorityStatus(context.Background(), envelope, ACPResultStatusRequestExpired)
		runtime.finishIdempotent(requestState, pending, terminal, signErr)
		if signErr != nil {
			writeUnsignedHTTPError(response, http.StatusServiceUnavailable)
			return
		}
		writeSignedHTTPResult(response, terminal)
		return
	}
	if err == nil {
		err = validateACPDecision(decision, verified)
	}
	var terminal []byte
	if err == nil {
		terminal, err = runtime.signAuthorityDecision(context.Background(), envelope, decision)
	}
	runtime.finishIdempotent(requestState, pending, terminal, err)
	if err != nil {
		writeUnsignedHTTPError(response, http.StatusServiceUnavailable)
		return
	}
	writeSignedHTTPResult(response, terminal)
}

func (runtime *SourceOperatorRuntime) signAuthorityStatus(ctx context.Context, envelope authenticatedACPEnvelope, status ACPResultStatus) ([]byte, error) {
	generation, err := runtime.authority.CurrentAuthorityGeneration(ctx, runtime.sourceOperator, runtime.profile)
	if err != nil || generation == 0 || generation == ^AuthorityGeneration(0) {
		return nil, ErrProviderUnavailable
	}
	return runtime.signAuthorityDecision(ctx, envelope, ACPDecision{Status: status, AuthorityGeneration: generation})
}

func (runtime *SourceOperatorRuntime) mustCurrentGeneration(ctx context.Context) AuthorityGeneration {
	generation, err := runtime.authority.CurrentAuthorityGeneration(ctx, runtime.sourceOperator, runtime.profile)
	if err != nil || generation == 0 || generation == ^AuthorityGeneration(0) {
		return 0
	}
	return generation
}

func validateACPDecision(decision ACPDecision, request VerifiedACPRequest) error {
	result := ACPResultPayload{
		ProtocolVersion: acpProtocolVersion, Operation: request.Operation(), RequestID: request.RequestID(),
		RequestDigest: request.Digest(), SourceOperator: request.SourceOperator(), Profile: request.Profile(),
		AuthorityGeneration: decision.AuthorityGeneration, Status: decision.Status, Artifact: decision.Artifact,
	}
	if err := validateACPResultPayload(result); err != nil {
		return err
	}
	if decision.Status == ACPResultStatusSuccess && request.Operation() != ACPOperationFreshness &&
		decision.AuthorityGeneration != request.AuthorityGeneration() {
		return ErrStaleGeneration
	}
	return nil
}

func (runtime *SourceOperatorRuntime) signAuthorityDecision(ctx context.Context, envelope authenticatedACPEnvelope, decision ACPDecision) ([]byte, error) {
	result := ACPResultPayload{
		ProtocolVersion: acpProtocolVersion, Operation: envelope.operation, RequestID: envelope.requestID,
		RequestDigest: envelope.digest, SourceOperator: envelope.sourceOperator, Profile: envelope.profile,
		AuthorityGeneration: decision.AuthorityGeneration, Status: decision.Status,
		Artifact: append([]byte(nil), decision.Artifact...),
	}
	payload, err := EncodeACPResultPayload(result)
	if err != nil {
		return nil, err
	}
	wire, err := signOperatorResult(ctx, payload, runtime.acpResultSigner, acpResultSigningPurpose)
	if err != nil || len(wire) > acpResultBodyLimit(envelope.operation) {
		return nil, ErrInvalidAuthority
	}
	return wire, nil
}

func (runtime *SourceOperatorRuntime) handleEnrollment(response http.ResponseWriter, request *http.Request) {
	authorization, err := runtime.bootstrap.AuthorizeInitialEnrollment(request.Context(), request)
	if err != nil {
		if errors.Is(err, ErrBootstrapUnauthorized) {
			writeUnsignedHTTPError(response, http.StatusForbidden)
		} else {
			writeUnsignedHTTPError(response, http.StatusServiceUnavailable)
		}
		return
	}
	if !validTextID(authorization.Subject) {
		writeUnsignedHTTPError(response, http.StatusForbidden)
		return
	}
	wire, err := readBoundedRequestBody(request, maxEnrollmentRequestBodySize)
	if err != nil {
		if errors.Is(err, errACPRequestBodyTooLarge) {
			writeUnsignedHTTPError(response, http.StatusRequestEntityTooLarge)
		} else {
			writeUnsignedHTTPError(response, http.StatusBadRequest)
		}
		return
	}
	now := runtime.nowUnix()
	if now == 0 {
		writeUnsignedHTTPError(response, http.StatusServiceUnavailable)
		return
	}
	verified, status, authErr := authenticateEnrollmentForServer(wire, runtime.sourceOperator, runtime.profile, now)
	if authErr != nil {
		if errors.Is(authErr, errACPRequestUnauthorized) {
			writeUnsignedHTTPError(response, http.StatusUnauthorized)
		} else {
			writeUnsignedHTTPError(response, http.StatusBadRequest)
		}
		return
	}
	if status == EnrollmentStatusExpired {
		terminal, err := runtime.signEnrollmentDecision(context.Background(), verified, EnrollmentDecision{Status: status})
		if err != nil {
			writeUnsignedHTTPError(response, http.StatusServiceUnavailable)
			return
		}
		writeSignedHTTPResult(response, terminal)
		return
	}
	payload := verified.Payload()
	requestState := IdempotencyRequest{
		Key: IdempotencyKey{
			Namespace: "enrollment", SourceOperator: payload.SourceOperator, Profile: payload.Profile,
			ActorID: enrollmentIdempotencyActor(authorization.Subject), ActorGeneration: 1,
			Operation: "ENROLL", RequestID: payload.RequestID,
		},
		Digest: verified.Digest(), DeadlineUnix: payload.DeadlineUnix, NowUnix: now,
		MaxTerminalBytes: maxEnrollmentResultBodySize,
	}
	claim, pending, err := runtime.beginIdempotent(request.Context(), requestState)
	if err != nil {
		runtime.writeIdempotencyAdmissionError(response, err)
		return
	}
	switch claim.Status {
	case IdempotencyReplay:
		writeSignedHTTPResult(response, claim.Terminal)
		return
	case IdempotencyConflict:
		terminal, err := runtime.signEnrollmentDecision(context.Background(), verified, EnrollmentDecision{Status: EnrollmentStatusRequestConflict})
		if err != nil {
			writeUnsignedHTTPError(response, http.StatusServiceUnavailable)
			return
		}
		writeSignedHTTPResult(response, terminal)
		return
	case IdempotencyPending:
		terminal, err := runtime.waitForPending(request.Context(), requestState.Key, pending)
		if err != nil {
			runtime.writeIdempotencyAdmissionError(response, err)
			return
		}
		writeSignedHTTPResult(response, terminal)
		return
	case IdempotencyOwner:
	default:
		writeUnsignedHTTPError(response, http.StatusServiceUnavailable)
		return
	}
	evaluationContext, cancel := context.WithTimeout(context.Background(), time.Duration(payload.DeadlineUnix-now)*time.Second)
	decision, err := runtime.enrollment.DecideInitialEnrollment(evaluationContext, authorization, verified)
	cancel()
	completionNow := runtime.nowUnix()
	if completionNow == 0 {
		err = ErrProviderUnavailable
	} else if completionNow >= payload.DeadlineUnix {
		decision = EnrollmentDecision{Status: EnrollmentStatusExpired}
		err = nil
	}
	if err == nil {
		err = validateEnrollmentDecision(decision)
	}
	var terminal []byte
	if err == nil {
		terminal, err = runtime.signEnrollmentDecision(context.Background(), verified, decision)
	}
	runtime.finishIdempotent(requestState, pending, terminal, err)
	if err != nil {
		writeUnsignedHTTPError(response, http.StatusServiceUnavailable)
		return
	}
	writeSignedHTTPResult(response, terminal)
}

func enrollmentIdempotencyActor(subject string) [32]byte {
	payload := make([]byte, 0, len("NBSR-ENROLL-IDEMPOTENCY-ACTOR-v1\x00")+len(subject))
	payload = append(payload, "NBSR-ENROLL-IDEMPOTENCY-ACTOR-v1\x00"...)
	payload = append(payload, subject...)
	return sha256.Sum256(payload)
}

func authenticateEnrollmentForServer(wire []byte, sourceOperator, profile string, now uint64) (VerifiedEnrollmentRequest, EnrollmentStatus, error) {
	request, canonical, sign1, err := parseEnrollmentRequestEnvelope(wire)
	if err != nil || !bytes.Equal(canonical, sign1.payload) {
		return VerifiedEnrollmentRequest{}, "", errACPRequestMalformed
	}
	if request.SourceOperator != sourceOperator || request.Profile != profile {
		return VerifiedEnrollmentRequest{}, "", errACPRequestMalformed
	}
	if !sameKID(sign1.kid, request.DeviceSigningKey.KeyID[:]) || sha256.Sum256(request.DeviceSigningKey.PublicKey[:]) != request.DeviceSigningKey.Thumbprint {
		return VerifiedEnrollmentRequest{}, "", errACPRequestUnauthorized
	}
	structure, err := encodeEnrollmentRequestSigStructure(sign1.protected, sign1.payload)
	if err != nil || !ed25519.Verify(ed25519.PublicKey(request.DeviceSigningKey.PublicKey[:]), appendEnrollmentRequestSignaturePayload(structure), sign1.signature) {
		return VerifiedEnrollmentRequest{}, "", errACPRequestUnauthorized
	}
	verified := VerifiedEnrollmentRequest{payload: request, canonical: append([]byte(nil), canonical...), digest: EnrollmentRequestDigest(canonical)}
	if now >= request.DeadlineUnix {
		return verified, EnrollmentStatusExpired, nil
	}
	if request.DeadlineUnix-now > maxEnrollmentRequestDeadlineWindow {
		return VerifiedEnrollmentRequest{}, "", errACPRequestMalformed
	}
	return verified, "", nil
}

func validateEnrollmentDecision(decision EnrollmentDecision) error {
	result := EnrollmentResultPayload{
		ProtocolVersion: enrollmentProtocolVersion, RequestID: RequestID{1}, RequestDigest: [32]byte{1},
		Status: decision.Status, DeviceIdentity: decision.DeviceIdentity,
	}
	return validateEnrollmentResultPayload(result)
}

func (runtime *SourceOperatorRuntime) signEnrollmentDecision(ctx context.Context, request VerifiedEnrollmentRequest, decision EnrollmentDecision) ([]byte, error) {
	payload := request.Payload()
	result := EnrollmentResultPayload{
		ProtocolVersion: enrollmentProtocolVersion, RequestID: payload.RequestID, RequestDigest: request.Digest(),
		Status: decision.Status, DeviceIdentity: decision.DeviceIdentity,
	}
	canonical, err := EncodeEnrollmentResultPayload(result)
	if err != nil {
		return nil, err
	}
	purpose, err := EnrollmentResultSigningPurpose()
	if err != nil {
		return nil, err
	}
	wire, err := signOperatorResult(ctx, canonical, runtime.enrollmentResultSigner, purpose)
	if err != nil || len(wire) > maxEnrollmentResultBodySize {
		return nil, ErrInvalidAuthority
	}
	return wire, nil
}

func signOperatorResult(ctx context.Context, payload []byte, signer OperatorResultSigner, expectedPurpose uint16) ([]byte, error) {
	if ctx == nil || isNilDependency(signer) || signer.Purpose() != expectedPurpose {
		return nil, ErrInvalidKeyPurpose
	}
	kid := signer.KID()
	if len(kid) < 1 || len(kid) > 64 {
		return nil, ErrInvalidAuthority
	}
	protected, err := encodeCBOR(map[uint64]any{1: int64(-8), 4: kid})
	if err != nil {
		return nil, err
	}
	structure, err := encodeCBOR([]any{"Signature1", protected, []byte{}, payload})
	if err != nil {
		return nil, err
	}
	signature, err := signer.Sign(ctx, structure)
	if err != nil {
		return nil, err
	}
	if len(signature) != ed25519.SignatureSize {
		return nil, ErrSignatureFailure
	}
	return buildSign1Envelope(protected, payload, signature)
}

func (runtime *SourceOperatorRuntime) beginIdempotent(ctx context.Context, request IdempotencyRequest) (IdempotencyClaim, *sourceOperatorPending, error) {
	runtime.mu.Lock()
	if runtime.closed.Load() {
		runtime.mu.Unlock()
		return IdempotencyClaim{}, nil, ErrClosed
	}
	if pending, ok := runtime.pending[request.Key]; ok {
		if pending.digest != request.Digest {
			runtime.mu.Unlock()
			return IdempotencyClaim{Status: IdempotencyConflict}, nil, nil
		}
		if pending.waiters >= maxSourceOperatorDuplicateWaiters {
			runtime.mu.Unlock()
			return IdempotencyClaim{}, nil, ErrWaiterCapacity
		}
		pending.waiters++
		runtime.mu.Unlock()
		return IdempotencyClaim{Status: IdempotencyPending}, pending, nil
	}
	claim, err := runtime.idempotency.Begin(ctx, request)
	if err != nil {
		runtime.mu.Unlock()
		return IdempotencyClaim{}, nil, err
	}
	if claim.Status == IdempotencyPending {
		runtime.mu.Unlock()
		return claim, nil, ErrRequestAmbiguous
	}
	if claim.Status != IdempotencyOwner {
		runtime.mu.Unlock()
		return claim, nil, nil
	}
	pending := &sourceOperatorPending{digest: request.Digest, done: make(chan struct{})}
	runtime.pending[request.Key] = pending
	runtime.mu.Unlock()
	return claim, pending, nil
}

func (runtime *SourceOperatorRuntime) waitForPending(ctx context.Context, key IdempotencyKey, pending *sourceOperatorPending) ([]byte, error) {
	if pending == nil {
		return nil, ErrRequestAmbiguous
	}
	select {
	case <-pending.done:
		runtime.mu.Lock()
		terminal := append([]byte(nil), pending.terminal...)
		err := pending.err
		runtime.mu.Unlock()
		return terminal, err
	case <-ctx.Done():
		runtime.mu.Lock()
		if current, ok := runtime.pending[key]; ok && current == pending && pending.waiters > 0 {
			pending.waiters--
		}
		runtime.mu.Unlock()
		return nil, ctx.Err()
	}
}

func (runtime *SourceOperatorRuntime) finishIdempotent(request IdempotencyRequest, pending *sourceOperatorPending, terminal []byte, resultErr error) {
	if resultErr == nil {
		completionContext, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		resultErr = runtime.idempotency.Complete(completionContext, request.Key, request.Digest, terminal)
		cancel()
	}
	runtime.mu.Lock()
	if current, ok := runtime.pending[request.Key]; ok && current == pending {
		pending.terminal = append([]byte(nil), terminal...)
		pending.err = resultErr
		delete(runtime.pending, request.Key)
		close(pending.done)
	}
	runtime.mu.Unlock()
}

func (runtime *SourceOperatorRuntime) tryAcquireActor(scope sourceOperatorActorScope) bool {
	runtime.mu.Lock()
	defer runtime.mu.Unlock()
	if runtime.active[scope] >= maxSourceOperatorConcurrentPerActor {
		return false
	}
	runtime.active[scope]++
	return true
}

func (runtime *SourceOperatorRuntime) releaseActor(scope sourceOperatorActorScope) {
	runtime.mu.Lock()
	defer runtime.mu.Unlock()
	if runtime.active[scope] <= 1 {
		delete(runtime.active, scope)
		return
	}
	runtime.active[scope]--
}

func (runtime *SourceOperatorRuntime) writeIdempotencyAdmissionError(response http.ResponseWriter, err error) {
	if errors.Is(err, ErrWaiterCapacity) {
		writeUnsignedHTTPError(response, http.StatusTooManyRequests)
		return
	}
	writeUnsignedHTTPError(response, http.StatusServiceUnavailable)
}

func (runtime *SourceOperatorRuntime) Close() error {
	if runtime == nil {
		return nil
	}
	if !runtime.closed.CompareAndSwap(false, true) {
		return nil
	}
	return runtime.idempotency.Close()
}

func readBoundedRequestBody(request *http.Request, maximum int) ([]byte, error) {
	if request == nil || request.Body == nil || maximum <= 0 {
		return nil, errACPRequestMalformed
	}
	if request.ContentLength > int64(maximum) {
		return nil, errACPRequestBodyTooLarge
	}
	wire, err := io.ReadAll(io.LimitReader(request.Body, int64(maximum)+1))
	if err != nil {
		return nil, errACPRequestMalformed
	}
	if len(wire) == 0 {
		return nil, errACPRequestMalformed
	}
	if len(wire) > maximum {
		return nil, errACPRequestBodyTooLarge
	}
	return wire, nil
}

func writeUnsignedHTTPError(response http.ResponseWriter, status int) {
	response.Header().Set("Cache-Control", "no-store")
	http.Error(response, http.StatusText(status), status)
}

func writeSignedHTTPResult(response http.ResponseWriter, wire []byte) {
	response.Header().Set("Content-Type", "application/cose")
	response.Header().Set("Cache-Control", "no-store")
	response.Header().Set("Content-Length", stringLength(len(wire)))
	response.WriteHeader(http.StatusOK)
	_, _ = response.Write(wire)
}

func stringLength(value int) string {
	if value == 0 {
		return "0"
	}
	var buffer [20]byte
	index := len(buffer)
	for value > 0 {
		index--
		buffer[index] = byte('0' + value%10)
		value /= 10
	}
	return string(buffer[index:])
}

var _ http.Handler = (*SourceOperatorRuntime)(nil)
