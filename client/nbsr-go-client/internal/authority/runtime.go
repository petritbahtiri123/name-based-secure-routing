package authority

import (
	"context"
	"errors"
	"sync"

	"nbsr.local/client/nbsr-go-client/internal/identity"
)

type EnrollmentClient interface {
	Enroll(context.Context, EnrollmentRequestPayload) (EnrollmentResultPayload, error)
	Close() error
}

type AuthorityProviderFactory func(identity.DeviceIdentity) (AuthorityProvider, error)

type ClientRuntimeConfig struct {
	SourceOperator  string
	Profile         string
	EnrollmentStore EnrollmentStateStore
	Enrollment      EnrollmentClient
	ProviderFactory AuthorityProviderFactory
	RestartGate     *RestartGate
	NowUnix         func() uint64
}

// ClientRuntime owns the Tranche 2B control-plane lifecycle. It deliberately
// restores no RouteGrants, authority cache, Transport Sessions, Service
// Channels, Stream Credits, or Application Streams across startup/restart.
type ClientRuntime struct {
	mu sync.RWMutex

	sourceOperator  string
	profile         string
	enrollmentStore EnrollmentStateStore
	enrollment      EnrollmentClient
	providerFactory AuthorityProviderFactory
	restartGate     *RestartGate
	nowUnix         func() uint64

	identity identity.DeviceIdentity
	provider AuthorityProvider
	ready    bool
	closed   bool
}

func NewClientRuntime(config ClientRuntimeConfig) (*ClientRuntime, error) {
	if !validTextID(config.SourceOperator) || !validTextID(config.Profile) ||
		isNilDependency(config.EnrollmentStore) || config.ProviderFactory == nil ||
		config.RestartGate == nil || config.NowUnix == nil {
		return nil, ErrInvalidAuthority
	}
	return &ClientRuntime{
		sourceOperator: config.SourceOperator, profile: config.Profile,
		enrollmentStore: config.EnrollmentStore, enrollment: config.Enrollment,
		providerFactory: config.ProviderFactory, restartGate: config.RestartGate, nowUnix: config.NowUnix,
	}, nil
}

func (runtime *ClientRuntime) StartPersisted(ctx context.Context, freshness FreshnessRequest) error {
	if runtime == nil || ctx == nil {
		return ErrInvalidAuthority
	}
	runtime.mu.Lock()
	defer runtime.mu.Unlock()
	if err := runtime.resetLocked(); err != nil {
		return err
	}
	state, err := LoadEnrollmentState(ctx, runtime.enrollmentStore, runtime.nowUnix())
	if err != nil {
		return err
	}
	return runtime.activateLocked(ctx, state.Identity, freshness)
}

func (runtime *ClientRuntime) StartInitial(ctx context.Context, request EnrollmentRequestPayload, freshness FreshnessRequest) error {
	if runtime == nil || ctx == nil {
		return ErrInvalidAuthority
	}
	runtime.mu.Lock()
	defer runtime.mu.Unlock()
	if err := runtime.resetLocked(); err != nil {
		return err
	}
	if isNilDependency(runtime.enrollment) {
		return ErrInvalidAuthority
	}
	initializer, ok := runtime.enrollmentStore.(InitialEnrollmentStateStore)
	if !ok || isNilDependency(initializer) {
		return ErrInvalidAuthority
	}
	payload, err := EncodeEnrollmentRequestPayload(request)
	if err != nil {
		return err
	}
	digest := EnrollmentRequestDigest(payload)
	device, err := initializer.Initialize(ctx, digest, func() (identity.DeviceIdentity, error) {
		result, err := runtime.enrollment.Enroll(ctx, request)
		if err != nil {
			return identity.DeviceIdentity{}, err
		}
		if err := validateEnrollmentResultPayload(result); err != nil {
			return identity.DeviceIdentity{}, err
		}
		return verifiedEnrollmentIdentity(request, result, runtime.nowUnix())
	})
	if err != nil {
		return err
	}
	return runtime.activateLocked(ctx, device, freshness)
}

func (runtime *ClientRuntime) Restart(ctx context.Context, freshness FreshnessRequest) error {
	return runtime.StartPersisted(ctx, freshness)
}

func (runtime *ClientRuntime) Refresh(ctx context.Context, freshness FreshnessRequest) error {
	if runtime == nil || ctx == nil {
		return ErrInvalidAuthority
	}
	runtime.mu.Lock()
	defer runtime.mu.Unlock()
	if runtime.closed || isNilDependency(runtime.provider) || runtime.identity == (identity.DeviceIdentity{}) {
		runtime.ready = false
		return ErrNotReady
	}
	runtime.ready = false
	return runtime.verifyFreshnessLocked(ctx, runtime.identity, runtime.provider, freshness)
}

func (runtime *ClientRuntime) Acquire(ctx context.Context, request AcquireRequest) (ProviderGrant, error) {
	if runtime == nil || ctx == nil {
		return ProviderGrant{}, ErrInvalidAuthority
	}
	runtime.mu.RLock()
	defer runtime.mu.RUnlock()
	if !runtime.ready || runtime.closed || isNilDependency(runtime.provider) {
		return ProviderGrant{}, ErrNotReady
	}
	if request.Device.ID != runtime.identity.ID || request.Device.CredentialGeneration != runtime.identity.CredentialGeneration ||
		request.Key.DeviceID != runtime.identity.ID || request.Key.DeviceGeneration != runtime.identity.CredentialGeneration {
		return ProviderGrant{}, ErrBindingMismatch
	}
	return runtime.provider.Acquire(ctx, request)
}

func (runtime *ClientRuntime) Renew(ctx context.Context, request RenewRequest) (ProviderGrant, error) {
	if runtime == nil || ctx == nil {
		return ProviderGrant{}, ErrInvalidAuthority
	}
	runtime.mu.RLock()
	defer runtime.mu.RUnlock()
	if !runtime.ready || runtime.closed || isNilDependency(runtime.provider) {
		return ProviderGrant{}, ErrNotReady
	}
	if request.Device.ID != runtime.identity.ID || request.Device.CredentialGeneration != runtime.identity.CredentialGeneration ||
		request.Key.DeviceID != runtime.identity.ID || request.Key.DeviceGeneration != runtime.identity.CredentialGeneration {
		return ProviderGrant{}, ErrBindingMismatch
	}
	return runtime.provider.Renew(ctx, request)
}

func (runtime *ClientRuntime) Ready() bool {
	if runtime == nil {
		return false
	}
	runtime.mu.RLock()
	ready := runtime.ready && !runtime.closed
	runtime.mu.RUnlock()
	return ready
}

func (runtime *ClientRuntime) Identity() (identity.DeviceIdentity, error) {
	if runtime == nil {
		return identity.DeviceIdentity{}, ErrUnknownIdentity
	}
	runtime.mu.RLock()
	defer runtime.mu.RUnlock()
	if runtime.identity == (identity.DeviceIdentity{}) {
		return identity.DeviceIdentity{}, ErrUnknownIdentity
	}
	return copyDeviceIdentity(runtime.identity), nil
}

func (runtime *ClientRuntime) Close() error {
	if runtime == nil {
		return ErrInvalidAuthority
	}
	runtime.mu.Lock()
	defer runtime.mu.Unlock()
	if runtime.closed {
		return ErrClosed
	}
	runtime.ready = false
	runtime.closed = true
	var first error
	if !isNilDependency(runtime.provider) {
		first = runtime.provider.Close()
		runtime.provider = nil
	}
	if !isNilDependency(runtime.enrollment) {
		if err := runtime.enrollment.Close(); first == nil {
			first = err
		}
	}
	return first
}

func (runtime *ClientRuntime) resetLocked() error {
	if runtime.closed {
		return ErrClosed
	}
	runtime.ready = false
	runtime.identity = identity.DeviceIdentity{}
	if !isNilDependency(runtime.provider) {
		err := runtime.provider.Close()
		runtime.provider = nil
		if err != nil && !errorsIsClosed(err) {
			return err
		}
	}
	return nil
}

func (runtime *ClientRuntime) activateLocked(ctx context.Context, device identity.DeviceIdentity, freshness FreshnessRequest) error {
	if device.SourceOperatorID != runtime.sourceOperator || freshness.SourceOperator != runtime.sourceOperator ||
		freshness.Profile != runtime.profile || freshness.DeviceID != device.ID ||
		freshness.DeviceGeneration != device.CredentialGeneration {
		return ErrBindingMismatch
	}
	provider, err := runtime.providerFactory(copyDeviceIdentity(device))
	if err != nil || isNilDependency(provider) {
		return ErrProviderUnavailable
	}
	runtime.identity = copyDeviceIdentity(device)
	runtime.provider = provider
	if err := runtime.verifyFreshnessLocked(ctx, device, provider, freshness); err != nil {
		_ = provider.Close()
		runtime.provider = nil
		runtime.identity = identity.DeviceIdentity{}
		return err
	}
	return nil
}

func (runtime *ClientRuntime) verifyFreshnessLocked(ctx context.Context, device identity.DeviceIdentity, provider AuthorityProvider, request FreshnessRequest) error {
	runtime.ready = false
	if request.SourceOperator != runtime.sourceOperator || request.Profile != runtime.profile ||
		request.DeviceID != device.ID || request.DeviceGeneration != device.CredentialGeneration {
		return ErrBindingMismatch
	}
	if err := runtime.restartGate.Load(ctx, runtime.sourceOperator, runtime.profile); err != nil {
		return err
	}
	freshness, err := provider.Freshness(ctx, request)
	if err != nil {
		return err
	}
	if _, err := runtime.restartGate.AcceptFresh(ctx, request, freshness); err != nil {
		return err
	}
	runtime.ready = true
	return nil
}

func errorsIsClosed(err error) bool { return errors.Is(err, ErrClosed) }
