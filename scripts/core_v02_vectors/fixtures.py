from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def _derive_public_key(seed: bytes) -> bytes:
    return Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


@dataclass(frozen=True, slots=True)
class VectorFixtures:
    route_grant_seed: bytes
    route_grant_public_key: bytes
    session_seed: bytes
    session_public_key: bytes
    source_operator_id: str
    source_edge_id: str
    destination_operator_id: str
    destination_edge_id: str
    service_id: str
    canonical_name: str
    transport: str
    port: int
    record_sequence: int
    request_id: bytes
    session_id: bytes
    route_id: bytes
    lease_id: bytes
    channel_id: bytes
    unique_nonce: bytes
    client_nonce: bytes
    edge_nonce: bytes
    not_before: int
    opened_at: int
    expires_at: int
    kid: bytes
    name_digest: bytes
    policy_hash: bytes
    client_session_key_thumbprint: bytes


_ROUTE_GRANT_SEED = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
_SESSION_SEED = bytes.fromhex("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb")
_SESSION_PUBLIC_KEY = _derive_public_key(_SESSION_SEED)
_CANONICAL_NAME = "service.example.test"

FIXTURES = VectorFixtures(
    route_grant_seed=_ROUTE_GRANT_SEED,
    route_grant_public_key=_derive_public_key(_ROUTE_GRANT_SEED),
    session_seed=_SESSION_SEED,
    session_public_key=_SESSION_PUBLIC_KEY,
    source_operator_id="source.operator",
    source_edge_id="source.edge",
    destination_operator_id="destination.operator",
    destination_edge_id="destination.edge",
    service_id="service.example",
    canonical_name=_CANONICAL_NAME,
    transport="tcp",
    port=8443,
    record_sequence=42,
    request_id=bytes(range(0x00, 0x10)),
    session_id=bytes(range(0x10, 0x20)),
    route_id=bytes(range(0x20, 0x30)),
    lease_id=bytes(range(0x30, 0x40)),
    channel_id=bytes(range(0x40, 0x50)),
    unique_nonce=bytes(range(0x50, 0x60)),
    client_nonce=bytes(range(0x60, 0x80)),
    edge_nonce=bytes(range(0x80, 0xA0)),
    not_before=1_893_455_940,
    opened_at=1_893_456_000,
    expires_at=1_893_456_300,
    kid=b"nbsr-test-route-grant-key",
    name_digest=sha256(_CANONICAL_NAME.encode("ascii")).digest(),
    policy_hash=sha256(b"nbsr-test-policy-v2").digest(),
    client_session_key_thumbprint=sha256(_SESSION_PUBLIC_KEY).digest(),
)
