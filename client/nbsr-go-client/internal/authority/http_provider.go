package authority

import (
	"bytes"
	"context"
	"crypto/tls"
	"crypto/x509"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"sync/atomic"
	"time"

	"nbsr.local/client/nbsr-go-client/internal/identity"
)

const (
	defaultHTTPMaxAttempts   = 2
	defaultHTTPMaxConcurrent = 16
	maximumHTTPMaxAttempts   = 3
	maximumHTTPConcurrent    = 16
	defaultAttemptTimeout    = 5 * time.Second
	defaultRetryBackoff      = 25 * time.Millisecond
)

var (
	errHTTP2Required = errors.New("authority transport requires negotiated HTTP/2")
	errRedirect      = errors.New("authority transport refuses redirects")
)

// HTTPProviderOptions bound transport resource use. Zero values select the
// production defaults; non-zero values are primarily useful for deployment
// tuning and deterministic timeout tests.
type HTTPProviderOptions struct {
	MaxAttempts    int
	MaxConcurrent  int
	RetryBackoff   time.Duration
	AttemptTimeout time.Duration
}

// HTTPProviderConfig binds one reusable connection pool to exactly one
// enrolled Source Operator endpoint and ACP profile.
type HTTPProviderConfig struct {
	Endpoint       string
	TLSConfig      *tls.Config
	SourceOperator string
	Profile        string
	Signer         identity.Signer
	ResultIssuers  ACPResultIssuerResolver
	RequestIDs     RequestIDSource
	Options        HTTPProviderOptions
	NowUnix        func() uint64
}

// HTTPProvider transports signed ACP requests and authenticates only the
// outer ACP result. Returned artifact bytes remain candidates for the existing
// independent RouteGrant or freshness verifier.
type HTTPProvider struct {
	http           *boundedHTTP2Client
	sourceOperator string
	profile        string
	signer         identity.Signer
	issuers        ACPResultIssuerResolver
	requestIDs     RequestIDSource
	nowUnix        func() uint64
}

func NewHTTPProvider(config HTTPProviderConfig) (*HTTPProvider, error) {
	if !validTextID(config.SourceOperator) || !validTextID(config.Profile) || isNilDependency(config.Signer) ||
		isNilDependency(config.ResultIssuers) || isNilDependency(config.RequestIDs) {
		return nil, ErrInvalidAuthority
	}
	if config.Signer.KeyRef().Purpose != identity.PurposeDeviceACPRequest {
		return nil, ErrInvalidKeyPurpose
	}
	client, err := newBoundedHTTP2Client(config.Endpoint, config.TLSConfig, config.Options)
	if err != nil {
		return nil, err
	}
	nowUnix := config.NowUnix
	if nowUnix == nil {
		nowUnix = func() uint64 { return uint64(time.Now().Unix()) }
	}
	return &HTTPProvider{http: client, sourceOperator: config.SourceOperator, profile: config.Profile, signer: config.Signer, issuers: config.ResultIssuers, requestIDs: config.RequestIDs, nowUnix: nowUnix}, nil
}

func (provider *HTTPProvider) Acquire(ctx context.Context, request AcquireRequest) (ProviderGrant, error) {
	if provider == nil || ctx == nil || request.Key.SourceOperator != provider.sourceOperator || request.Key.Profile != provider.profile {
		return ProviderGrant{}, ErrBindingMismatch
	}
	signed, err := SignACPAcquireRequest(ctx, request, provider.signer, provider.nowUnix())
	if err != nil {
		return ProviderGrant{}, err
	}
	return provider.grant(ctx, signed)
}

func (provider *HTTPProvider) Renew(ctx context.Context, request RenewRequest) (ProviderGrant, error) {
	if provider == nil || ctx == nil || request.Key.SourceOperator != provider.sourceOperator || request.Key.Profile != provider.profile {
		return ProviderGrant{}, ErrBindingMismatch
	}
	signed, err := SignACPRenewRequest(ctx, request, provider.signer, provider.nowUnix())
	if err != nil {
		return ProviderGrant{}, err
	}
	return provider.grant(ctx, signed)
}

func (provider *HTTPProvider) Freshness(ctx context.Context, request FreshnessRequest) (ProviderFreshness, error) {
	if provider == nil || ctx == nil || request.SourceOperator != provider.sourceOperator || request.Profile != provider.profile {
		return ProviderFreshness{}, ErrBindingMismatch
	}
	requestID, err := provider.requestIDs.NewRequestID()
	if err != nil {
		return ProviderFreshness{}, err
	}
	signed, err := SignACPFreshnessRequest(ctx, request, requestID, provider.signer, provider.nowUnix())
	if err != nil {
		return ProviderFreshness{}, err
	}
	verified, err := provider.invoke(ctx, signed)
	if err != nil {
		return ProviderFreshness{}, err
	}
	if verified.Status() != ACPResultStatusSuccess {
		return ProviderFreshness{}, acpSemanticError(verified.Status())
	}
	return ProviderFreshness{SourceOperator: provider.sourceOperator, Profile: provider.profile, Evidence: verified.Artifact()}, nil
}

func (provider *HTTPProvider) Close() error {
	if provider == nil || provider.http == nil {
		return ErrInvalidAuthority
	}
	return provider.http.Close()
}

func (provider *HTTPProvider) grant(ctx context.Context, signed SignedACPRequest) (ProviderGrant, error) {
	verified, err := provider.invoke(ctx, signed)
	if err != nil {
		return ProviderGrant{}, err
	}
	if verified.Status() != ACPResultStatusSuccess {
		return ProviderGrant{}, acpSemanticError(verified.Status())
	}
	return ProviderGrant{ExactRouteGrant: verified.Artifact(), Profile: provider.profile, AuthorityGeneration: verified.AuthorityGeneration()}, nil
}

func (provider *HTTPProvider) invoke(ctx context.Context, signed SignedACPRequest) (VerifiedACPResult, error) {
	wire, err := provider.http.Post(ctx, "/acp/authority", signed.Body(), acpResultBodyLimit(signed.Operation()), signed.DeadlineUnix(), provider.nowUnix)
	if err != nil {
		return VerifiedACPResult{}, err
	}
	return ParseVerifiedACPResult(ctx, wire, signed, provider.issuers, provider.nowUnix())
}

// VerifiedACPSemanticError is emitted only after the outer ACP result has
// passed canonical parsing, issuer/purpose/signature validation, and exact
// request binding. Its concrete type preserves signed semantic provenance;
// Unwrap retains compatibility with existing local policy categories.
type VerifiedACPSemanticError struct {
	status ACPResultStatus
	cause  error
}

func (semantic *VerifiedACPSemanticError) Error() string {
	if semantic == nil {
		return "<nil>"
	}
	return fmt.Sprintf("verified ACP semantic result: %s", semantic.status)
}

func (semantic *VerifiedACPSemanticError) Unwrap() error {
	if semantic == nil {
		return nil
	}
	return semantic.cause
}

func (semantic *VerifiedACPSemanticError) Status() ACPResultStatus {
	if semantic == nil {
		return ""
	}
	return semantic.status
}

func (semantic *VerifiedACPSemanticError) Verified() bool {
	return semantic != nil && semantic.cause != nil && semantic.status != ACPResultStatusSuccess && validACPResultStatus(semantic.status)
}

func acpSemanticError(status ACPResultStatus) error {
	var cause error
	switch status {
	case ACPResultStatusPolicyDenied:
		cause = ErrPolicyDenied
	case ACPResultStatusRevoked:
		cause = ErrRevoked
	case ACPResultStatusStaleFreshness:
		cause = ErrStaleFreshness
	case ACPResultStatusStaleGeneration:
		cause = ErrStaleGeneration
	case ACPResultStatusRequestIDConflict:
		cause = ErrRequestConflict
	case ACPResultStatusRequestExpired:
		cause = ErrExpired
	case ACPResultStatusResourceExhausted:
		cause = ErrPendingCapacity
	case ACPResultStatusInternalError:
		cause = ErrProviderUnavailable
	case ACPResultStatusBindingError:
		cause = ErrBindingMismatch
	case ACPResultStatusSignatureError:
		cause = ErrSignatureFailure
	case ACPResultStatusInvalidRequest, ACPResultStatusUnsupportedVersion, ACPResultStatusUnsupportedProfile:
		cause = ErrInvalidAuthority
	default:
		return ErrInvalidAuthority
	}
	return &VerifiedACPSemanticError{status: status, cause: cause}
}

type boundedHTTP2Client struct {
	endpoint       *url.URL
	client         *http.Client
	transport      *http.Transport
	maxAttempts    int
	retryBackoff   time.Duration
	attemptTimeout time.Duration
	semaphore      chan struct{}
	closed         atomic.Bool
}

func newBoundedHTTP2Client(endpoint string, tlsConfig *tls.Config, options HTTPProviderOptions) (*boundedHTTP2Client, error) {
	parsed, err := url.Parse(endpoint)
	if err != nil || parsed.Scheme != "https" || parsed.Host == "" || parsed.User != nil || (parsed.Path != "" && parsed.Path != "/") || parsed.RawQuery != "" || parsed.Fragment != "" {
		return nil, ErrInvalidAuthority
	}
	if tlsConfig == nil || tlsConfig.InsecureSkipVerify {
		return nil, ErrInvalidAuthority
	}
	maxAttempts := options.MaxAttempts
	if maxAttempts == 0 {
		maxAttempts = defaultHTTPMaxAttempts
	}
	maxConcurrent := options.MaxConcurrent
	if maxConcurrent == 0 {
		maxConcurrent = defaultHTTPMaxConcurrent
	}
	attemptTimeout := options.AttemptTimeout
	if attemptTimeout == 0 {
		attemptTimeout = defaultAttemptTimeout
	}
	retryBackoff := options.RetryBackoff
	if retryBackoff == 0 {
		retryBackoff = defaultRetryBackoff
	}
	if maxAttempts < 1 || maxAttempts > maximumHTTPMaxAttempts || maxConcurrent < 1 || maxConcurrent > maximumHTTPConcurrent ||
		retryBackoff < 0 || retryBackoff > time.Second || attemptTimeout <= 0 || attemptTimeout > 30*time.Second {
		return nil, ErrInvalidLimits
	}
	secureTLS := tlsConfig.Clone()
	secureTLS.MinVersion = tls.VersionTLS13
	secureTLS.MaxVersion = tls.VersionTLS13
	secureTLS.NextProtos = []string{"h2"}
	if secureTLS.ServerName == "" {
		secureTLS.ServerName = parsed.Hostname()
	}
	dialer := &net.Dialer{Timeout: attemptTimeout, KeepAlive: 30 * time.Second}
	transport := &http.Transport{
		Proxy:                 nil,
		ForceAttemptHTTP2:     true,
		TLSClientConfig:       secureTLS,
		TLSHandshakeTimeout:   attemptTimeout,
		ResponseHeaderTimeout: attemptTimeout,
		IdleConnTimeout:       90 * time.Second,
		MaxIdleConns:          maxConcurrent,
		MaxIdleConnsPerHost:   maxConcurrent,
		MaxConnsPerHost:       maxConcurrent,
		DisableCompression:    true,
	}
	transport.DialTLSContext = func(ctx context.Context, network, address string) (net.Conn, error) {
		connection, err := (&tls.Dialer{NetDialer: dialer, Config: secureTLS}).DialContext(ctx, network, address)
		if err != nil {
			return nil, err
		}
		tlsConnection, ok := connection.(*tls.Conn)
		if !ok || tlsConnection.ConnectionState().Version != tls.VersionTLS13 || tlsConnection.ConnectionState().NegotiatedProtocol != "h2" {
			_ = connection.Close()
			return nil, errHTTP2Required
		}
		return connection, nil
	}
	client := &http.Client{
		Transport:     transport,
		CheckRedirect: func(*http.Request, []*http.Request) error { return errRedirect },
	}
	parsed.Path = ""
	return &boundedHTTP2Client{endpoint: parsed, client: client, transport: transport, maxAttempts: maxAttempts, retryBackoff: retryBackoff, attemptTimeout: attemptTimeout, semaphore: make(chan struct{}, maxConcurrent)}, nil
}

func (client *boundedHTTP2Client) Post(ctx context.Context, path string, body []byte, responseLimit int, deadlineUnix uint64, nowUnix func() uint64) ([]byte, error) {
	if client == nil || ctx == nil || client.closed.Load() || (path != "/acp/authority" && path != "/acp/enroll") || len(body) == 0 || responseLimit <= 0 || nowUnix == nil {
		return nil, ErrInvalidAuthority
	}
	now := nowUnix()
	if now == 0 || deadlineUnix <= now || deadlineUnix-now > 30 {
		return nil, ErrExpired
	}
	admissionContext, cancelAdmission := context.WithTimeout(ctx, time.Duration(deadlineUnix-now)*time.Second)
	select {
	case client.semaphore <- struct{}{}:
		defer func() { <-client.semaphore }()
		cancelAdmission()
	case <-admissionContext.Done():
		cancelAdmission()
		if ctx.Err() != nil {
			return nil, ctx.Err()
		}
		return nil, ErrExpired
	}
	now = nowUnix()
	if now == 0 {
		return nil, ErrInvalidAuthority
	}
	if deadlineUnix <= now {
		return nil, ErrExpired
	}
	callContext, cancelCall := context.WithTimeout(ctx, time.Duration(deadlineUnix-now)*time.Second)
	defer cancelCall()
	var lastErr error
	for attempt := 0; attempt < client.maxAttempts; attempt++ {
		now = nowUnix()
		if now == 0 {
			if lastErr == nil {
				return nil, ErrInvalidAuthority
			}
			break
		}
		if deadlineUnix <= now {
			if lastErr == nil {
				return nil, ErrExpired
			}
			break
		}
		if client.closed.Load() {
			return nil, ErrClosed
		}
		attemptContext, cancelAttempt := context.WithTimeout(callContext, client.attemptTimeout)
		response, err := client.doPost(attemptContext, path, body, responseLimit)
		cancelAttempt()
		if err == nil {
			return response, nil
		}
		lastErr = err
		if ctx.Err() != nil {
			return nil, ErrRequestAmbiguous
		}
		if !retryableTransportError(err) {
			return nil, transportError(err, false)
		}
		if attempt+1 == client.maxAttempts || callContext.Err() != nil {
			break
		}
		if client.retryBackoff > 0 {
			timer := time.NewTimer(client.retryBackoff)
			select {
			case <-timer.C:
			case <-callContext.Done():
				timer.Stop()
				return nil, ErrRequestAmbiguous
			}
		}
	}
	return nil, transportError(lastErr, true)
}

func (client *boundedHTTP2Client) doPost(ctx context.Context, path string, body []byte, responseLimit int) ([]byte, error) {
	target := *client.endpoint
	target.Path = path
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, target.String(), bytes.NewReader(body))
	if err != nil {
		return nil, &permanentTransportError{err}
	}
	// NewRequest installs GetBody for bytes.Reader. The HTTP/2 transport uses
	// that hook to replay body-bearing requests internally for REFUSED_STREAM
	// and qualifying GOAWAY paths, bypassing maxAttempts. Only the explicit
	// outer retry controller may replay these exact signed bytes.
	request.GetBody = nil
	request.Header.Set("Content-Type", "application/cose")
	request.Header.Set("Accept", "application/cose")
	response, err := client.client.Do(request)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	if response.ProtoMajor != 2 || response.TLS == nil || response.TLS.Version != tls.VersionTLS13 || response.TLS.NegotiatedProtocol != "h2" {
		return nil, &permanentTransportError{errHTTP2Required}
	}
	if response.StatusCode != http.StatusOK {
		return nil, &permanentTransportError{fmt.Errorf("unexpected HTTP status %d", response.StatusCode)}
	}
	if response.ContentLength > int64(responseLimit) {
		return nil, &invalidResponseError{errors.New("response exceeds operation limit")}
	}
	wire, err := io.ReadAll(io.LimitReader(response.Body, int64(responseLimit)+1))
	if err != nil {
		return nil, err
	}
	if len(wire) == 0 || len(wire) > responseLimit {
		return nil, &invalidResponseError{errors.New("response exceeds operation limit")}
	}
	return wire, nil
}

func (client *boundedHTTP2Client) Close() error {
	if client == nil {
		return ErrInvalidAuthority
	}
	if !client.closed.CompareAndSwap(false, true) {
		return ErrClosed
	}
	client.transport.CloseIdleConnections()
	return nil
}

type permanentTransportError struct{ error }
type invalidResponseError struct{ error }

func retryableTransportError(err error) bool {
	var permanent *permanentTransportError
	var invalid *invalidResponseError
	if errors.As(err, &permanent) || errors.As(err, &invalid) || errors.Is(err, errRedirect) || errors.Is(err, errHTTP2Required) {
		return false
	}
	var certificateError *tls.CertificateVerificationError
	var unknownAuthority x509.UnknownAuthorityError
	var hostnameError x509.HostnameError
	if errors.As(err, &certificateError) || errors.As(err, &unknownAuthority) || errors.As(err, &hostnameError) {
		return false
	}
	if errors.Is(err, io.EOF) || errors.Is(err, io.ErrUnexpectedEOF) || errors.Is(err, context.DeadlineExceeded) {
		return true
	}
	var networkError net.Error
	return errors.As(err, &networkError)
}

func transportError(err error, ambiguous bool) error {
	var invalid *invalidResponseError
	if errors.As(err, &invalid) {
		return ErrInvalidAuthority
	}
	if ambiguous {
		return ErrRequestAmbiguous
	}
	return ErrProviderUnavailable
}

var _ AuthorityProvider = (*HTTPProvider)(nil)
