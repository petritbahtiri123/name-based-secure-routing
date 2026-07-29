from __future__ import annotations

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from nbsr.protocol.cbor import decode_deterministic, encode_deterministic
from nbsr.protocol.errors import ProtocolViolation
from nbsr.protocol.fields import (
    require_bytes,
    require_port,
    require_text_id,
    require_timestamp,
    require_uint,
)
from nbsr.protocol.registry import ErrorCode


def _profile_error(message: str) -> ProtocolViolation:
    return ProtocolViolation(ErrorCode.NBSR_E_PROFILE_UNSUPPORTED, message)


def _grant_error(message: str) -> ProtocolViolation:
    return ProtocolViolation(ErrorCode.NBSR_E_GRANT_INVALID, message)


def _proof_error(message: str) -> ProtocolViolation:
    return ProtocolViolation(ErrorCode.NBSR_E_PROOF_INVALID, message)


def _private_key(seed: bytes) -> Ed25519PrivateKey:
    try:
        return Ed25519PrivateKey.from_private_bytes(require_bytes(seed, minimum=32, maximum=32))
    except (ProtocolViolation, ValueError) as exc:
        raise _profile_error("Invalid Ed25519 test seed") from exc


def encode_cose_sign1(payload: bytes, seed: bytes, kid: bytes) -> bytes:
    valid_payload = require_bytes(
        payload,
        minimum=1,
        maximum=32_768,
        message="Invalid COSE payload",
    )
    valid_kid = require_bytes(
        kid,
        minimum=1,
        maximum=64,
        message="Invalid COSE kid",
    )
    protected = encode_deterministic({1: -8, 4: valid_kid})
    sig_structure = encode_deterministic(["Signature1", protected, b"", valid_payload])
    signature = _private_key(seed).sign(sig_structure)
    return b"\xd2" + encode_deterministic([protected, {}, valid_payload, signature])


def verify_cose_sign1(
    wire: bytes,
    public_key: bytes,
    expected_kid: bytes,
) -> bytes:
    if not isinstance(wire, bytes) or not wire.startswith(b"\xd2"):
        raise _profile_error("COSE Sign1 tag 18 is required")
    try:
        value = decode_deterministic(wire[1:])
    except ProtocolViolation as exc:
        raise _profile_error("Malformed COSE Sign1") from exc
    if not isinstance(value, list) or len(value) != 4:
        raise _profile_error("Invalid COSE Sign1 shape")
    protected, unprotected, payload, signature = value
    if not isinstance(protected, bytes):
        raise _profile_error("Invalid protected header")
    try:
        protected_map = decode_deterministic(protected)
    except ProtocolViolation as exc:
        raise _profile_error("Invalid protected header") from exc
    if not isinstance(protected_map, dict) or set(protected_map) != {1, 4}:
        raise _profile_error("Invalid protected header keys")
    if protected_map[1] != -8 or type(protected_map[1]) is not int:
        raise _profile_error("COSE algorithm must be EdDSA")
    kid = protected_map[4]
    if not isinstance(kid, bytes) or not 1 <= len(kid) <= 64:
        raise _profile_error("COSE kid must be an opaque byte string")
    if not isinstance(unprotected, dict) or unprotected:
        raise _profile_error("COSE unprotected map must be empty")
    if not isinstance(payload, bytes):
        raise _profile_error("Detached COSE payload is not supported")
    if not isinstance(signature, bytes) or len(signature) != 64:
        raise _profile_error("Invalid COSE signature shape")
    if not isinstance(expected_kid, bytes) or kid != expected_kid:
        raise _grant_error("COSE kid does not match the trust context")
    if not isinstance(public_key, bytes) or len(public_key) != 32:
        raise _grant_error("Invalid RouteGrant issuer key")
    sig_structure = encode_deterministic(["Signature1", protected, b"", payload])
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            signature,
            sig_structure,
        )
    except (InvalidSignature, ValueError) as exc:
        raise _grant_error("Invalid RouteGrant signature") from exc
    return payload


def encode_route_open_transcript(
    *,
    protocol_version: int,
    session_id: bytes,
    request_id: bytes,
    channel_id: bytes,
    route_id: bytes,
    service_id: str,
    destination_edge_id: str,
    edge_nonce: bytes,
    transport: str,
    port: int,
    route_grant_digest: bytes,
    opened_at: int,
) -> bytes:
    version = require_uint(
        protocol_version,
        minimum=2,
        maximum=2,
        message="Invalid Core v0.2 proof version",
    )
    valid_transport = require_text_id(
        transport,
        message="Invalid proof transport",
    )
    if valid_transport != "tcp":
        raise _profile_error("Unsupported proof transport")
    return encode_deterministic(
        [
            "NBSR-ROUTE-OPEN-v2",
            version,
            require_bytes(session_id, minimum=16, maximum=16),
            require_bytes(request_id, minimum=16, maximum=16),
            require_bytes(channel_id, minimum=16, maximum=16),
            require_bytes(route_id, minimum=16, maximum=16),
            require_text_id(service_id),
            require_text_id(destination_edge_id),
            require_bytes(edge_nonce, minimum=32, maximum=32),
            valid_transport,
            require_port(port),
            require_bytes(route_grant_digest, minimum=32, maximum=32),
            require_timestamp(opened_at),
        ]
    )


def sign_route_open(transcript: bytes, seed: bytes) -> bytes:
    valid_transcript = require_bytes(
        transcript,
        minimum=1,
        maximum=32_768,
        message="Invalid Route Open transcript",
    )
    return _private_key(seed).sign(valid_transcript)


def verify_route_open(
    transcript: bytes,
    signature: bytes,
    public_key: bytes,
) -> None:
    if (
        not isinstance(transcript, bytes)
        or not transcript
        or not isinstance(signature, bytes)
        or len(signature) != 64
        or not isinstance(public_key, bytes)
        or len(public_key) != 32
    ):
        raise _proof_error("Invalid Route Open proof shape")
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            signature,
            transcript,
        )
    except (InvalidSignature, ValueError) as exc:
        raise _proof_error("Invalid Route Open proof") from exc
