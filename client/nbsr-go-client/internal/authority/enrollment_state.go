package authority

import (
	"context"
	"errors"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"sync"

	"nbsr.local/client/nbsr-go-client/internal/identity"
)

const maxEnrollmentStateBytes = 1 << 20

type EnrollmentState struct {
	Identity identity.DeviceIdentity
	Ready    bool
}

type EnrollmentStateStore interface {
	Load(context.Context) (identity.DeviceIdentity, bool, error)
	Store(context.Context, identity.DeviceIdentity) error
}

func ApplyVerifiedEnrollmentResult(ctx context.Context, request EnrollmentRequestPayload, result EnrollmentResultPayload, store EnrollmentStateStore, now uint64) (EnrollmentState, error) {
	if err := validateEnrollmentResultCommitInputs(ctx, request, result, store, now); err != nil {
		return EnrollmentState{}, err
	}
	if result.Status != EnrollmentStatusAccepted {
		return EnrollmentState{}, ErrTerminalEnrollment
	}
	if result.DeviceIdentity == nil {
		return EnrollmentState{}, ErrInvalidAuthority
	}
	device := copyDeviceIdentity(*result.DeviceIdentity)
	if err := validateEnrollmentResultBinding(request, device); err != nil {
		return EnrollmentState{}, err
	}
	if err := validateEnrollmentDeviceIdentityTemporal(device, now); err != nil {
		return EnrollmentState{}, err
	}
	if err := store.Store(ctx, device); err != nil {
		return EnrollmentState{}, err
	}
	return EnrollmentState{Identity: device, Ready: false}, nil
}

func LoadEnrollmentState(ctx context.Context, store EnrollmentStateStore, now uint64) (EnrollmentState, error) {
	if err := validateEnrollmentStateLoadInputs(ctx, store, now); err != nil {
		return EnrollmentState{}, err
	}
	device, found, err := store.Load(ctx)
	if err != nil {
		return EnrollmentState{}, err
	}
	if !found {
		return EnrollmentState{}, ErrUnknownIdentity
	}
	if err := validateEnrollmentDeviceIdentity(device); err != nil {
		return EnrollmentState{}, err
	}
	if err := validateEnrollmentDeviceIdentityTemporal(device, now); err != nil {
		return EnrollmentState{}, err
	}
	return EnrollmentState{Identity: copyDeviceIdentity(device), Ready: false}, nil
}

func validateEnrollmentResultCommitInputs(ctx context.Context, request EnrollmentRequestPayload, result EnrollmentResultPayload, store EnrollmentStateStore, now uint64) error {
	if err := validateEnrollmentRequestPayload(request); err != nil {
		return err
	}
	if err := validateEnrollmentResultPayload(result); err != nil {
		return err
	}
	if isNilDependency(ctx) || isNilDependency(store) || !validUnixTime(now) {
		return ErrInvalidAuthority
	}
	return nil
}

func validateEnrollmentStateLoadInputs(ctx context.Context, store EnrollmentStateStore, now uint64) error {
	if isNilDependency(ctx) || isNilDependency(store) || !validUnixTime(now) || now == 0 {
		return ErrInvalidAuthority
	}
	return nil
}

func validateEnrollmentResultBinding(request EnrollmentRequestPayload, device identity.DeviceIdentity) error {
	if device.SourceOperatorID != request.SourceOperator {
		return ErrBindingMismatch
	}
	if device.SigningKey.ID != request.DeviceSigningKey.KeyID ||
		device.SigningKey.Purpose != request.DeviceSigningKey.Purpose ||
		device.SigningKey.Generation != request.DeviceSigningKey.Generation ||
		device.SigningKey.Thumbprint != request.DeviceSigningKey.Thumbprint ||
		device.CredentialGeneration != request.DeviceSigningKey.Generation {
		return ErrBindingMismatch
	}
	return nil
}

func validateEnrollmentDeviceIdentityTemporal(device identity.DeviceIdentity, now uint64) error {
	if !validUnixTime(now) || now == 0 {
		return ErrInvalidAuthority
	}
	if now < device.CredentialNotBefore {
		return ErrExpired
	}
	if now >= device.CredentialExpiresAt {
		return ErrExpired
	}
	return nil
}

func copyDeviceIdentity(device identity.DeviceIdentity) identity.DeviceIdentity {
	return identity.DeviceIdentity{
		ID:                   device.ID,
		SourceOperatorID:     device.SourceOperatorID,
		CredentialGeneration: device.CredentialGeneration,
		CredentialNotBefore:  device.CredentialNotBefore,
		CredentialExpiresAt:  device.CredentialExpiresAt,
		SigningKey: identity.KeyRef{
			ID:         device.SigningKey.ID,
			Purpose:    device.SigningKey.Purpose,
			Generation: device.SigningKey.Generation,
			Thumbprint: device.SigningKey.Thumbprint,
		},
	}
}

type MemoryEnrollmentStateStore struct {
	mu     sync.RWMutex
	seen   bool
	device identity.DeviceIdentity
}

func NewMemoryEnrollmentStateStore() *MemoryEnrollmentStateStore {
	return &MemoryEnrollmentStateStore{}
}

func (store *MemoryEnrollmentStateStore) Load(_ context.Context) (identity.DeviceIdentity, bool, error) {
	if store == nil {
		return identity.DeviceIdentity{}, false, ErrInvalidAuthority
	}
	store.mu.RLock()
	defer store.mu.RUnlock()
	if !store.seen {
		return identity.DeviceIdentity{}, false, nil
	}
	return copyDeviceIdentity(store.device), true, nil
}

func (store *MemoryEnrollmentStateStore) Store(_ context.Context, device identity.DeviceIdentity) error {
	if store == nil || !validateEnrollmentResultIdentity(device) {
		return ErrInvalidAuthority
	}
	store.mu.Lock()
	defer store.mu.Unlock()
	if store.seen {
		return ErrTerminalEnrollment
	}
	store.device = copyDeviceIdentity(device)
	store.seen = true
	return nil
}

func validateEnrollmentResultIdentity(device identity.DeviceIdentity) bool {
	return validateEnrollmentDeviceIdentity(device) == nil
}

type FileEnrollmentStateStore struct {
	mu sync.Mutex

	path string

	write func(path string, payload []byte) error
}

func NewFileEnrollmentStateStore(path string) *FileEnrollmentStateStore {
	return &FileEnrollmentStateStore{path: path, write: atomicWriteEnrollmentState}
}

func (store *FileEnrollmentStateStore) Load(_ context.Context) (identity.DeviceIdentity, bool, error) {
	if store == nil || store.path == "" {
		return identity.DeviceIdentity{}, false, ErrInvalidAuthority
	}
	data, err := os.ReadFile(store.path)
	if err != nil {
		if errors.Is(err, fs.ErrNotExist) {
			return identity.DeviceIdentity{}, false, nil
		}
		return identity.DeviceIdentity{}, false, ErrInvalidAuthority
	}
	if len(data) == 0 || len(data) > maxEnrollmentStateBytes {
		return identity.DeviceIdentity{}, false, ErrInvalidAuthority
	}
	device, err := parseStoredEnrollmentDeviceIdentity(data)
	if err != nil {
		return identity.DeviceIdentity{}, false, ErrInvalidAuthority
	}
	return copyDeviceIdentity(device), true, nil
}

func (store *FileEnrollmentStateStore) Store(_ context.Context, device identity.DeviceIdentity) error {
	if store == nil || store.path == "" {
		return ErrInvalidAuthority
	}
	if !validateEnrollmentResultIdentity(device) {
		return ErrInvalidAuthority
	}
	payload, err := encodeStoredEnrollmentDeviceIdentity(device)
	if err != nil {
		return ErrInvalidAuthority
	}
	store.mu.Lock()
	defer store.mu.Unlock()
	_, present, err := store.loadLocked()
	if err != nil {
		return err
	}
	if present {
		return ErrTerminalEnrollment
	}
	write := store.write
	if write == nil {
		write = atomicWriteEnrollmentState
	}
	return write(store.path, payload)
}

func (store *FileEnrollmentStateStore) loadLocked() (identity.DeviceIdentity, bool, error) {
	data, err := os.ReadFile(store.path)
	if err != nil {
		if errors.Is(err, fs.ErrNotExist) {
			return identity.DeviceIdentity{}, false, nil
		}
		return identity.DeviceIdentity{}, false, ErrInvalidAuthority
	}
	if len(data) == 0 || len(data) > maxEnrollmentStateBytes {
		return identity.DeviceIdentity{}, false, ErrInvalidAuthority
	}
	device, err := parseStoredEnrollmentDeviceIdentity(data)
	if err != nil {
		return identity.DeviceIdentity{}, false, ErrInvalidAuthority
	}
	return device, true, nil
}

var atomicWriteEnrollmentState = func(path string, payload []byte) error {
	return writeEnrollmentStateAtomically(path, payload)
}

func writeEnrollmentStateAtomically(path string, payload []byte) error {
	if path == "" {
		return ErrInvalidAuthority
	}
	if len(payload) == 0 || len(payload) > maxEnrollmentStateBytes {
		return ErrInvalidAuthority
	}
	parent := filepath.Dir(path)
	if err := os.MkdirAll(parent, 0o700); err != nil {
		return err
	}
	file, err := os.CreateTemp(parent, "nbsr-enrollment-state-*")
	if err != nil {
		return err
	}
	tempPath := file.Name()
	defer os.Remove(tempPath)
	if n, err := file.Write(payload); err != nil {
		_ = file.Close()
		return err
	} else if n != len(payload) {
		_ = file.Close()
		return io.ErrShortWrite
	}
	if err := file.Sync(); err != nil {
		_ = file.Close()
		return err
	}
	if err := file.Close(); err != nil {
		return err
	}
	if err := os.Rename(tempPath, path); err != nil {
		return err
	}
	_ = os.Remove(tempPath)
	return nil
}

func encodeStoredEnrollmentDeviceIdentity(device identity.DeviceIdentity) ([]byte, error) {
	return encodeCBOR(map[uint64]any{
		0: device.ID[:],
		1: device.SourceOperatorID,
		2: device.CredentialGeneration,
		3: device.CredentialNotBefore,
		4: device.CredentialExpiresAt,
		5: map[uint64]any{
			0: device.SigningKey.ID[:],
			1: uint64(device.SigningKey.Purpose),
			2: device.SigningKey.Generation,
			3: device.SigningKey.Thumbprint[:],
		},
	})
}

func parseStoredEnrollmentDeviceIdentity(payload []byte) (identity.DeviceIdentity, error) {
	raw, err := decodeCBORExact(payload, defaultCBORLimits())
	if err != nil {
		return identity.DeviceIdentity{}, err
	}
	fields, ok := raw.(map[uint64]any)
	if !ok {
		return identity.DeviceIdentity{}, ErrInvalidAuthority
	}
	return parseEnrollmentDeviceIdentity(fields)
}
