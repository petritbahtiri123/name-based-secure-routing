from __future__ import annotations

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from nbsr.protocol.cbor import decode_deterministic
from nbsr.protocol.cose import sign1, verify_sign1
from nbsr.protocol.errors import ProtocolViolation
from nbsr.protocol.registry import ErrorCode


PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
KID = b"test-owner-key"
PAYLOAD = b"\xa1\x00\x01"


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
