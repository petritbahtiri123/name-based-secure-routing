from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from nbsr.protocol.cbor import decode_deterministic, encode_deterministic
from nbsr.federation.identity import OperatorId
from nbsr.federation.ownership import derive_service_id
from scripts.wp8_f75_vectors.package import (
    F75VectorError,
    build_package,
    build_mutation_vectors,
    build_positive_vector,
    decode_f75_body,
    verify_package,
    validate_f75_route_authority,
    validate_f75_authority_proof,
    _authority_proof_bytes,
    validate_f75_route_time,
    write_package,
)


EXPECTED_CONTEXT_DIGEST = "586b97a3d9539c420adcf8cfbc87fdf3c08e258cb512783436499dfba37f0699"
EXPECTED_ROUTE_GRANT_DIGEST = "f6090054a832c559b28bba386f78616557ce13af39e1a95d3dff9e1f7ba96860"
EXPECTED_BINDING_HEX = (
    "a600010101020103766e6273722d66656465726174696f6e2d6465762d7631"
    "045820f6090054a832c559b28bba386f78616557ce13af39e1a95d3dff9e1f7ba96860"
    "055820586b97a3d9539c420adcf8cfbc87fdf3c08e258cb512783436499dfba37f0699"
)
EXPECTED_TRANSCRIPT_HEX = (
    "90734e4253522d4645442d524f5554452d4f50454e020284010101"
    "766e6273722d66656465726174696f6e2d6465762d7631"
    "50101112131415161718191a1b1c1d1e1f"
    "50000102030405060708090a0b0c0d0e10"
    "50404142434445464748494a4b4c4d4e4f"
    "50202122232425262728292a2b2c2d2e2f"
    "7064657374696e6174696f6e2e65646765"
    "5820808182838485868788898a8b8c8d8e8f909192939495969798999a9b9c9d9e9f"
    "63746370"
    "6f736572766963652e6578616d706c65"
    "1920fb"
    "5820f6090054a832c559b28bba386f78616557ce13af39e1a95d3dff9e1f7ba96860"
    "1a70dbd880"
    "5820586b97a3d9539c420adcf8cfbc87fdf3c08e258cb512783436499dfba37f0699"
)
EXPECTED_SIGNATURE_HEX = (
    "d14c077add7654643b87fda22f6574ca0ba69b145d1c50717013c433491c31d010cb0eb7b389d85b25dddc0f36a83840aaa30bb4b9e17a9351a17be37a3b520e"
)
EXPECTED_MUTATIONS = {
    "domain-separator",
    "core-version",
    "body-version",
    "binding-version",
    "extension-id",
    "extension-version",
    "profile-id",
    "session-id",
    "request-id",
    "channel-id",
    "route-id",
    "destination-edge",
    "edge-nonce",
    "transport",
    "service",
    "port",
    "route-grant-digest",
    "opened-at",
    "federation-context-digest",
}


def test_positive_f75_literals_are_specification_authored() -> None:
    vector = build_positive_vector()

    assert vector["route_grant_digest"] == EXPECTED_ROUTE_GRANT_DIGEST
    assert vector["federation_context_digest"] == EXPECTED_CONTEXT_DIGEST
    assert vector["binding_hex"] == EXPECTED_BINDING_HEX
    assert vector["transcript_hex"] == EXPECTED_TRANSCRIPT_HEX
    assert vector["signature_hex"] == EXPECTED_SIGNATURE_HEX
    body = bytes.fromhex(vector["body_hex"])
    assert len(body) == 718
    assert set(decode_deterministic(body)) == set(range(9))
    assert len(bytes.fromhex(vector["transcript_hex"])) == 265
    assert vector["transcript_item_count"] == 16


def test_f75_route_grant_uses_normative_federation_operator_text_and_service_identity() -> None:
    package = build_package()
    cose = decode_deterministic(package["route-grant.cose"][1:])
    claims = decode_deterministic(cose[2])
    context_payload = decode_deterministic(package["federation-context.cbor"])
    assert claims[4] == OperatorId(b"S" * 32).text
    assert claims[6] == OperatorId(b"D" * 32).text
    assert claims[3] == "service.example"
    assert context_payload[35] == derive_service_id(b"S" * 32, claims[3])


def test_f75_service_port_is_8443_across_context_grant_and_route_open() -> None:
    package = build_package()
    body = decode_deterministic(package["route-open-body.cbor"])
    context_wire = package["federation-context.cbor"]
    context = decode_deterministic(context_wire)
    claims = decode_deterministic(decode_deterministic(body[2][1:])[2])
    assert context[40][7] == [[8443, 8443]]
    assert claims[9] == [8443]
    assert (body[4], body[5]) == ("tcp", 8443)
    validate_f75_route_authority(body, context_wire)


def test_f75_authority_proof_is_bound_to_the_derived_service() -> None:
    package = build_package()
    context_wire = package["federation-context.cbor"]
    context = decode_deterministic(context_wire)
    proof_wire = _authority_proof_bytes()
    assert context[35].hex() == "63af737542a51a0f0d5ba43ca83224fcbad57af696971e6141a412d542310d6d"
    assert context[36].hex() == "1f8665e01d478677f401d291c1bed02f36d70a8d9e69b9582706d23d2ffca000"
    validate_f75_authority_proof(context_wire, proof_wire)

    old = dict(context)
    old[36] = bytes.fromhex("f1aca34bedb3572de2a65675d4f54e22ccb601e68611afefb5c5c94e5c246255")
    with pytest.raises(F75VectorError):
        validate_f75_authority_proof(encode_deterministic(old), proof_wire)

    wrong_service = dict(context)
    wrong_service[35] = b"V" * 32
    with pytest.raises(F75VectorError):
        validate_f75_authority_proof(encode_deterministic(wrong_service), proof_wire)

    changed_proof = bytearray(proof_wire)
    changed_proof[-1] ^= 1
    with pytest.raises(F75VectorError):
        validate_f75_authority_proof(context_wire, bytes(changed_proof))


def test_f75_route_uses_one_core_and_federation_time_domain() -> None:
    package = build_package()
    body = decode_deterministic(package["route-open-body.cbor"])
    context_wire = package["federation-context.cbor"]
    proof_wire = _authority_proof_bytes()
    context = decode_deterministic(context_wire)
    proof = decode_deterministic(proof_wire)
    assert (context[9], body[6], context[41]) == (1_893_455_940, 1_893_456_000, 1_893_456_300)
    assert proof[42] == 1_893_456_300
    validate_f75_route_time(body, context_wire, proof_wire)

    expired_context = {**context, 41: body[6] - 1}
    with pytest.raises(F75VectorError):
        validate_f75_route_time(body, encode_deterministic(expired_context), proof_wire)
    future_context = {**context, 9: body[6] + 1}
    with pytest.raises(F75VectorError):
        validate_f75_route_time(body, encode_deterministic(future_context), proof_wire)
    expired_proof = {**proof, 42: body[6] - 1}
    with pytest.raises(F75VectorError):
        validate_f75_route_time(body, context_wire, encode_deterministic(expired_proof))

    sign1_body = decode_deterministic(body[2][1:])
    claims = decode_deterministic(sign1_body[2])
    claims[12] = body[6] - 1
    sign1_body[2] = encode_deterministic(claims)
    expired_grant = {**body, 2: b"\xd2" + encode_deterministic(sign1_body)}
    with pytest.raises(F75VectorError):
        validate_f75_route_time(expired_grant, context_wire, proof_wire)

    artificial = {**body, 6: 150}
    with pytest.raises(F75VectorError):
        validate_f75_route_time(artificial, context_wire, proof_wire)


def test_f75_service_port_mismatches_fail_closed() -> None:
    package = build_package()
    body = decode_deterministic(package["route-open-body.cbor"])
    context = decode_deterministic(package["federation-context.cbor"])

    wrong_context = dict(context)
    wrong_scope = dict(context[40])
    wrong_scope[7] = [[443, 443]]
    wrong_context[40] = wrong_scope
    with pytest.raises(F75VectorError):
        validate_f75_route_authority(body, encode_deterministic(wrong_context))

    wrong_grant = dict(body)
    sign1_body = decode_deterministic(body[2][1:])
    claims = decode_deterministic(sign1_body[2])
    claims[9] = [443]
    sign1_body[2] = encode_deterministic(claims)
    wrong_grant[2] = b"\xd2" + encode_deterministic(sign1_body)
    with pytest.raises(F75VectorError):
        validate_f75_route_authority(wrong_grant, package["federation-context.cbor"])

    wrong_route = dict(body)
    wrong_route[5] = 443
    with pytest.raises(F75VectorError):
        validate_f75_route_authority(wrong_route, package["federation-context.cbor"])


def test_edge_quic_udp_443_does_not_satisfy_service_port_authority() -> None:
    package = build_package()
    body = decode_deterministic(package["route-open-body.cbor"])
    assert ("udp", 443) != (body[4], body[5])
    wrong_route = {**body, 4: "udp", 5: 443}
    with pytest.raises(F75VectorError):
        validate_f75_route_authority(wrong_route, package["federation-context.cbor"])


def test_each_f75_transcript_binding_invalidates_the_valid_signature() -> None:
    mutations = build_mutation_vectors()
    assert {mutation["id"] for mutation in mutations} == EXPECTED_MUTATIONS
    public_hex = Path("vectors/core-v0.2/keys/test-only-session-ed25519-public.hex").read_text(encoding="ascii").strip()
    public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_hex))
    signature = bytes.fromhex(EXPECTED_SIGNATURE_HEX)

    for mutation in mutations:
        with pytest.raises(InvalidSignature):
            public_key.verify(signature, bytes.fromhex(mutation["transcript_hex"]))


def _positive_body() -> dict[int, object]:
    return decode_deterministic(bytes.fromhex(build_positive_vector()["body_hex"]))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda body: {**body, 0: 1},
        lambda body: {key: value for key, value in body.items() if key != 8},
        lambda body: {**body, 8: {**body[8], 0: 2}},
        lambda body: {**body, 8: {**body[8], 1: 2}},
        lambda body: {**body, 8: {**body[8], 2: 2}},
        lambda body: {**body, 8: {**body[8], 3: "nbsr-static-trust-v1"}},
        lambda body: {**body, 8: {**body[8], 4: b"x" * 31}},
        lambda body: {**body, 8: {**body[8], 5: b"x" * 31}},
        lambda body: {**body, 8: {**body[8], 6: 1}},
        lambda body: {**body, 8: {**body[8], 4: b"x" * 32}},
        lambda body: {**body, 8: {**body[8], 5: b"x" * 32}},
    ],
)
def test_closed_f75_body_rejects_invalid_binding(mutate) -> None:
    body = mutate(_positive_body())
    with pytest.raises(F75VectorError):
        decode_f75_body(
            encode_deterministic(body),
            expected_context_digest=bytes.fromhex(EXPECTED_CONTEXT_DIGEST),
        )


def test_body_v1_forbids_federation_key_8() -> None:
    body = _positive_body()
    body[0] = 1
    with pytest.raises(F75VectorError):
        decode_f75_body(encode_deterministic(body), expected_context_digest=bytes.fromhex(EXPECTED_CONTEXT_DIGEST))


def test_duplicate_and_noncanonical_f75_cbor_fail_closed() -> None:
    body_wire = bytes.fromhex(build_positive_vector()["body_hex"])
    noncanonical = body_wire[:2] + b"\x18\x02" + body_wire[3:]
    with pytest.raises(F75VectorError):
        decode_f75_body(noncanonical, expected_context_digest=bytes.fromhex(EXPECTED_CONTEXT_DIGEST))

    binding_wire = bytes.fromhex(EXPECTED_BINDING_HEX)
    duplicate_binding = bytes([0xA7]) + binding_wire[1:] + b"\x00\x01"
    body = _positive_body()
    body[8] = decode_deterministic(binding_wire)
    canonical = encode_deterministic(body)
    duplicate_body = canonical[: canonical.rfind(binding_wire)] + duplicate_binding
    with pytest.raises(F75VectorError):
        decode_f75_body(duplicate_body, expected_context_digest=bytes.fromhex(EXPECTED_CONTEXT_DIGEST))


def _tree_snapshot(root: Path) -> dict[str, str]:
    import hashlib

    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_f75_package_is_closed_deterministic_and_task7_immutable(tmp_path: Path) -> None:
    task7 = Path("vectors/federation-v0.1")
    before = _tree_snapshot(task7)
    first = tmp_path / "first"
    second = tmp_path / "second"

    write_package(first, build_package())
    write_package(second, build_package())

    assert _tree_snapshot(first) == _tree_snapshot(second)
    result = verify_package(first)
    assert result == {"artifacts": 8, "transcript_mutations": 19, "body_mutations": 15}
    assert _tree_snapshot(task7) == before


def test_f75_generator_check_and_independent_node_parity(tmp_path: Path) -> None:
    generated = tmp_path / "f75"
    subprocess.run(
        [sys.executable, "scripts/generate_wp8_f75_vectors.py", str(generated)],
        check=True,
        text=True,
    )
    checked = subprocess.run(
        [sys.executable, "scripts/generate_wp8_f75_vectors.py", "--check", str(generated)],
        check=True,
        text=True,
        capture_output=True,
    )
    assert checked.stdout.strip() == "F75 package verified: 8 artifacts, 19 transcript mutations, 15 body mutations"
    parity = subprocess.run(
        ["node", "scripts/verify_wp8_f75_vectors.mjs", str(generated)],
        check=True,
        text=True,
        capture_output=True,
    )
    assert parity.stdout.strip() == "F75 Node parity verified: binding, transcript, digest, and signature"
