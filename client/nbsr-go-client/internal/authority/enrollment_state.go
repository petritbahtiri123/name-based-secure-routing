package authority

import (
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"io"
	"path/filepath"
	"sync"

	"nbsr.local/client/nbsr-go-client/internal/identity"
)

const (
	enrollmentStateEnvelopeVersion           = 1
	enrollmentStateTypeEnrollment            = 1
	enrollmentStateIntegrityAlgorithmEd25519 = 1
	maxEnrollmentStateBytes                  = 1 << 20

	enrollmentStateEnvelopeFieldVersion   = uint64(0)
	enrollmentStateEnvelopeFieldType      = uint64(1)
	enrollmentStateEnvelopeFieldPayload   = uint64(2)
	enrollmentStateEnvelopeFieldIntegrity = uint64(3)
	enrollmentStateEnvelopeFieldSignature = uint64(4)

	enrollmentStateIntegrityFieldID         = uint64(0)
	enrollmentStateIntegrityFieldPurpose    = uint64(1)
	enrollmentStateIntegrityFieldGeneration = uint64(2)
	enrollmentStateIntegrityFieldThumbprint = uint64(3)
	enrollmentStateIntegrityFieldPublicKey  = uint64(4)
	enrollmentStateIntegrityFieldAlgorithm  = uint64(5)
	enrollmentStateIntegrityFieldPrivateKey = uint64(6)
)

const enrollmentStateIntegritySigningDomain = "NBSR-GO-CLIENT-KEY-PURPOSE-v1\x00"

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

	paths EnrollmentStatePaths

	write func(path string, payload []byte) error
}

func NewFileEnrollmentStateStore() (*FileEnrollmentStateStore, error) {
	paths, err := ResolveEnrollmentStatePaths()
	if err != nil {
		return nil, err
	}
	return newFileEnrollmentStateStore(paths)
}

func newFileEnrollmentStateStoreForTest(root string) (*FileEnrollmentStateStore, error) {
	paths, err := ResolveEnrollmentStatePathsForTest(root)
	if err != nil {
		return nil, err
	}
	return newFileEnrollmentStateStore(paths)
}

func newFileEnrollmentStateStore(paths EnrollmentStatePaths) (*FileEnrollmentStateStore, error) {
	if err := validateEnrollmentStatePaths(paths); err != nil {
		return nil, err
	}
	return &FileEnrollmentStateStore{paths: paths, write: atomicWriteEnrollmentState}, nil
}

func (store *FileEnrollmentStateStore) Load(ctx context.Context) (identity.DeviceIdentity, bool, error) {
	if store == nil || isNilDependency(ctx) {
		return identity.DeviceIdentity{}, false, ErrInvalidAuthority
	}
	store.mu.Lock()
	defer store.mu.Unlock()
	return store.withLock(func() (identity.DeviceIdentity, bool, error) {
		return store.loadLocked()
	})
}

func (store *FileEnrollmentStateStore) Store(ctx context.Context, device identity.DeviceIdentity) error {
	if store == nil || isNilDependency(ctx) {
		return ErrInvalidAuthority
	}
	if !validateEnrollmentResultIdentity(device) {
		return ErrInvalidAuthority
	}
	store.mu.Lock()
	defer store.mu.Unlock()
	_, _, err := store.withLock(func() (identity.DeviceIdentity, bool, error) {
		_, present, err := store.loadLocked()
		if err != nil {
			return identity.DeviceIdentity{}, false, err
		}
		if present {
			return identity.DeviceIdentity{}, false, ErrTerminalEnrollment
		}
		if err := cleanupEnrollmentStateTemps(store.paths.Root); err != nil {
			return identity.DeviceIdentity{}, false, err
		}
		payload, err := store.buildEnrollmentStateEnvelope(device)
		if err != nil {
			return identity.DeviceIdentity{}, false, err
		}
		write := store.write
		if write == nil {
			write = atomicWriteEnrollmentState
		}
		if err := write(store.paths.StatePath, payload); err != nil {
			return identity.DeviceIdentity{}, false, err
		}
		return identity.DeviceIdentity{}, false, nil
	})
	return err
}

func (store *FileEnrollmentStateStore) loadLocked() (identity.DeviceIdentity, bool, error) {
	data, found, err := readEnrollmentStateBlob(store.paths.StatePath)
	if err != nil {
		return identity.DeviceIdentity{}, false, err
	}
	if !found {
		return identity.DeviceIdentity{}, false, nil
	}
	device, err := parseStoredEnrollmentState(data, store.integrityKeyPath())
	if err != nil {
		return identity.DeviceIdentity{}, false, err
	}
	return device, true, nil
}

func (store *FileEnrollmentStateStore) integrityKeyPath() string {
	return filepath.Join(store.paths.Root, enrollmentStateIntegrityKeyName)
}

func (store *FileEnrollmentStateStore) withLock(operation func() (identity.DeviceIdentity, bool, error)) (device identity.DeviceIdentity, found bool, err error) {
	if err := validateEnrollmentStatePaths(store.paths); err != nil {
		return identity.DeviceIdentity{}, false, err
	}
	lock, err := AcquireEnrollmentStateLock(store.paths)
	if err != nil {
		return identity.DeviceIdentity{}, false, err
	}
	defer func() {
		if closeErr := lock.Close(); err == nil && closeErr != nil {
			err = closeErr
		}
	}()
	if err := validateEnrollmentStatePaths(store.paths); err != nil {
		return identity.DeviceIdentity{}, false, err
	}
	return operation()
}

func (store *FileEnrollmentStateStore) buildEnrollmentStateEnvelope(device identity.DeviceIdentity) ([]byte, error) {
	payload, err := encodeStoredEnrollmentDeviceIdentity(device)
	if err != nil {
		return nil, err
	}
	material, err := loadOrCreateEnrollmentStateIntegrityMaterial(store.integrityKeyPath())
	if err != nil {
		return nil, err
	}
	integrityMeta, err := material.encodedIntegrityMetadata()
	if err != nil {
		return nil, err
	}
	unsigned, err := encodeCBOR(map[uint64]any{
		enrollmentStateEnvelopeFieldVersion:   uint64(enrollmentStateEnvelopeVersion),
		enrollmentStateEnvelopeFieldType:      uint64(enrollmentStateTypeEnrollment),
		enrollmentStateEnvelopeFieldPayload:   payload,
		enrollmentStateEnvelopeFieldIntegrity: integrityMeta,
	})
	if err != nil {
		return nil, err
	}
	signature := material.signEnrollmentStateIntegrity(unsigned)
	return encodeCBOR(map[uint64]any{
		enrollmentStateEnvelopeFieldVersion:   uint64(enrollmentStateEnvelopeVersion),
		enrollmentStateEnvelopeFieldType:      uint64(enrollmentStateTypeEnrollment),
		enrollmentStateEnvelopeFieldPayload:   payload,
		enrollmentStateEnvelopeFieldIntegrity: integrityMeta,
		enrollmentStateEnvelopeFieldSignature: signature,
	})
}

var atomicWriteEnrollmentState = func(path string, payload []byte) error {
	return writeEnrollmentStateAtomically(path, payload)
}

func parseStoredEnrollmentState(raw []byte, integrityKeyPath string) (identity.DeviceIdentity, error) {
	if len(raw) == 0 || len(raw) > maxEnrollmentStateBytes {
		return identity.DeviceIdentity{}, ErrInvalidAuthority
	}
	envelopeRaw, err := decodeCBORExact(raw, defaultCBORLimits())
	if err != nil {
		return identity.DeviceIdentity{}, ErrInvalidAuthority
	}
	fields, ok := envelopeRaw.(map[uint64]any)
	if !ok {
		return identity.DeviceIdentity{}, ErrInvalidAuthority
	}
	if len(fields) != 5 {
		return identity.DeviceIdentity{}, ErrInvalidAuthority
	}
	version, ok := fields[enrollmentStateEnvelopeFieldVersion].(uint64)
	if !ok || version != enrollmentStateEnvelopeVersion {
		return identity.DeviceIdentity{}, ErrInvalidAuthority
	}
	stateType, ok := fields[enrollmentStateEnvelopeFieldType].(uint64)
	if !ok || stateType != enrollmentStateTypeEnrollment {
		return identity.DeviceIdentity{}, ErrInvalidAuthority
	}
	payload, ok := fields[enrollmentStateEnvelopeFieldPayload].([]byte)
	if !ok || len(payload) == 0 {
		return identity.DeviceIdentity{}, ErrInvalidAuthority
	}
	integrityRaw, ok := fields[enrollmentStateEnvelopeFieldIntegrity].(map[uint64]any)
	if !ok {
		return identity.DeviceIdentity{}, ErrInvalidAuthority
	}
	signature, ok := fields[enrollmentStateEnvelopeFieldSignature].([]byte)
	if !ok || len(signature) != ed25519.SignatureSize {
		return identity.DeviceIdentity{}, ErrInvalidAuthority
	}

	unsigned, err := encodeCBOR(map[uint64]any{
		enrollmentStateEnvelopeFieldVersion:   version,
		enrollmentStateEnvelopeFieldType:      stateType,
		enrollmentStateEnvelopeFieldPayload:   payload,
		enrollmentStateEnvelopeFieldIntegrity: integrityRaw,
	})
	if err != nil {
		return identity.DeviceIdentity{}, ErrInvalidAuthority
	}
	ref, publicKey, err := parseEnrollmentStateIntegrityMetadata(integrityRaw)
	if err != nil {
		return identity.DeviceIdentity{}, ErrInvalidAuthority
	}
	material, err := loadEnrollmentStateIntegrityMaterial(integrityKeyPath)
	if err != nil {
		return identity.DeviceIdentity{}, ErrInvalidAuthority
	}
	if material.keyRef != ref || !bytes.Equal(material.public, publicKey) {
		return identity.DeviceIdentity{}, ErrInvalidAuthority
	}

	if !ed25519.Verify(material.public, appendEnrollmentStateIntegrityMessage(unsigned), signature) {
		return identity.DeviceIdentity{}, ErrSignatureFailure
	}

	device, err := parseStoredEnrollmentDeviceIdentity(payload)
	if err != nil {
		return identity.DeviceIdentity{}, ErrInvalidAuthority
	}
	return device, nil
}

type enrollmentStateIntegrityMaterial struct {
	keyRef  identity.KeyRef
	private ed25519.PrivateKey
	public  ed25519.PublicKey
}

func loadOrCreateEnrollmentStateIntegrityMaterial(path string) (enrollmentStateIntegrityMaterial, error) {
	_, found, err := readEnrollmentStateBlob(path)
	if err != nil {
		return enrollmentStateIntegrityMaterial{}, err
	}
	if found {
		return loadEnrollmentStateIntegrityMaterial(path)
	}
	material, err := newEnrollmentStateIntegrityMaterial()
	if err != nil {
		return enrollmentStateIntegrityMaterial{}, err
	}
	encoded, err := material.encode()
	if err != nil {
		return enrollmentStateIntegrityMaterial{}, err
	}
	protected, err := protectEnrollmentStateIntegrityBlob(encoded)
	if err != nil {
		return enrollmentStateIntegrityMaterial{}, err
	}
	if err := writeEnrollmentStateIntegrityBlob(path, protected); err != nil {
		return enrollmentStateIntegrityMaterial{}, err
	}
	return material, nil
}

func loadEnrollmentStateIntegrityMaterial(path string) (enrollmentStateIntegrityMaterial, error) {
	protected, found, err := readEnrollmentStateBlob(path)
	if err != nil {
		return enrollmentStateIntegrityMaterial{}, ErrStoragePathRejected
	}
	if !found {
		return enrollmentStateIntegrityMaterial{}, ErrStoragePathRejected
	}
	decoded, err := unprotectEnrollmentStateIntegrityBlob(protected)
	if err != nil {
		return enrollmentStateIntegrityMaterial{}, ErrStoragePathRejected
	}
	return parseEnrollmentStateIntegrityMaterial(decoded)
}

func parseEnrollmentStateIntegrityMetadata(raw map[uint64]any) (identity.KeyRef, []byte, error) {
	if len(raw) != 6 {
		return identity.KeyRef{}, nil, ErrInvalidAuthority
	}
	keyID, ok := raw[enrollmentStateIntegrityFieldID].([]byte)
	if !ok || len(keyID) != 32 {
		return identity.KeyRef{}, nil, ErrInvalidAuthority
	}
	purpose, ok := raw[enrollmentStateIntegrityFieldPurpose].(uint64)
	if !ok || purpose != uint64(identity.PurposeLocalStateIntegrity) {
		return identity.KeyRef{}, nil, ErrInvalidAuthority
	}
	generation, ok := raw[enrollmentStateIntegrityFieldGeneration].(uint64)
	if !ok || generation == 0 {
		return identity.KeyRef{}, nil, ErrInvalidAuthority
	}
	thumbprint, ok := raw[enrollmentStateIntegrityFieldThumbprint].([]byte)
	if !ok || len(thumbprint) != 32 {
		return identity.KeyRef{}, nil, ErrInvalidAuthority
	}
	public, ok := raw[enrollmentStateIntegrityFieldPublicKey].([]byte)
	if !ok || len(public) != ed25519.PublicKeySize {
		return identity.KeyRef{}, nil, ErrInvalidAuthority
	}
	algorithm, ok := raw[enrollmentStateIntegrityFieldAlgorithm].(uint64)
	if !ok || algorithm != enrollmentStateIntegrityAlgorithmEd25519 {
		return identity.KeyRef{}, nil, ErrInvalidAuthority
	}
	var keyRef identity.KeyRef
	copy(keyRef.ID[:], keyID)
	keyRef.Purpose = identity.Purpose(purpose)
	keyRef.Generation = generation
	copy(keyRef.Thumbprint[:], thumbprint)
	if keyRef == (identity.KeyRef{}) {
		return identity.KeyRef{}, nil, ErrInvalidAuthority
	}
	return keyRef, append([]byte(nil), public...), nil
}

func (material enrollmentStateIntegrityMaterial) encodedIntegrityMetadata() (map[uint64]any, error) {
	return map[uint64]any{
		enrollmentStateIntegrityFieldID:         material.keyRef.ID[:],
		enrollmentStateIntegrityFieldPurpose:    uint64(material.keyRef.Purpose),
		enrollmentStateIntegrityFieldGeneration: material.keyRef.Generation,
		enrollmentStateIntegrityFieldThumbprint: material.keyRef.Thumbprint[:],
		enrollmentStateIntegrityFieldPublicKey:  []byte(material.public),
		enrollmentStateIntegrityFieldAlgorithm:  uint64(enrollmentStateIntegrityAlgorithmEd25519),
	}, nil
}

func (material enrollmentStateIntegrityMaterial) encode() ([]byte, error) {
	return encodeCBOR(map[uint64]any{
		enrollmentStateIntegrityFieldID:         material.keyRef.ID[:],
		enrollmentStateIntegrityFieldPurpose:    uint64(material.keyRef.Purpose),
		enrollmentStateIntegrityFieldGeneration: material.keyRef.Generation,
		enrollmentStateIntegrityFieldThumbprint: material.keyRef.Thumbprint[:],
		enrollmentStateIntegrityFieldPublicKey:  []byte(material.public),
		enrollmentStateIntegrityFieldPrivateKey: []byte(material.private),
	})
}

func parseEnrollmentStateIntegrityMaterial(raw []byte) (enrollmentStateIntegrityMaterial, error) {
	decoded, err := decodeCBORExact(raw, defaultCBORLimits())
	if err != nil {
		return enrollmentStateIntegrityMaterial{}, err
	}
	fields, ok := decoded.(map[uint64]any)
	if !ok {
		return enrollmentStateIntegrityMaterial{}, ErrInvalidAuthority
	}
	if len(fields) != 6 {
		return enrollmentStateIntegrityMaterial{}, ErrInvalidAuthority
	}
	keyID, ok := fields[enrollmentStateIntegrityFieldID].([]byte)
	if !ok || len(keyID) != 32 {
		return enrollmentStateIntegrityMaterial{}, ErrInvalidAuthority
	}
	purposeValue, ok := fields[enrollmentStateIntegrityFieldPurpose].(uint64)
	if !ok || purposeValue != uint64(identity.PurposeLocalStateIntegrity) {
		return enrollmentStateIntegrityMaterial{}, ErrInvalidAuthority
	}
	generation, ok := fields[enrollmentStateIntegrityFieldGeneration].(uint64)
	if !ok || generation == 0 {
		return enrollmentStateIntegrityMaterial{}, ErrInvalidAuthority
	}
	thumbprint, ok := fields[enrollmentStateIntegrityFieldThumbprint].([]byte)
	if !ok || len(thumbprint) != 32 {
		return enrollmentStateIntegrityMaterial{}, ErrInvalidAuthority
	}
	public, ok := fields[enrollmentStateIntegrityFieldPublicKey].([]byte)
	if !ok || len(public) != ed25519.PublicKeySize {
		return enrollmentStateIntegrityMaterial{}, ErrInvalidAuthority
	}
	private, ok := fields[enrollmentStateIntegrityFieldPrivateKey].([]byte)
	if !ok || len(private) != ed25519.PrivateKeySize {
		return enrollmentStateIntegrityMaterial{}, ErrInvalidAuthority
	}
	var keyRef identity.KeyRef
	copy(keyRef.ID[:], keyID)
	keyRef.Purpose = identity.Purpose(purposeValue)
	keyRef.Generation = generation
	copy(keyRef.Thumbprint[:], thumbprint)
	if keyRef == (identity.KeyRef{}) {
		return enrollmentStateIntegrityMaterial{}, ErrInvalidAuthority
	}
	privateCopy := append(ed25519.PrivateKey(nil), private...)
	publicFromPrivate := ed25519.PrivateKey(privateCopy).Public().(ed25519.PublicKey)
	if !bytes.Equal(publicFromPrivate, public) {
		return enrollmentStateIntegrityMaterial{}, ErrInvalidAuthority
	}
	if sha256.Sum256(publicFromPrivate) != keyRef.Thumbprint {
		return enrollmentStateIntegrityMaterial{}, ErrInvalidAuthority
	}
	return enrollmentStateIntegrityMaterial{
		keyRef:  keyRef,
		private: privateCopy,
		public:  publicFromPrivate,
	}, nil
}

func newEnrollmentStateIntegrityMaterial() (enrollmentStateIntegrityMaterial, error) {
	public, private, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		return enrollmentStateIntegrityMaterial{}, err
	}
	var id [32]byte
	if _, err := io.ReadFull(rand.Reader, id[:]); err != nil {
		return enrollmentStateIntegrityMaterial{}, err
	}
	for isZero32(id) {
		if _, err := io.ReadFull(rand.Reader, id[:]); err != nil {
			return enrollmentStateIntegrityMaterial{}, err
		}
	}
	return enrollmentStateIntegrityMaterial{
		keyRef: identity.KeyRef{
			ID:         id,
			Purpose:    identity.PurposeLocalStateIntegrity,
			Generation: 1,
			Thumbprint: sha256.Sum256(public),
		},
		private: private,
		public:  append(ed25519.PublicKey(nil), public...),
	}, nil
}

func appendEnrollmentStateIntegrityMessage(payload []byte) []byte {
	message := make([]byte, 0, len(enrollmentStateIntegritySigningDomain)+1+len(payload))
	message = append(message, enrollmentStateIntegritySigningDomain...)
	message = append(message, byte(identity.PurposeLocalStateIntegrity))
	return append(message, payload...)
}

func (material enrollmentStateIntegrityMaterial) signEnrollmentStateIntegrity(payload []byte) []byte {
	return ed25519.Sign(material.private, appendEnrollmentStateIntegrityMessage(payload))
}

func writeEnrollmentStateIntegrityBlob(path string, blob []byte) error {
	if path == "" {
		return ErrInvalidAuthority
	}
	if len(blob) > maxEnrollmentStateBytes {
		return ErrInvalidAuthority
	}
	return writeEnrollmentStateIntegrityBlobAtomically(path, blob)
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

func isZero32(value [32]byte) bool {
	return value == [32]byte{}
}
