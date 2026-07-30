from __future__ import annotations

from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nbsr.protocol.cbor import encode_deterministic
from nbsr.protocol.errors import ProtocolViolation
from nbsr.protocol.registry import ErrorCode


_TAG_18 = b"\xd2"
_ALGORITHM_EDDSA = -8


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
