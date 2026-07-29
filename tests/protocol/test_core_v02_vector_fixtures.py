from __future__ import annotations

import ipaddress

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from scripts.core_v02_vectors.fixtures import FIXTURES


def _public_key(seed: bytes) -> bytes:
    return Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def test_public_fixture_registry_is_exact_and_test_only() -> None:
    assert FIXTURES.route_grant_seed.hex() == ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
    assert FIXTURES.route_grant_public_key.hex() == ("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
    assert FIXTURES.session_seed.hex() == ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb")
    assert FIXTURES.session_public_key.hex() == ("3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c")
    assert FIXTURES.canonical_name == "service.example.test"
    assert FIXTURES.service_id == "service.example"
    assert FIXTURES.request_id == bytes(range(0x00, 0x10))
    assert FIXTURES.session_id == bytes(range(0x10, 0x20))
    assert FIXTURES.route_id == bytes(range(0x20, 0x30))
    assert FIXTURES.lease_id == bytes(range(0x30, 0x40))
    assert FIXTURES.channel_id == bytes(range(0x40, 0x50))
    assert FIXTURES.unique_nonce == bytes(range(0x50, 0x60))
    assert FIXTURES.client_nonce == bytes(range(0x60, 0x80))
    assert FIXTURES.edge_nonce == bytes(range(0x80, 0xA0))
    assert FIXTURES.not_before == 1_893_455_940
    assert FIXTURES.opened_at == 1_893_456_000
    assert FIXTURES.expires_at == 1_893_456_300
    assert FIXTURES.port == 8443
    assert FIXTURES.record_sequence == 42
    assert FIXTURES.kid == b"nbsr-test-route-grant-key"


def test_public_keys_are_derived_from_the_fixed_public_test_seeds() -> None:
    assert _public_key(FIXTURES.route_grant_seed) == FIXTURES.route_grant_public_key
    assert _public_key(FIXTURES.session_seed) == FIXTURES.session_public_key


def test_textual_fixture_values_are_not_ip_addresses() -> None:
    for value in (
        FIXTURES.source_operator_id,
        FIXTURES.source_edge_id,
        FIXTURES.destination_operator_id,
        FIXTURES.destination_edge_id,
        FIXTURES.service_id,
        FIXTURES.canonical_name,
        FIXTURES.transport,
    ):
        try:
            ipaddress.ip_address(value)
        except ValueError:
            continue
        raise AssertionError(f"fixture value must not be an IP address: {value}")
