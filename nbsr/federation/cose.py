from __future__ import annotations

from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from nbsr.federation.delegation import DelegationRecord
from nbsr.federation.fields import FederationValidationError, KeyAuthorizationRecord, OperatorRegistryRecord
from nbsr.federation.ownership import NameOwnershipRecord
from nbsr.federation.registry import AuthorityClass, KeyLifecycle, KeyPurpose, ObjectType
from nbsr.protocol.cose import verify_sign1
from nbsr.protocol.errors import ProtocolViolation
from nbsr.protocol.registry import ErrorCode


@dataclass(frozen=True, slots=True)
class FederationAuthority:
    kid: bytes
    public_key: Ed25519PublicKey
    operator_id: bytes
    purpose: KeyPurpose
    lifecycle: KeyLifecycle
    generation: int
    sequence: int
    not_before: int
    expires_at: int
    revoked: bool


def _reject(message: str) -> None:
    raise FederationValidationError(message)


def verify_federation_sign1(
    message: bytes,
    authority: FederationAuthority,
    expected_object_type: ObjectType,
    now: int,
    *,
    expected_payload: bytes | None = None,
    expected_key_purpose: KeyPurpose = KeyPurpose.REGISTRY_SIGNING,
    current_record: NameOwnershipRecord | DelegationRecord | None = None,
    transition: object | None = None,
) -> OperatorRegistryRecord | KeyAuthorizationRecord | NameOwnershipRecord | DelegationRecord:
    """Verify the approved single-Sign1 Task 2 boundary.

    Multi-authority registrar/witness and recovery threshold packaging is not
    represented here because the Development Profile does not freeze such a
    transport container.
    """
    if not isinstance(authority, FederationAuthority):
        _reject("Federation authority context is invalid")
    if type(expected_object_type) is not ObjectType or type(now) is not int:
        _reject("Federation verification context is invalid")
    if (
        type(authority.kid) is not bytes
        or not 1 <= len(authority.kid) <= 64
        or not isinstance(authority.public_key, Ed25519PublicKey)
        or type(authority.operator_id) is not bytes
        or len(authority.operator_id) != 32
        or type(authority.generation) is not int
        or authority.generation < 1
        or type(authority.sequence) is not int
        or authority.sequence < 1
        or type(authority.revoked) is not bool
    ):
        _reject("Federation signer identity or lineage is invalid")
    if authority.lifecycle is not KeyLifecycle.ACTIVE or authority.revoked:
        _reject("Federation signer is not active")
    if not authority.not_before <= now <= authority.expires_at:
        _reject("Federation signer is outside its validity window")

    try:
        verified = verify_sign1(message, {authority.kid: authority.public_key}, ErrorCode.NBSR_E_RECORD_UNTRUSTED)
    except ProtocolViolation as exc:
        raise FederationValidationError("Federation COSE Sign1 verification failed") from exc
    if expected_payload is not None and verified.payload != expected_payload:
        _reject("Federation Sign1 payload binding failed")

    if expected_object_type is ObjectType.KeyAuthorizationRecord:
        if authority.purpose is not KeyPurpose.IDENTITY_ROOT:
            _reject("Key authorization requires the identity-root purpose")
        record: OperatorRegistryRecord | KeyAuthorizationRecord = KeyAuthorizationRecord.from_bytes(
            verified.payload, context={"expected_key_purpose": expected_key_purpose.value}
        )
        if record.operator_id != authority.operator_id:
            _reject("signer and payload Operator IDs differ")
        authorizer = record._payload[37]
        if (
            authorizer[1] != 1
            or authorizer[2] != authority.operator_id
            or authorizer[3] != authority.kid
            or authorizer[4] != authority.operator_id
        ):
            _reject("payload authorizing authority does not identify the exact signer")
        record.require_valid_at(now)
        return record

    if expected_object_type is ObjectType.OperatorRegistryRecord:
        _reject("registrar plus witness Sign1-set packaging is not frozen")
    if expected_object_type is ObjectType.NameOwnershipRecord:
        if authority.purpose is not KeyPurpose.NAME_OWNERSHIP or expected_key_purpose is not KeyPurpose.NAME_OWNERSHIP:
            _reject("name ownership requires the exact name-ownership purpose")
        ownership = NameOwnershipRecord.from_bytes(verified.payload)
        signer = ownership._payload[3]
        if (
            signer[1] != AuthorityClass.NAME_OWNER
            or signer[2] != authority.operator_id
            or signer[3] != authority.kid
            or signer[4] != authority.operator_id
        ):
            _reject("ownership issuer does not identify the exact signer")
        ownership.require_valid_at(now)
        if 8 in ownership._payload and current_record is None:
            _reject("non-genesis ownership verification requires current_record")
        if current_record is not None:
            if not isinstance(current_record, NameOwnershipRecord):
                _reject("ownership current-record context is invalid")
            ownership.require_newer_than(current_record, transition=transition)
        return ownership
    if expected_object_type is ObjectType.DelegationRecord:
        if authority.purpose is not KeyPurpose.DELEGATION or expected_key_purpose is not KeyPurpose.DELEGATION:
            _reject("delegation requires the exact delegation purpose")
        delegation = DelegationRecord.from_bytes(verified.payload)
        signer = delegation._payload[32]
        if (
            signer[1] not in {AuthorityClass.NAME_OWNER, AuthorityClass.DELEGATE}
            or signer[2] != authority.operator_id
            or signer[3] != authority.kid
            or signer[4] != authority.operator_id
        ):
            _reject("delegator does not identify the exact signer")
        delegation.require_valid_at(now)
        if 8 in delegation._payload and current_record is None:
            _reject("non-genesis delegation verification requires current_record")
        if current_record is not None:
            if not isinstance(current_record, DelegationRecord):
                _reject("delegation current-record context is invalid")
            delegation.require_newer_than(current_record, recovery_transition=transition)
        return delegation
    _reject("object type is outside the approved Task 2 COSE surface")
