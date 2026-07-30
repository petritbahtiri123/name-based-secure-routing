from __future__ import annotations

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nbsr.protocol.cbor import decode_deterministic
from nbsr.protocol.cose import sign1


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
