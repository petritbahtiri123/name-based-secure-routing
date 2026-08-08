from __future__ import annotations

from hashlib import sha256

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from nbsr.federation.ownership import derive_service_id
from nbsr.protocol.cbor import decode_deterministic
from nbsr.protocol.cose import verify_sign1
from nbsr.protocol.errors import ErrorCode
from scripts.core_v02_vectors.fixtures import FIXTURES
from scripts.performance.authorities import build_authority_set, write_authority_set


def test_twenty_services_have_independent_signed_authority() -> None:
    services = build_authority_set(20)
    assert len(services) == 20
    assert len({service.canonical_name for service in services}) == 20
    assert len({service.channel_id for service in services}) == 20
    assert len({service.route_id for service in services}) == 20
    assert len({sha256(service.route_grant).digest() for service in services}) == 20
    assert len({sha256(service.federation_context).digest() for service in services}) == 20
    for index, service in enumerate(services):
        expected_name = f"service-{index:02d}.example"
        assert service.canonical_name == expected_name
        verified = verify_sign1(
            service.route_grant,
            {FIXTURES.kid: Ed25519PrivateKey.from_private_bytes(FIXTURES.route_grant_seed).public_key()},
            ErrorCode.NBSR_E_GRANT_INVALID,
        )
        claims = decode_deterministic(verified.payload)
        context = decode_deterministic(service.federation_context)
        assert claims[3] == expected_name
        assert context[35] == derive_service_id(b"S" * 32, expected_name)
        assert context[40][1] == expected_name


def test_route_open_binding_is_specific_to_each_service() -> None:
    first, second = build_authority_set(2)
    first_body = decode_deterministic(first.route_open_body)
    second_body = decode_deterministic(second.route_open_body)
    assert first_body[1] == first.channel_id
    assert first_body[2] == first.route_grant
    assert first_body[8][4] == sha256(first.route_grant).digest()
    assert first_body[8][5] == sha256(first.federation_context).digest()
    assert first_body[8][4] != second_body[8][4]
    assert first_body[8][5] != second_body[8][5]


def test_authority_set_is_written_without_ambiguous_overwrite(tmp_path) -> None:
    write_authority_set(tmp_path, 2)
    before = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    write_authority_set(tmp_path, 2)
    after = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert after == before
    assert (tmp_path / "00" / "name.txt").read_text(encoding="ascii") == "service-00.example\n"
    assert (tmp_path / "01" / "route-open-body.cbor").read_bytes()
    assert sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*") if path.is_file()) == [
        "00/channel-id.bin", "00/destination.cose", "00/federation-context.cbor", "00/grant-digest.bin", "00/name.txt", "00/request-id.bin", "00/route-id.bin", "00/route-open-body.cbor", "00/source.cose",
        "01/channel-id.bin", "01/destination.cose", "01/federation-context.cbor", "01/grant-digest.bin", "01/name.txt", "01/request-id.bin", "01/route-id.bin", "01/route-open-body.cbor", "01/source.cose",
    ]
