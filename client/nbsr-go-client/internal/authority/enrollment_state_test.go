package authority

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"testing"
	"time"

	"nbsr.local/client/nbsr-go-client/internal/identity"
)

func TestApplyVerifiedEnrollmentResultAcceptsExactIdentityAndPersistsNotReady(t *testing.T) {
	ctx := context.Background()
	store := NewMemoryEnrollmentStateStore()

	request := validEnrollmentRequestPayload()
	requestPayload, err := EncodeEnrollmentRequestPayload(request)
	if err != nil {
		t.Fatal(err)
	}
	result := validEnrollmentResultPayloadBoundToRequest(request, requestPayload, EnrollmentStatusAccepted)

	now := result.DeviceIdentity.CredentialNotBefore + 10
	state, err := ApplyVerifiedEnrollmentResult(ctx, request, result, store, now)
	if err != nil {
		t.Fatalf("ApplyVerifiedEnrollmentResult: %v", err)
	}
	if state.Ready {
		t.Fatal("accepted enrollment state was marked ready without freshness")
	}
	if !sameDeviceIdentity(state.Identity, *result.DeviceIdentity) {
		t.Fatalf("persisted identity mismatch: got=%#v want=%#v", state.Identity, *result.DeviceIdentity)
	}

	loaded, has, err := store.Load(ctx)
	if err != nil {
		t.Fatalf("Store.Load: %v", err)
	}
	if !has {
		t.Fatal("accepted identity was not persisted")
	}
	if !sameDeviceIdentity(loaded, *result.DeviceIdentity) {
		t.Fatalf("loaded identity mismatch: got=%#v want=%#v", loaded, *result.DeviceIdentity)
	}
}

func TestLoadEnrollmentStateReturnsStoredIdentityAsNotReady(t *testing.T) {
	ctx := context.Background()
	storePath := filepath.Join(t.TempDir(), "enrollment-state")
	store := NewFileEnrollmentStateStore(storePath)

	request := validEnrollmentRequestPayload()
	requestPayload, err := EncodeEnrollmentRequestPayload(request)
	if err != nil {
		t.Fatal(err)
	}
	result := validEnrollmentResultPayloadBoundToRequest(request, requestPayload, EnrollmentStatusAccepted)
	now := result.DeviceIdentity.CredentialNotBefore + 10

	if _, err := ApplyVerifiedEnrollmentResult(ctx, request, result, store, now); err != nil {
		t.Fatalf("ApplyVerifiedEnrollmentResult: %v", err)
	}
	loaded, err := LoadEnrollmentState(ctx, store, now)
	if err != nil {
		t.Fatalf("LoadEnrollmentState: %v", err)
	}
	if loaded.Ready {
		t.Fatal("loaded identity was marked ready before freshness")
	}
	if !sameDeviceIdentity(loaded.Identity, *result.DeviceIdentity) {
		t.Fatalf("loaded identity mismatch: got=%#v want=%#v", loaded.Identity, *result.DeviceIdentity)
	}

	entries, err := os.ReadDir(filepath.Dir(storePath))
	if err != nil {
		t.Fatalf("ReadDir: %v", err)
	}
	for _, entry := range entries {
		if entry.Type().IsRegular() && entry.Name() != filepath.Base(storePath) && filepath.HasPrefix(entry.Name(), "nbsr-enrollment-state-") {
			t.Fatalf("temporary file leaked: %s", entry.Name())
		}
	}
}

func TestApplyVerifiedEnrollmentResultRejectsNonSuccessStatus(t *testing.T) {
	ctx := context.Background()
	store := NewMemoryEnrollmentStateStore()

	request := validEnrollmentRequestPayload()
	requestPayload, err := EncodeEnrollmentRequestPayload(request)
	if err != nil {
		t.Fatal(err)
	}
	for _, status := range []EnrollmentStatus{
		EnrollmentStatusRejected,
		EnrollmentStatusInvalid,
		EnrollmentStatusRequestConflict,
		EnrollmentStatusExpired,
	} {
		result := validEnrollmentResultPayload(status, requestPayload)
		now := uint64(time.Now().Unix()) + 1
		if _, err := ApplyVerifiedEnrollmentResult(ctx, request, result, store, now); !errors.Is(err, ErrTerminalEnrollment) {
			t.Fatalf("status %s error = %v, want ErrTerminalEnrollment", status, err)
		}
		if _, has, err := store.Load(ctx); err != nil {
			t.Fatalf("Store.Load after %s: %v", status, err)
		} else if has {
			t.Fatalf("state exists after non-success status %s", status)
		}
	}
}

func TestApplyVerifiedEnrollmentResultRejectsBindingFailures(t *testing.T) {
	ctx := context.Background()
	request := validEnrollmentRequestPayload()
	requestPayload, err := EncodeEnrollmentRequestPayload(request)
	if err != nil {
		t.Fatal(err)
	}

	base := validEnrollmentResultPayloadBoundToRequest(request, requestPayload, EnrollmentStatusAccepted)
	store := NewMemoryEnrollmentStateStore()
	now := base.DeviceIdentity.CredentialNotBefore + 10
	if _, err := ApplyVerifiedEnrollmentResult(ctx, request, base, store, now); err != nil {
		t.Fatalf("initial enroll: %v", err)
	}

	tests := []struct {
		name   string
		mutate func(*identity.DeviceIdentity)
	}{
		{name: "source operator", mutate: func(d *identity.DeviceIdentity) { d.SourceOperatorID = "other.operator" }},
		{name: "signing key id", mutate: func(d *identity.DeviceIdentity) { d.SigningKey.ID = [32]byte{0x99} }},
		{name: "signing key generation", mutate: func(d *identity.DeviceIdentity) { d.SigningKey.Generation = 9 }},
		{name: "signing key thumbprint", mutate: func(d *identity.DeviceIdentity) { d.SigningKey.Thumbprint[0] = 0x99 }},
		{name: "credential generation", mutate: func(d *identity.DeviceIdentity) { d.CredentialGeneration = 9 }},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			result := base
			mutated := *base.DeviceIdentity
			tc.mutate(&mutated)
			result.DeviceIdentity = &mutated
			if _, err := ApplyVerifiedEnrollmentResult(ctx, request, result, store, now); !errors.Is(err, ErrBindingMismatch) {
				t.Fatalf("error = %v, want ErrBindingMismatch", err)
			}
			loaded, has, err := store.Load(ctx)
			if err != nil {
				t.Fatalf("Store.Load: %v", err)
			}
			if !has || !sameDeviceIdentity(loaded, *base.DeviceIdentity) {
				t.Fatalf("existing identity was replaced: has=%v loaded=%#v", has, loaded)
			}
		})
	}
}

func TestApplyVerifiedEnrollmentResultRejectsUntrustedOrMalformedResult(t *testing.T) {
	ctx := context.Background()
	request := validEnrollmentRequestPayload()
	requestPayload, err := EncodeEnrollmentRequestPayload(request)
	if err != nil {
		t.Fatal(err)
	}
	store := NewMemoryEnrollmentStateStore()

	if _, err := ApplyVerifiedEnrollmentResult(ctx, request, EnrollmentResultPayload{
		ProtocolVersion: 1,
		RequestID:       request.RequestID,
		RequestDigest:   EnrollmentRequestDigest(requestPayload),
		Status:          EnrollmentStatusAccepted,
	}, store, request.DeadlineUnix); err == nil || !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("unverified result error = %v, want ErrInvalidAuthority", err)
	}
	if _, has, err := store.Load(ctx); err != nil {
		t.Fatalf("Store.Load: %v", err)
	} else if has {
		t.Fatal("untrusted result persisted")
	}

	malformed := validEnrollmentResultPayloadBoundToRequest(request, requestPayload, EnrollmentStatusAccepted)
	malformed.DeviceIdentity.CredentialExpiresAt = 0
	if _, err := ApplyVerifiedEnrollmentResult(ctx, request, malformed, store, uint64(time.Now().Unix())+10); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("malformed identity error = %v, want ErrInvalidAuthority", err)
	}
}

func TestApplyVerifiedEnrollmentResultRejectsInvalidLifetimeAndExistingIdentity(t *testing.T) {
	ctx := context.Background()
	request := validEnrollmentRequestPayload()
	requestPayload, err := EncodeEnrollmentRequestPayload(request)
	if err != nil {
		t.Fatal(err)
	}
	store := NewFileEnrollmentStateStore(filepath.Join(t.TempDir(), "enrollment-state"))

	expired := validEnrollmentResultPayloadBoundToRequest(request, requestPayload, EnrollmentStatusAccepted)
	if _, err := ApplyVerifiedEnrollmentResult(ctx, request, expired, store, expired.DeviceIdentity.CredentialExpiresAt+1); !errors.Is(err, ErrExpired) {
		t.Fatalf("expired identity error = %v, want ErrExpired", err)
	}
	if _, has, err := store.Load(ctx); err != nil {
		t.Fatalf("Store.Load before initial store: %v", err)
	} else if has {
		t.Fatal("invalid lifetime was persisted")
	}

	valid := validEnrollmentResultPayloadBoundToRequest(request, requestPayload, EnrollmentStatusAccepted)
	if _, err := ApplyVerifiedEnrollmentResult(ctx, request, valid, store, valid.DeviceIdentity.CredentialNotBefore+1); err != nil {
		t.Fatalf("initial store: %v", err)
	}
	if _, err := ApplyVerifiedEnrollmentResult(ctx, request, valid, store, valid.DeviceIdentity.CredentialNotBefore+2); !errors.Is(err, ErrTerminalEnrollment) {
		t.Fatalf("replacement error = %v, want ErrTerminalEnrollment", err)
	}
}

func TestApplyVerifiedEnrollmentResultSimulatedWriteFailureLeavesNoPersistedIdentity(t *testing.T) {
	ctx := context.Background()
	request := validEnrollmentRequestPayload()
	requestPayload, err := EncodeEnrollmentRequestPayload(request)
	if err != nil {
		t.Fatal(err)
	}
	store := NewFileEnrollmentStateStore(filepath.Join(t.TempDir(), "enrollment-state"))
	previous := store.write
	simulate := errors.New("simulated failure")
	store.write = func(string, []byte) error { return simulate }
	t.Cleanup(func() { store.write = previous })

	result := validEnrollmentResultPayloadBoundToRequest(request, requestPayload, EnrollmentStatusAccepted)
	now := result.DeviceIdentity.CredentialNotBefore + 1
	_, err = ApplyVerifiedEnrollmentResult(ctx, request, result, store, now)
	if !errors.Is(err, simulate) {
		t.Fatalf("simulated write failure error = %v, want %v", err, simulate)
	}
	if _, has, err := store.Load(ctx); err != nil {
		t.Fatalf("Store.Load after failed write: %v", err)
	} else if has {
		t.Fatal("identity persisted after failed write")
	}
}

func TestLoadEnrollmentStateRejectsMalformedPersistedState(t *testing.T) {
	ctx := context.Background()
	storePath := filepath.Join(t.TempDir(), "enrollment-state")
	store := NewFileEnrollmentStateStore(storePath)
	if err := os.WriteFile(storePath, []byte{0x00, 0x01, 0x02}, 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := LoadEnrollmentState(ctx, store, uint64(time.Now().Unix())); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("malformed state load error = %v, want ErrInvalidAuthority", err)
	}
}

func TestLoadEnrollmentStateRejectsTamperedStateSignature(t *testing.T) {
	ctx := context.Background()
	storePath := filepath.Join(t.TempDir(), "enrollment-state")
	store := NewFileEnrollmentStateStore(storePath)

	request := validEnrollmentRequestPayload()
	requestPayload, err := EncodeEnrollmentRequestPayload(request)
	if err != nil {
		t.Fatal(err)
	}
	result := validEnrollmentResultPayloadBoundToRequest(request, requestPayload, EnrollmentStatusAccepted)
	now := result.DeviceIdentity.CredentialNotBefore + 10

	if _, err := ApplyVerifiedEnrollmentResult(ctx, request, result, store, now); err != nil {
		t.Fatalf("ApplyVerifiedEnrollmentResult: %v", err)
	}

	state, err := os.ReadFile(storePath)
	if err != nil {
		t.Fatalf("ReadFile(%s): %v", storePath, err)
	}
	decoded, err := decodeCBORExact(state, defaultCBORLimits())
	if err != nil {
		t.Fatalf("decode envelope: %v", err)
	}
	envelope, ok := decoded.(map[uint64]any)
	if !ok {
		t.Fatalf("decode envelope type %T", decoded)
	}
	signature, ok := envelope[enrollmentStateEnvelopeFieldSignature].([]byte)
	if !ok || len(signature) == 0 {
		t.Fatalf("missing signature field: %v", signature)
	}
	tamperedSignature := append([]byte(nil), signature...)
	tamperedSignature[0] ^= 0x55
	envelope[enrollmentStateEnvelopeFieldSignature] = tamperedSignature
	tampered, err := encodeCBOR(envelope)
	if err != nil {
		t.Fatalf("encodeCBOR tampered envelope: %v", err)
	}
	if err := os.WriteFile(storePath, tampered, 0o600); err != nil {
		t.Fatalf("WriteFile(%s): %v", storePath, err)
	}
	if _, err := LoadEnrollmentState(ctx, store, now); !errors.Is(err, ErrSignatureFailure) {
		t.Fatalf("load after signature tamper error = %v, want %v", err, ErrSignatureFailure)
	}
}

func TestLoadEnrollmentStateRejectsUnsignedEnvelopeState(t *testing.T) {
	ctx := context.Background()
	storePath := filepath.Join(t.TempDir(), "enrollment-state")
	store := NewFileEnrollmentStateStore(storePath)

	request := validEnrollmentRequestPayload()
	requestPayload, err := EncodeEnrollmentRequestPayload(request)
	if err != nil {
		t.Fatal(err)
	}
	result := validEnrollmentResultPayloadBoundToRequest(request, requestPayload, EnrollmentStatusAccepted)
	now := result.DeviceIdentity.CredentialNotBefore + 10

	if _, err := ApplyVerifiedEnrollmentResult(ctx, request, result, store, now); err != nil {
		t.Fatalf("ApplyVerifiedEnrollmentResult: %v", err)
	}
	state, err := os.ReadFile(storePath)
	if err != nil {
		t.Fatalf("ReadFile(%s): %v", storePath, err)
	}
	decoded, err := decodeCBORExact(state, defaultCBORLimits())
	if err != nil {
		t.Fatalf("decode envelope: %v", err)
	}
	envelope, ok := decoded.(map[uint64]any)
	if !ok {
		t.Fatalf("decode envelope type %T", decoded)
	}
	delete(envelope, enrollmentStateEnvelopeFieldSignature)
	unsigned, err := encodeCBOR(envelope)
	if err != nil {
		t.Fatalf("encodeCBOR unsigned envelope: %v", err)
	}
	if err := os.WriteFile(storePath, unsigned, 0o600); err != nil {
		t.Fatalf("WriteFile(%s): %v", storePath, err)
	}
	if _, err := LoadEnrollmentState(ctx, store, now); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("load unsigned envelope error = %v, want %v", err, ErrInvalidAuthority)
	}
}

func TestLoadEnrollmentStateRejectsOversizedStateBlob(t *testing.T) {
	ctx := context.Background()
	storePath := filepath.Join(t.TempDir(), "enrollment-state")
	store := NewFileEnrollmentStateStore(storePath)
	oversized := make([]byte, maxEnrollmentStateBytes+1)
	for i := range oversized {
		oversized[i] = byte(i)
	}
	if err := os.WriteFile(storePath, oversized, 0o600); err != nil {
		t.Fatalf("WriteFile(%s): %v", storePath, err)
	}
	if _, err := LoadEnrollmentState(ctx, store, uint64(time.Now().Unix())); !errors.Is(err, ErrInvalidAuthority) {
		t.Fatalf("oversized load error = %v, want %v", err, ErrInvalidAuthority)
	}
}

func TestLoadEnrollmentStateRejectsCorruptedIntegrityKeyBlob(t *testing.T) {
	ctx := context.Background()
	storePath := filepath.Join(t.TempDir(), "enrollment-state")
	store := NewFileEnrollmentStateStore(storePath)

	request := validEnrollmentRequestPayload()
	requestPayload, err := EncodeEnrollmentRequestPayload(request)
	if err != nil {
		t.Fatal(err)
	}
	result := validEnrollmentResultPayloadBoundToRequest(request, requestPayload, EnrollmentStatusAccepted)
	now := result.DeviceIdentity.CredentialNotBefore + 10
	if _, err := ApplyVerifiedEnrollmentResult(ctx, request, result, store, now); err != nil {
		t.Fatalf("ApplyVerifiedEnrollmentResult: %v", err)
	}

	keyPath := filepath.Join(filepath.Dir(storePath), enrollmentStateIntegrityKeyName)
	keyBlob, err := os.ReadFile(keyPath)
	if err != nil {
		t.Fatalf("ReadFile(%s): %v", keyPath, err)
	}
	if len(keyBlob) == 0 {
		t.Fatal("empty integrity key blob")
	}
	keyBlob[len(keyBlob)-1] ^= 0x5a
	if err := os.WriteFile(keyPath, keyBlob, 0o600); err != nil {
		t.Fatalf("WriteFile(%s): %v", keyPath, err)
	}
	err = nil
	if _, err = LoadEnrollmentState(ctx, store, now); !errors.Is(err, ErrInvalidAuthority) && !errors.Is(err, ErrStoragePathRejected) {
		t.Fatalf("corrupted integrity key load error = %v, want %v or %v", err, ErrInvalidAuthority, ErrStoragePathRejected)
	}
}

func TestApplyVerifiedEnrollmentResultRejectsDuplicateIdentityStoreAttempts(t *testing.T) {
	ctx := context.Background()
	request := validEnrollmentRequestPayload()
	requestPayload, err := EncodeEnrollmentRequestPayload(request)
	if err != nil {
		t.Fatal(err)
	}
	store := NewFileEnrollmentStateStore(filepath.Join(t.TempDir(), "enrollment-state"))

	result := validEnrollmentResultPayloadBoundToRequest(request, requestPayload, EnrollmentStatusAccepted)
	now := result.DeviceIdentity.CredentialNotBefore + 10
	if _, err := ApplyVerifiedEnrollmentResult(ctx, request, result, store, now); err != nil {
		t.Fatalf("initial persist: %v", err)
	}
	duplicate := validEnrollmentResultPayloadBoundToRequest(request, requestPayload, EnrollmentStatusAccepted)
	if _, err := ApplyVerifiedEnrollmentResult(ctx, request, duplicate, store, now); !errors.Is(err, ErrTerminalEnrollment) {
		t.Fatalf("duplicate identity write error = %v, want %v", err, ErrTerminalEnrollment)
	}
}

func TestApplyVerifiedEnrollmentResultSimulatedCrashDuringWriteKeepsStoreUnmodified(t *testing.T) {
	ctx := context.Background()
	request := validEnrollmentRequestPayload()
	requestPayload, err := EncodeEnrollmentRequestPayload(request)
	if err != nil {
		t.Fatal(err)
	}
	storePath := filepath.Join(t.TempDir(), "enrollment-state")
	store := NewFileEnrollmentStateStore(storePath)
	result := validEnrollmentResultPayloadBoundToRequest(request, requestPayload, EnrollmentStatusAccepted)
	now := result.DeviceIdentity.CredentialNotBefore + 10
	payload, err := store.buildEnrollmentStateEnvelope(*result.DeviceIdentity)
	if err != nil {
		t.Fatalf("buildEnrollmentStateEnvelope: %v", err)
	}

	crashPath := filepath.Join(filepath.Dir(storePath), "nbsr-enrollment-state-orphan")
	crashErr := errors.New("simulated write crash")
	store.write = func(string, []byte) error {
		if err := os.WriteFile(crashPath, payload, 0o600); err != nil {
			return err
		}
		return crashErr
	}
	if _, err := ApplyVerifiedEnrollmentResult(ctx, request, result, store, now); !errors.Is(err, crashErr) {
		t.Fatalf("write crash error = %v, want %v", err, crashErr)
	}
	if _, has, err := store.Load(ctx); err != nil {
		t.Fatalf("Store.Load after crash: %v", err)
	} else if has {
		t.Fatal("identity persisted after crash")
	}
	store.write = nil
	if _, err := ApplyVerifiedEnrollmentResult(ctx, request, result, store, now); err != nil {
		t.Fatalf("recovered write: %v", err)
	}
	if _, has, err := store.Load(ctx); err != nil {
		t.Fatalf("Store.Load after recovery: %v", err)
	} else if !has {
		t.Fatal("identity not persisted after recovery")
	}
}

func TestLoadEnrollmentStateReturnsErrUnknownWhenStateAbsent(t *testing.T) {
	ctx := context.Background()
	store := NewMemoryEnrollmentStateStore()
	if _, err := LoadEnrollmentState(ctx, store, uint64(time.Now().Unix())); !errors.Is(err, ErrUnknownIdentity) {
		t.Fatalf("absent state error = %v, want ErrUnknownIdentity", err)
	}
}

func sameDeviceIdentity(left, right identity.DeviceIdentity) bool {
	return left.ID == right.ID &&
		left.SourceOperatorID == right.SourceOperatorID &&
		left.CredentialGeneration == right.CredentialGeneration &&
		left.CredentialNotBefore == right.CredentialNotBefore &&
		left.CredentialExpiresAt == right.CredentialExpiresAt &&
		left.SigningKey == right.SigningKey
}

func validEnrollmentResultPayloadBoundToRequest(request EnrollmentRequestPayload, requestPayload []byte, status EnrollmentStatus) EnrollmentResultPayload {
	payload := validEnrollmentResultPayload(status, requestPayload)
	if payload.DeviceIdentity == nil {
		return payload
	}
	payload.DeviceIdentity.SourceOperatorID = request.SourceOperator
	payload.DeviceIdentity.SigningKey.ID = request.DeviceSigningKey.KeyID
	payload.DeviceIdentity.SigningKey.Purpose = request.DeviceSigningKey.Purpose
	payload.DeviceIdentity.SigningKey.Generation = request.DeviceSigningKey.Generation
	payload.DeviceIdentity.SigningKey.Thumbprint = request.DeviceSigningKey.Thumbprint
	payload.DeviceIdentity.CredentialGeneration = request.DeviceSigningKey.Generation
	return payload
}
