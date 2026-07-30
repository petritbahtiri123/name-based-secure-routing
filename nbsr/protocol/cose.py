from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from nbsr.protocol.cbor import DEFAULT_LIMITS, decode_deterministic, encode_deterministic
from nbsr.protocol.errors import ProtocolViolation
from nbsr.protocol.registry import ErrorCode


_TAG_18 = b"\xd2"
_ALGORITHM_EDDSA = -8
_VERIFICATION_CODES = frozenset(
    {
        ErrorCode.NBSR_E_RECORD_UNTRUSTED,
        ErrorCode.NBSR_E_GRANT_INVALID,
    }
)


@dataclass(frozen=True, slots=True)
class VerifiedSign1:
    payload: bytes
    kid: bytes


def _profile_error() -> ProtocolViolation:
    return ProtocolViolation(
        ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
        "Unsupported COSE Sign1 profile",
    )


def _require_kid_value(kid: object) -> bytes:
    if type(kid) is not bytes or not 1 <= len(kid) <= 64:
        raise _profile_error()
    return kid


def _verification_error(code: ErrorCode) -> ProtocolViolation:
    return ProtocolViolation(code, "Invalid COSE Sign1")


def sign1(
    payload: bytes,
    kid: bytes,
    key: Ed25519PrivateKey,
) -> bytes:
    if type(payload) is not bytes or not isinstance(key, Ed25519PrivateKey):
        raise _profile_error()
    checked_kid = _require_kid_value(kid)
    protected = encode_deterministic({1: _ALGORITHM_EDDSA, 4: checked_kid})
    to_be_signed = encode_deterministic(["Signature1", protected, b"", payload])
    signature = key.sign(to_be_signed)
    return _TAG_18 + encode_deterministic([protected, {}, payload, signature])


def verify_sign1(
    message: bytes,
    keys: Mapping[bytes, Ed25519PublicKey],
    failure_code: ErrorCode,
) -> VerifiedSign1:
    if type(failure_code) is not ErrorCode or failure_code not in _VERIFICATION_CODES:
        raise ValueError("unsupported COSE verification failure code")
    if not isinstance(keys, Mapping):
        raise TypeError("keys must be a mapping")

    try:
        if type(message) is bytes and len(message) > DEFAULT_LIMITS.max_total_bytes:
            raise ProtocolViolation(
                ErrorCode.NBSR_E_OVER_CAPACITY,
                "COSE resource limit exceeded",
            )
        if type(message) is not bytes or not message.startswith(_TAG_18):
            raise _verification_error(failure_code)
        body = decode_deterministic(message[1:])
        if type(body) is not list or len(body) != 4:
            raise _verification_error(failure_code)
        protected, unprotected, payload, signature = body
        if (
            type(protected) is not bytes
            or unprotected != {}
            or type(payload) is not bytes
            or type(signature) is not bytes
            or len(signature) != 64
        ):
            raise _verification_error(failure_code)
        protected_map = decode_deterministic(protected)
        if (
            type(protected_map) is not dict
            or set(protected_map) != {1, 4}
            or type(protected_map[1]) is not int
            or protected_map[1] != _ALGORITHM_EDDSA
        ):
            raise _verification_error(failure_code)
        kid = _require_kid_value(protected_map[4])
        key = keys.get(kid)
        if not isinstance(key, Ed25519PublicKey):
            raise _verification_error(failure_code)
        to_be_signed = encode_deterministic(["Signature1", protected, b"", payload])
        key.verify(signature, to_be_signed)
        return VerifiedSign1(payload=payload, kid=kid)
    except ProtocolViolation as exc:
        if exc.code is ErrorCode.NBSR_E_OVER_CAPACITY:
            raise
        if exc.code is failure_code:
            raise
        raise _verification_error(failure_code) from exc
    except (InvalidSignature, KeyError, TypeError, ValueError) as exc:
        raise _verification_error(failure_code) from exc


def require_kid(
    verified: VerifiedSign1,
    expected_kid: bytes,
    failure_code: ErrorCode,
) -> None:
    if type(failure_code) is not ErrorCode or failure_code not in _VERIFICATION_CODES:
        raise ValueError("unsupported COSE verification failure code")
    if not isinstance(verified, VerifiedSign1) or type(expected_kid) is not bytes or verified.kid != expected_kid:
        raise _verification_error(failure_code)
