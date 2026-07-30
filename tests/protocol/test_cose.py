from __future__ import annotations

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
import pytest

from nbsr.protocol.cbor import DEFAULT_LIMITS, decode_deterministic, encode_deterministic
from nbsr.protocol.cose import sign1, verify_sign1
from nbsr.protocol.errors import ProtocolViolation
from nbsr.protocol.registry import ErrorCode


PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
KID = b"test-owner-key"
PAYLOAD = b"\xa1\x00\x01"


def raw_sign1(
    protected_map: object,
    *,
    unprotected: object = None,
    payload: object = PAYLOAD,
    signature: object | None = None,
    tag: bytes = b"\xd2",
) -> bytes:
    protected = encode_deterministic(protected_map)
    if signature is None:
        signature = PRIVATE_KEY.sign(encode_deterministic(["Signature1", protected, b"", payload]))
    body = [
        protected,
        {} if unprotected is None else unprotected,
        payload,
        signature,
    ]
    return tag + encode_deterministic(body)


def assert_record_rejected(message: bytes) -> None:
    with pytest.raises(ProtocolViolation) as rejected:
        verify_sign1(
            message,
            {KID: PRIVATE_KEY.public_key()},
            ErrorCode.NBSR_E_RECORD_UNTRUSTED,
        )

    assert rejected.value.code is ErrorCode.NBSR_E_RECORD_UNTRUSTED


def test_sign1_is_deterministic_and_uses_exact_tagged_profile() -> None:
    first = sign1(PAYLOAD, KID, PRIVATE_KEY)
    second = sign1(PAYLOAD, KID, PRIVATE_KEY)

    assert first == second
    assert first[:1] == b"\xd2"
    body = decode_deterministic(first[1:])
    assert len(body) == 4
    assert decode_deterministic(body[0]) == {1: -8, 4: KID}
    assert body[1] == {}
    assert body[2] == PAYLOAD
    assert len(body[3]) == 64


@pytest.mark.parametrize(
    "failure_code",
    (
        ErrorCode.NBSR_E_RECORD_UNTRUSTED,
        ErrorCode.NBSR_E_GRANT_INVALID,
    ),
)
def test_verify_sign1_uses_only_caller_trust_context(
    failure_code: ErrorCode,
) -> None:
    message = sign1(PAYLOAD, KID, PRIVATE_KEY)
    verified = verify_sign1(
        message,
        {KID: PRIVATE_KEY.public_key()},
        failure_code,
    )

    assert verified.payload == PAYLOAD
    assert verified.kid == KID

    with pytest.raises(ProtocolViolation) as missing:
        verify_sign1(message, {}, failure_code)
    assert missing.value.code is failure_code


def test_verify_sign1_rejects_invalid_failure_context() -> None:
    message = sign1(PAYLOAD, KID, PRIVATE_KEY)

    with pytest.raises(ValueError):
        verify_sign1(
            message,
            {KID: PRIVATE_KEY.public_key()},
            ErrorCode.NBSR_E_INTERNAL,
        )


@pytest.mark.parametrize(
    "message",
    (
        raw_sign1({4: KID}),
        raw_sign1({1: -7, 4: KID}),
        raw_sign1({1: True, 4: KID}),
        raw_sign1({1: -8, 4: KID, 2: [1]}),
        raw_sign1({4: KID}, unprotected={1: -8}),
        raw_sign1({1: -8, 4: KID}, unprotected={4: KID}),
        raw_sign1({1: -8, 4: KID}, unprotected=[]),
        raw_sign1({1: -8, 4: b""}),
        raw_sign1({1: -8, 4: b"k" * 65}),
        raw_sign1({1: -8, 4: "text-kid"}),
        raw_sign1({1: -8, 4: 7}),
        raw_sign1({1: -8, 4: KID}, payload=None),
        raw_sign1({1: -8, 4: KID}, signature=b""),
        raw_sign1({1: -8, 4: KID}, signature=b"\x00" * 63),
        raw_sign1({1: -8, 4: KID}, signature=b"\x00" * 65),
        raw_sign1({1: -8, 4: KID}, tag=b"\xd1"),
        raw_sign1({1: -8, 4: KID}) + b"\x00",
        b"\xd2" + encode_deterministic([]),
        b"\xd2" + encode_deterministic([encode_deterministic({1: -8, 4: KID}), {}, PAYLOAD]),
    ),
)
def test_rejects_non_profile_headers_and_structures(message: bytes) -> None:
    assert_record_rejected(message)


def test_rejects_missing_tag_and_non_array_body() -> None:
    valid = raw_sign1({1: -8, 4: KID})

    assert_record_rejected(valid[1:])
    assert_record_rejected(b"\xd2" + encode_deterministic({}))


def test_rejects_duplicate_protected_header_key() -> None:
    duplicate_alg = b"\xa3\x01\x27\x01\x27\x04\x4e" + KID
    signature = PRIVATE_KEY.sign(encode_deterministic(["Signature1", duplicate_alg, b"", PAYLOAD]))
    message = b"\xd2" + encode_deterministic([duplicate_alg, {}, PAYLOAD, signature])

    assert_record_rejected(message)


def test_rejects_non_ed25519_public_key() -> None:
    message = sign1(PAYLOAD, KID, PRIVATE_KEY)

    with pytest.raises(ProtocolViolation) as rejected:
        verify_sign1(
            message,
            {KID: X25519PrivateKey.generate().public_key()},
            ErrorCode.NBSR_E_GRANT_INVALID,
        )

    assert rejected.value.code is ErrorCode.NBSR_E_GRANT_INVALID


def test_rejects_tampered_protected_payload_and_signature() -> None:
    valid = sign1(PAYLOAD, KID, PRIVATE_KEY)
    protected, unprotected, payload, signature = decode_deterministic(valid[1:])

    changed_protected = encode_deterministic({1: -8, 4: b"other-key"})
    assert_record_rejected(b"\xd2" + encode_deterministic([changed_protected, unprotected, payload, signature]))
    assert_record_rejected(b"\xd2" + encode_deterministic([protected, unprotected, b"changed", signature]))
    changed_signature = signature[:-1] + bytes((signature[-1] ^ 1,))
    assert_record_rejected(b"\xd2" + encode_deterministic([protected, unprotected, payload, changed_signature]))


def test_preserves_cbor_over_capacity_error() -> None:
    oversized = b"\xd2" + b"\x00" * (DEFAULT_LIMITS.max_total_bytes + 1)

    with pytest.raises(ProtocolViolation) as rejected:
        verify_sign1(
            oversized,
            {KID: PRIVATE_KEY.public_key()},
            ErrorCode.NBSR_E_RECORD_UNTRUSTED,
        )

    assert rejected.value.code is ErrorCode.NBSR_E_OVER_CAPACITY


@pytest.mark.parametrize(
    ("payload", "kid", "key"),
    (
        (bytearray(PAYLOAD), KID, PRIVATE_KEY),
        (PAYLOAD, b"", PRIVATE_KEY),
        (PAYLOAD, b"k" * 65, PRIVATE_KEY),
        (PAYLOAD, KID, X25519PrivateKey.generate()),
    ),
)
def test_sign1_rejects_non_profile_local_inputs(
    payload: object,
    kid: object,
    key: object,
) -> None:
    with pytest.raises(ProtocolViolation) as rejected:
        sign1(payload, kid, key)  # type: ignore[arg-type]

    assert rejected.value.code is ErrorCode.NBSR_E_PROFILE_UNSUPPORTED
