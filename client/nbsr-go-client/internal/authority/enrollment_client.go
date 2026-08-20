package authority

import (
	"context"
	"crypto/tls"
	"time"

	"nbsr.local/client/nbsr-go-client/internal/identity"
)

// EnrollmentHTTPClientConfig binds an initial-enrollment client to one Source
// Operator endpoint. Deployment bootstrap authorization is intentionally not
// represented here or serialized into the generic enrollment wire.
type EnrollmentHTTPClientConfig struct {
	Endpoint       string
	TLSConfig      *tls.Config
	SourceOperator string
	Profile        string
	Signer         identity.Signer
	ResultIssuers  EnrollmentResultIssuerResolver
	Options        HTTPProviderOptions
	NowUnix        func() uint64
}

type EnrollmentHTTPClient struct {
	http           *boundedHTTP2Client
	sourceOperator string
	profile        string
	signer         identity.Signer
	issuers        EnrollmentResultIssuerResolver
	nowUnix        func() uint64
}

func NewEnrollmentHTTPClient(config EnrollmentHTTPClientConfig) (*EnrollmentHTTPClient, error) {
	if !validTextID(config.SourceOperator) || !validTextID(config.Profile) || isNilDependency(config.Signer) || isNilDependency(config.ResultIssuers) {
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
	return &EnrollmentHTTPClient{http: client, sourceOperator: config.SourceOperator, profile: config.Profile, signer: config.Signer, issuers: config.ResultIssuers, nowUnix: nowUnix}, nil
}

func (client *EnrollmentHTTPClient) Enroll(ctx context.Context, request EnrollmentRequestPayload) (EnrollmentResultPayload, error) {
	if client == nil || ctx == nil || request.SourceOperator != client.sourceOperator || request.Profile != client.profile {
		return EnrollmentResultPayload{}, ErrBindingMismatch
	}
	if err := validateEnrollmentRequestDeadline(request.DeadlineUnix, client.nowUnix()); err != nil {
		return EnrollmentResultPayload{}, err
	}
	payload, err := EncodeEnrollmentRequestPayload(request)
	if err != nil {
		return EnrollmentResultPayload{}, err
	}
	wire, err := SignEnrollmentRequest(ctx, request, client.signer)
	if err != nil {
		return EnrollmentResultPayload{}, err
	}
	if len(wire) == 0 || len(wire) > maxEnrollmentRequestBodySize {
		return EnrollmentResultPayload{}, ErrInvalidAuthority
	}
	response, err := client.http.Post(ctx, "/acp/enroll", wire, maxEnrollmentResultBodySize, request.DeadlineUnix, client.nowUnix)
	if err != nil {
		return EnrollmentResultPayload{}, err
	}
	result, _, err := ParseVerifiedEnrollmentResult(ctx, response, request, payload, client.issuers, client.nowUnix())
	if err != nil {
		return EnrollmentResultPayload{}, err
	}
	if result.Status != EnrollmentStatusAccepted {
		return result, enrollmentSemanticError(result.Status)
	}
	return result, nil
}

func (client *EnrollmentHTTPClient) Close() error {
	if client == nil || client.http == nil {
		return ErrInvalidAuthority
	}
	return client.http.Close()
}

func enrollmentSemanticError(status EnrollmentStatus) error {
	switch status {
	case EnrollmentStatusRequestConflict:
		return ErrRequestConflict
	case EnrollmentStatusExpired:
		return ErrExpired
	case EnrollmentStatusRejected, EnrollmentStatusInvalid:
		return ErrTerminalEnrollment
	default:
		return ErrInvalidAuthority
	}
}
