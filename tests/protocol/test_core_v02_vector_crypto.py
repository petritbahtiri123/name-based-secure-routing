from __future__ import annotations

from hashlib import sha256

import pytest

from nbsr.protocol.cbor import decode_deterministic, encode_deterministic
from nbsr.protocol.errors import ProtocolViolation
from nbsr.protocol.registry import ErrorCode
from scripts.core_v02_vectors.crypto import (
    encode_cose_sign1,
    encode_route_open_transcript,
    sign_route_open,
    verify_cose_sign1,
    verify_route_open,
)
from scripts.core_v02_vectors.fixtures import FIXTURES


def _assert_error(code: ErrorCode, call: object) -> None:
    with pytest.raises(ProtocolViolation) as exc_info:
        call()  # type: ignore[operator]
    assert exc_info.value.code is code


def _valid_cose() -> tuple[bytes, bytes]:
    payload = encode_deterministic({0: 1, 1: FIXTURES.route_id})
    return (
        payload,
        encode_cose_sign1(payload, FIXTURES.route_grant_seed, FIXTURES.kid),
    )


def _cose_parts(wire: bytes) -> list[object]:
    value = decode_deterministic(wire[1:])
    assert isinstance(value, list)
    return value


def _rewire(parts: list[object], *, tagged: bool = True) -> bytes:
    return (b"\xd2" if tagged else b"") + encode_deterministic(parts)


def test_cose_sign1_shape_is_tagged_deterministic_and_verifiable() -> None:
    payload, wire = _valid_cose()

    assert wire.startswith(b"\xd2")
    assert encode_cose_sign1(payload, FIXTURES.route_grant_seed, FIXTURES.kid) == wire
    protected, unprotected, embedded, signature = _cose_parts(wire)
    assert decode_deterministic(protected) == {1: -8, 4: FIXTURES.kid}
    assert unprotected == {}
    assert embedded == payload
    assert isinstance(signature, bytes) and len(signature) == 64
    assert (
        verify_cose_sign1(
            wire,
            FIXTURES.route_grant_public_key,
            FIXTURES.kid,
        )
        == payload
    )


@pytest.mark.parametrize(
    ("name", "mutate"),
    [
        ("missing-tag", lambda parts: _rewire(parts, tagged=False)),
        (
            "wrong-algorithm",
            lambda parts: _rewire([encode_deterministic({1: -7, 4: FIXTURES.kid}), *parts[1:]]),
        ),
        (
            "missing-kid",
            lambda parts: _rewire([encode_deterministic({1: -8}), *parts[1:]]),
        ),
        (
            "text-kid",
            lambda parts: _rewire([encode_deterministic({1: -8, 4: "kid"}), *parts[1:]]),
        ),
        (
            "empty-kid",
            lambda parts: _rewire([encode_deterministic({1: -8, 4: b""}), *parts[1:]]),
        ),
        (
            "oversized-kid",
            lambda parts: _rewire([encode_deterministic({1: -8, 4: b"x" * 65}), *parts[1:]]),
        ),
        (
            "detached-payload",
            lambda parts: _rewire([parts[0], parts[1], None, parts[3]]),
        ),
        (
            "nonempty-unprotected",
            lambda parts: _rewire([parts[0], {4: b"x"}, *parts[2:]]),
        ),
    ],
)
def test_cose_rejects_profile_shape_errors(name: str, mutate: object) -> None:
    del name
    _, wire = _valid_cose()
    invalid = mutate(_cose_parts(wire))  # type: ignore[operator]

    _assert_error(
        ErrorCode.NBSR_E_PROFILE_UNSUPPORTED,
        lambda: verify_cose_sign1(
            invalid,
            FIXTURES.route_grant_public_key,
            FIXTURES.kid,
        ),
    )


def test_cose_rejects_wrong_expected_kid_key_and_signature() -> None:
    _, wire = _valid_cose()
    _assert_error(
        ErrorCode.NBSR_E_GRANT_INVALID,
        lambda: verify_cose_sign1(
            wire,
            FIXTURES.route_grant_public_key,
            b"other-kid",
        ),
    )
    _assert_error(
        ErrorCode.NBSR_E_GRANT_INVALID,
        lambda: verify_cose_sign1(
            wire,
            FIXTURES.session_public_key,
            FIXTURES.kid,
        ),
    )
    parts = _cose_parts(wire)
    signature = bytearray(parts[3])
    signature[32] ^= 1
    parts[3] = bytes(signature)
    _assert_error(
        ErrorCode.NBSR_E_GRANT_INVALID,
        lambda: verify_cose_sign1(
            _rewire(parts),
            FIXTURES.route_grant_public_key,
            FIXTURES.kid,
        ),
    )


def _transcript() -> bytes:
    return encode_route_open_transcript(
        protocol_version=2,
        session_id=FIXTURES.session_id,
        request_id=FIXTURES.request_id,
        channel_id=FIXTURES.channel_id,
        route_id=FIXTURES.route_id,
        service_id=FIXTURES.service_id,
        destination_edge_id=FIXTURES.destination_edge_id,
        edge_nonce=FIXTURES.edge_nonce,
        transport=FIXTURES.transport,
        port=FIXTURES.port,
        route_grant_digest=sha256(b"route-grant").digest(),
        opened_at=FIXTURES.opened_at,
    )


def test_route_open_transcript_is_exact_and_signature_verifies() -> None:
    route_grant_digest = sha256(b"route-grant").digest()
    transcript = _transcript()

    assert decode_deterministic(transcript) == [
        "NBSR-ROUTE-OPEN-v2",
        2,
        FIXTURES.session_id,
        FIXTURES.request_id,
        FIXTURES.channel_id,
        FIXTURES.route_id,
        FIXTURES.service_id,
        FIXTURES.destination_edge_id,
        FIXTURES.edge_nonce,
        "tcp",
        8443,
        route_grant_digest,
        FIXTURES.opened_at,
    ]
    signature = sign_route_open(transcript, FIXTURES.session_seed)
    assert len(signature) == 64
    verify_route_open(
        transcript,
        signature,
        FIXTURES.session_public_key,
    )


def test_route_open_proof_rejects_wrong_key_mutation_and_signature_length() -> None:
    transcript = _transcript()
    signature = sign_route_open(transcript, FIXTURES.session_seed)

    _assert_error(
        ErrorCode.NBSR_E_PROOF_INVALID,
        lambda: verify_route_open(
            transcript,
            signature,
            FIXTURES.route_grant_public_key,
        ),
    )
    mutated = bytearray(transcript)
    mutated[-1] ^= 1
    _assert_error(
        ErrorCode.NBSR_E_PROOF_INVALID,
        lambda: verify_route_open(
            bytes(mutated),
            signature,
            FIXTURES.session_public_key,
        ),
    )
    _assert_error(
        ErrorCode.NBSR_E_PROOF_INVALID,
        lambda: verify_route_open(
            transcript,
            signature[:-1],
            FIXTURES.session_public_key,
        ),
    )
