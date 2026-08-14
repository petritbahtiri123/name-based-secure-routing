package identity

import (
	"errors"
	"sync"
	"testing"
	"time"
)

func TestPurposeSeparatedReferencesRejectReuse(t *testing.T) {
	device := keyRef(1, PurposeDeviceACPRequest, 1)
	if _, err := NewMemoryRegistry(deviceIdentity(device), nil,
		[]TSProofKey{{TSGeneration: 7, Key: device}}, localKey()); !errors.Is(err, ErrInvalidKeyPurpose) {
		t.Fatal(err)
	}
}

func TestPurposeSeparatedReferencesRejectKeyIDReuseAcrossRoles(t *testing.T) {
	sharedID := byte32(1)
	device := keyRef(1, PurposeDeviceACPRequest, 1)
	ts := keyRef(2, PurposeTSProof, 7)
	local := localKey()
	tests := []struct {
		name   string
		device DeviceIdentity
		ts     []TSProofKey
		local  LocalStateIntegrityKey
	}{
		{
			name:   "device and TS proof",
			device: deviceIdentity(device),
			ts:     []TSProofKey{{TSGeneration: 7, Key: KeyRef{ID: sharedID, Purpose: PurposeTSProof, Generation: 7, Thumbprint: ts.Thumbprint}}},
			local:  local,
		},
		{
			name:   "device and local state",
			device: deviceIdentity(device),
			local:  LocalStateIntegrityKey{Key: KeyRef{ID: sharedID, Purpose: PurposeLocalStateIntegrity, Generation: 1, Thumbprint: local.Key.Thumbprint}},
		},
		{
			name:   "TS proof and local state",
			device: deviceIdentity(keyRef(9, PurposeDeviceACPRequest, 1)),
			ts:     []TSProofKey{{TSGeneration: 7, Key: ts}},
			local:  LocalStateIntegrityKey{Key: KeyRef{ID: ts.ID, Purpose: PurposeLocalStateIntegrity, Generation: 1, Thumbprint: local.Key.Thumbprint}},
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if _, err := NewMemoryRegistry(tt.device, nil, tt.ts, tt.local); !errors.Is(err, ErrInvalidKeyPurpose) {
				t.Fatalf("error = %v, want errors.Is(_, %v)", err, ErrInvalidKeyPurpose)
			}
		})
	}
}

func TestIdentityRejectsMissingDevice(t *testing.T) {
	if _, err := NewMemoryRegistry(DeviceIdentity{}, nil, nil, localKey()); !errors.Is(err, ErrInvalidIdentity) {
		t.Fatal(err)
	}
}

func TestIdentityRejectsInvalidKeyReferences(t *testing.T) {
	validDevice := keyRef(1, PurposeDeviceACPRequest, 3)
	tests := []struct {
		name   string
		device DeviceIdentity
		ts     []TSProofKey
		local  LocalStateIntegrityKey
		want   error
	}{
		{"device wrong purpose", deviceIdentity(keyRef(1, PurposeTSProof, 3)), nil, localKey(), ErrInvalidKeyPurpose},
		{"ts wrong purpose", deviceIdentity(validDevice), []TSProofKey{{TSGeneration: 7, Key: keyRef(2, PurposeLocalStateIntegrity, 7)}}, localKey(), ErrInvalidKeyPurpose},
		{"local wrong purpose", deviceIdentity(validDevice), nil, LocalStateIntegrityKey{Key: keyRef(3, PurposeTSProof, 1)}, ErrInvalidKeyPurpose},
		{"zero key id", deviceIdentity(KeyRef{Purpose: PurposeDeviceACPRequest, Generation: 3}), nil, localKey(), ErrInvalidIdentity},
		{"zero key purpose", deviceIdentity(KeyRef{ID: byte32(1), Generation: 3}), nil, localKey(), ErrInvalidKeyPurpose},
		{"zero key generation", deviceIdentity(KeyRef{ID: byte32(1), Purpose: PurposeDeviceACPRequest}), nil, localKey(), ErrInvalidGeneration},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if _, err := NewMemoryRegistry(tt.device, nil, tt.ts, tt.local); !errors.Is(err, tt.want) {
				t.Fatalf("error = %v, want errors.Is(_, %v)", err, tt.want)
			}
		})
	}
}

func TestTSProofRejectsDuplicateAndMismatchedGeneration(t *testing.T) {
	device := deviceIdentity(keyRef(1, PurposeDeviceACPRequest, 1))
	if _, err := NewMemoryRegistry(device, nil, []TSProofKey{
		{TSGeneration: 7, Key: keyRef(2, PurposeTSProof, 7)},
		{TSGeneration: 7, Key: keyRef(3, PurposeTSProof, 7)},
	}, alternateLocalKey()); !errors.Is(err, ErrInvalidGeneration) {
		t.Fatal(err)
	}
	if _, err := NewMemoryRegistry(device, nil, []TSProofKey{
		{TSGeneration: 7, Key: keyRef(2, PurposeTSProof, 8)},
	}, alternateLocalKey()); !errors.Is(err, ErrInvalidGeneration) {
		t.Fatal(err)
	}
}

func TestIdentityRejectsCredentialExpiryAtBoundary(t *testing.T) {
	device := deviceIdentity(keyRef(1, PurposeDeviceACPRequest, 1))
	device.CredentialExpiresAt = uint64(time.Now().Unix())
	if _, err := NewMemoryRegistry(device, nil, nil, localKey()); !errors.Is(err, ErrExpiredIdentity) {
		t.Fatal(err)
	}
}

func TestWorkloadAbsenceReturnsTypedUnknownIdentity(t *testing.T) {
	registry, err := NewMemoryRegistry(deviceIdentity(keyRef(1, PurposeDeviceACPRequest, 1)), nil, nil, localKey())
	if err != nil {
		t.Fatal(err)
	}
	if _, err := registry.Workload(byte32(9)); !errors.Is(err, ErrUnknownIdentity) {
		t.Fatal(err)
	}
}

func TestRegistryReadOnlyLookupsAreConcurrentSafe(t *testing.T) {
	workload := WorkloadPolicyContext{
		SubjectDigest:       byte32(4),
		PolicyGeneration:    1,
		CredentialExpiresAt: uint64(time.Now().Add(time.Hour).Unix()),
		PolicyExpiresAt:     uint64(time.Now().Add(time.Hour).Unix()),
	}
	registry, err := NewMemoryRegistry(deviceIdentity(keyRef(1, PurposeDeviceACPRequest, 1)), []WorkloadPolicyContext{workload}, []TSProofKey{{TSGeneration: 7, Key: keyRef(2, PurposeTSProof, 7)}}, localKey())
	if err != nil {
		t.Fatal(err)
	}
	var group sync.WaitGroup
	for range 32 {
		group.Add(1)
		go func() {
			defer group.Done()
			if _, err := registry.Device(); err != nil {
				t.Error(err)
			}
			if _, err := registry.Workload(workload.SubjectDigest); err != nil {
				t.Error(err)
			}
			if _, err := registry.TSProof(7); err != nil {
				t.Error(err)
			}
			if _, err := registry.LocalStateIntegrity(); err != nil {
				t.Error(err)
			}
		}()
	}
	group.Wait()
}

func byte32(value byte) (result [32]byte) {
	result[0] = value
	return result
}

func keyRef(id byte, purpose Purpose, generation uint64) KeyRef {
	return KeyRef{ID: byte32(id), Purpose: purpose, Generation: generation, Thumbprint: byte32(id + 32)}
}

func deviceIdentity(key KeyRef) DeviceIdentity {
	now := uint64(time.Now().Unix())
	return DeviceIdentity{
		ID:                   byte32(7),
		SourceOperatorID:     "source.example",
		CredentialGeneration: 1,
		CredentialNotBefore:  now - 1,
		CredentialExpiresAt:  now + 3600,
		SigningKey:           key,
	}
}

func localKey() LocalStateIntegrityKey {
	return LocalStateIntegrityKey{Key: keyRef(3, PurposeLocalStateIntegrity, 1)}
}

func alternateLocalKey() LocalStateIntegrityKey {
	return LocalStateIntegrityKey{Key: keyRef(8, PurposeLocalStateIntegrity, 1)}
}
