"""Bounded local registry for signed NBSR ServiceRecord state."""

from collections.abc import Mapping
from hashlib import sha256
from threading import RLock

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from nbsr.protocol import (
    ErrorCode,
    ProtocolViolation,
    Revocation,
    RevocationTargetType,
    ServiceRecord,
    decode_revocation,
    decode_service_record,
    require_kid,
    verify_sign1,
)
from nbsr.protocol.fields import require_canonical_name


_MAX_RECORDS = 1_000_000


def _copy_trust_context(
    keys: Mapping[bytes, Ed25519PublicKey],
    *,
    field_name: str,
) -> dict[bytes, Ed25519PublicKey]:
    if not isinstance(keys, Mapping):
        raise TypeError(f"{field_name} must be a mapping")

    copied: dict[bytes, Ed25519PublicKey] = {}
    for kid, key in keys.items():
        if type(kid) is not bytes or not 1 <= len(kid) <= 64:
            raise ValueError(f"{field_name} contains an invalid kid")
        if not isinstance(key, Ed25519PublicKey):
            raise TypeError(f"{field_name} contains an invalid public key")
        copied[kid] = key
    return copied


class SignedServiceRegistry:
    """Validate and retain bounded signed service metadata."""

    def __init__(
        self,
        record_keys: Mapping[bytes, Ed25519PublicKey],
        revocation_keys: Mapping[bytes, Ed25519PublicKey],
        *,
        max_records: int = 1_024,
    ) -> None:
        if type(max_records) is not int or not 1 <= max_records <= _MAX_RECORDS:
            raise ValueError("max_records must be an integer from 1 to 1000000")

        self._record_keys = _copy_trust_context(record_keys, field_name="record_keys")
        self._revocation_keys = _copy_trust_context(
            revocation_keys,
            field_name="revocation_keys",
        )
        self._max_records = max_records
        self._records: dict[str, ServiceRecord] = {}
        self._record_sequences: dict[str, int] = {}
        self._revocation_generations: dict[bytes, int] = {}
        self._revocations: dict[str, Revocation] = {}
        self._lock = RLock()

    def install_record(self, cose_sign1: bytes, *, now: int) -> ServiceRecord:
        verified = verify_sign1(
            cose_sign1,
            self._record_keys,
            ErrorCode.NBSR_E_RECORD_UNTRUSTED,
        )
        record = decode_service_record(verified.payload)
        require_kid(
            verified,
            record.owner_key_id,
            ErrorCode.NBSR_E_RECORD_UNTRUSTED,
        )
        record.require_valid_at(now)

        with self._lock:
            record.require_newer_than(
                self._record_sequences.get(record.canonical_name, 0),
            )
            if record.canonical_name not in self._records and len(self._records) >= self._max_records:
                raise ProtocolViolation(
                    ErrorCode.NBSR_E_OVER_CAPACITY,
                    "ServiceRecord registry capacity exceeded",
                )
            self._records[record.canonical_name] = record
            self._record_sequences[record.canonical_name] = record.sequence
        return record

    def apply_revocation(self, cose_sign1: bytes, *, now: int) -> Revocation:
        verified = verify_sign1(
            cose_sign1,
            self._revocation_keys,
            ErrorCode.NBSR_E_RECORD_UNTRUSTED,
        )
        revocation = decode_revocation(verified.payload)
        require_kid(
            verified,
            revocation.issuer_key_id,
            ErrorCode.NBSR_E_RECORD_UNTRUSTED,
        )
        revocation.require_valid_at(now)
        if revocation.target_type is not RevocationTargetType.SERVICE_RECORD:
            raise ProtocolViolation(
                ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
                "Unsupported revocation target type",
            )

        with self._lock:
            revocation.require_newer_generation(
                self._revocation_generations.get(revocation.issuer_key_id, 0),
            )
            names = [name for name in self._records if sha256(name.encode("ascii")).digest() == revocation.target_id]
            if len(names) != 1:
                raise ProtocolViolation(
                    ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
                    "Revocation target does not identify one accepted ServiceRecord",
                )
            canonical_name = names[0]
            revocation.require_target_sequence(
                self._records[canonical_name].sequence,
            )
            self._revocations[canonical_name] = revocation
            self._revocation_generations[revocation.issuer_key_id] = revocation.generation
        return revocation

    def resolve(self, canonical_name: str, *, now: int) -> ServiceRecord | None:
        checked_name = require_canonical_name(canonical_name)
        with self._lock:
            record = self._records.get(checked_name)
            revocation = self._revocations.get(checked_name)
            if record is None:
                return None
            record.require_valid_at(now)
            if (
                revocation is not None
                and now >= revocation.not_before
                and (revocation.expires_at is None or now < revocation.expires_at)
                and (revocation.target_sequence is None or revocation.target_sequence == record.sequence)
            ):
                raise ProtocolViolation(
                    ErrorCode.NBSR_E_RECORD_REVOKED,
                    "ServiceRecord is revoked",
                )
            return record
