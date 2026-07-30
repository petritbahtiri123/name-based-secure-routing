from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
import pytest

from nbsr.protocol.cbor import decode_deterministic
from nbsr.protocol.cose import require_kid, verify_sign1
from nbsr.protocol.errors import ProtocolViolation
from nbsr.protocol.registry import ErrorCode
from nbsr.protocol.schemas import (
    decode_envelope,
    decode_error,
    decode_revocation,
    decode_route_grant,
    decode_route_intent,
    decode_service_record,
)
from tools.generate_core_v01_vectors import (
    OUTPUT,
    TEST_SEED,
    build_package,
    check_package,
    validate_target,
)


ROOT = Path(__file__).resolve().parents[2]
VECTORS = ROOT / "tests" / "vectors" / "core-v0.1"
MANIFEST = VECTORS / "manifest.json"

EXPECTED_VECTOR_NAMES = (
    "cbor-duplicate-key",
    "cbor-excessive-nesting",
    "cbor-indefinite-map",
    "cbor-non-shortest-integer",
    "cbor-unsorted-map-key",
    "control-envelope-duplicate-critical-extension",
    "control-envelope-unknown-critical-extension",
    "control-envelope-valid-01",
    "cose-alg-unprotected",
    "cose-missing-alg",
    "cose-tampered-payload",
    "cose-tampered-signature",
    "cose-wrong-alg",
    "cose-wrong-kid",
    "origin-ipv4-192-0-2-9",
    "origin-ipv4-198-51-100-9",
    "origin-ipv4-203-0-113-9",
    "origin-ipv6-2001-db8-9",
    "protocol-error-valid-01",
    "revocation-immediate-valid-01",
    "route-grant-reversed-window",
    "route-grant-valid-01",
    "route-grant-wrong-edge",
    "route-grant-wrong-name",
    "route-grant-wrong-port",
    "route-grant-wrong-service",
    "route-grant-wrong-transport",
    "route-intent-valid-01",
    "service-record-expired",
    "service-record-not-yet-valid",
    "service-record-stale-sequence",
    "service-record-unknown-core-field",
    "service-record-valid-01",
    "service-record-wrong-field-type",
)


def load_manifest() -> dict[str, object]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_core_v01_manifest_is_complete_sorted_and_hash_bound() -> None:
    manifest = load_manifest()

    assert manifest["format_version"] == 1
    assert manifest["protocol_version"] == 1
    vectors = manifest["vectors"]
    assert tuple(entry["name"] for entry in vectors) == EXPECTED_VECTOR_NAMES
    assert sum(entry["valid"] is True for entry in vectors) == 6
    assert sum(entry["valid"] is False for entry in vectors) == 28
    assert all(set(entry) == {"name", "file", "kind", "valid", "sha256", "expected"} for entry in vectors)

    declared_files = set()
    for entry in vectors:
        relative = entry["file"]
        assert re.fullmatch(r"[a-z0-9][a-z0-9-]*\.cbor", relative)
        payload = (VECTORS / relative).read_bytes()
        assert entry["sha256"] == sha256(payload).hexdigest()
        declared_files.add(relative)

    public_key = manifest["public_key"]
    assert set(public_key) == {"file", "kid_hex", "sha256"}
    assert public_key["file"] == "test-ed25519-public.hex"
    key_bytes = (VECTORS / public_key["file"]).read_bytes()
    assert public_key["sha256"] == sha256(key_bytes).hexdigest()
    assert re.fullmatch(rb"[0-9a-f]{64}\n", key_bytes)
    assert re.fullmatch(r"[0-9a-f]{2,128}", public_key["kid_hex"])
    declared_files.add(public_key["file"])

    actual_files = {path.relative_to(VECTORS).as_posix() for path in VECTORS.iterdir() if path.is_file() and path.name != "manifest.json"}
    assert actual_files == declared_files


def _trust_context(
    manifest: dict[str, object],
) -> tuple[bytes, dict[bytes, Ed25519PublicKey]]:
    public_key = manifest["public_key"]
    kid = bytes.fromhex(public_key["kid_hex"])
    public_bytes = bytes.fromhex((VECTORS / public_key["file"]).read_text(encoding="ascii").strip())
    return kid, {kid: Ed25519PublicKey.from_public_bytes(public_bytes)}


def _validate_binding(grant: object, context: dict[str, object]) -> None:
    matches = (
        grant.name_digest.hex() == context["name_digest"]
        and grant.service_id == context["service_id"]
        and context["transport"] in grant.allowed_transports
        and context["port"] in grant.allowed_ports
        and context["destination_edge_id"] in grant.destination_edge_set
    )
    if not matches:
        raise ProtocolViolation(
            ErrorCode.NBSR_E_GRANT_INVALID,
            "RouteGrant fixture context mismatch",
        )


def _evaluate_vector(
    entry: dict[str, object],
    trust: dict[bytes, Ed25519PublicKey],
) -> dict[str, object]:
    wire = (VECTORS / entry["file"]).read_bytes()
    kind = entry["kind"]

    if kind == "control_envelope":
        envelope = decode_envelope(wire)
        return {
            "message_type": envelope.message_type.name,
            "monotonic_sequence": envelope.monotonic_sequence,
            "request_id": envelope.request_id.hex(),
        }
    if kind == "signed_service_record":
        verified = verify_sign1(
            wire,
            trust,
            ErrorCode.NBSR_E_RECORD_UNTRUSTED,
        )
        record = decode_service_record(verified.payload)
        require_kid(
            verified,
            record.owner_key_id,
            ErrorCode.NBSR_E_RECORD_UNTRUSTED,
        )
        return {
            "canonical_name": record.canonical_name,
            "owner_key_id": record.owner_key_id.hex(),
            "sequence": record.sequence,
            "service_id": record.service_id,
        }
    if kind == "route_intent":
        intent = decode_route_intent(wire)
        return {
            "lease_id": intent.lease_id.hex(),
            "record_sequence": intent.record_sequence,
            "route_id": intent.route_id.hex(),
            "service_id": intent.service_id,
        }
    if kind == "signed_route_grant":
        verified = verify_sign1(
            wire,
            trust,
            ErrorCode.NBSR_E_GRANT_INVALID,
        )
        grant = decode_route_grant(verified.payload)
        return {
            "kid": verified.kid.hex(),
            "record_sequence": grant.record_sequence,
            "route_id": grant.route_id.hex(),
            "service_id": grant.service_id,
        }
    if kind == "signed_revocation":
        verified = verify_sign1(
            wire,
            trust,
            ErrorCode.NBSR_E_RECORD_UNTRUSTED,
        )
        revocation = decode_revocation(verified.payload)
        require_kid(
            verified,
            revocation.issuer_key_id,
            ErrorCode.NBSR_E_RECORD_UNTRUSTED,
        )
        return {
            "generation": revocation.generation,
            "issuer_key_id": revocation.issuer_key_id.hex(),
            "revocation_id": revocation.revocation_id.hex(),
        }
    if kind == "protocol_error":
        error = decode_error(wire)
        return {
            "error_code": error.error_code.name,
            "request_id": error.request_id.hex(),
            "retryable": error.retryable,
        }
    if kind == "invalid_cbor":
        decode_deterministic(wire)
    elif kind in {"invalid_service_record", "invalid_service_record_origin"}:
        decode_service_record(wire)
    elif kind == "invalid_control_envelope":
        decode_envelope(wire)
    elif kind == "invalid_route_grant":
        decode_route_grant(wire)
    elif kind == "invalid_signed_route_grant":
        verify_sign1(wire, trust, ErrorCode.NBSR_E_GRANT_INVALID)
    elif kind == "signed_service_record_state":
        verified = verify_sign1(
            wire,
            trust,
            ErrorCode.NBSR_E_RECORD_UNTRUSTED,
        )
        record = decode_service_record(verified.payload)
        require_kid(
            verified,
            record.owner_key_id,
            ErrorCode.NBSR_E_RECORD_UNTRUSTED,
        )
        if "highest_sequence" in entry["expected"]:
            record.require_newer_than(entry["expected"]["highest_sequence"])
        else:
            record.require_valid_at(entry["expected"]["now"])
    elif kind == "signed_route_grant_binding":
        verified = verify_sign1(
            wire,
            trust,
            ErrorCode.NBSR_E_GRANT_INVALID,
        )
        grant = decode_route_grant(verified.payload)
        _validate_binding(grant, entry["expected"]["context"])
    else:
        raise AssertionError(f"unknown vector kind: {kind}")
    raise AssertionError(f"invalid vector unexpectedly accepted: {entry['name']}")


def test_every_vector_produces_its_declared_result() -> None:
    manifest = load_manifest()
    _, trust = _trust_context(manifest)

    for entry in manifest["vectors"]:
        if entry["valid"]:
            assert _evaluate_vector(entry, trust) == entry["expected"], entry["name"]
            continue
        with pytest.raises(ProtocolViolation) as rejected:
            _evaluate_vector(entry, trust)
        assert rejected.value.code.name == entry["expected"]["error"], entry["name"]


def test_generator_is_deterministic_target_bounded_and_in_sync(
    tmp_path: Path,
) -> None:
    first = build_package()
    second = build_package()

    assert first == second
    assert validate_target(OUTPUT) == OUTPUT.resolve()
    with pytest.raises(ValueError):
        validate_target(tmp_path / "core-v0.1")
    check_package()


def test_documentation_ip_literals_are_invalid_only() -> None:
    manifest = load_manifest()
    valid_files = [VECTORS / entry["file"] for entry in manifest["vectors"] if entry["valid"]]
    invalid_ip_entries = [entry for entry in manifest["vectors"] if "documentation_ip" in entry["expected"]]

    assert len(invalid_ip_entries) == 4
    assert {entry["expected"]["documentation_ip"] for entry in invalid_ip_entries} == {
        "192.0.2.9",
        "198.51.100.9",
        "203.0.113.9",
        "2001:db8::9",
    }
    assert all(
        literal.encode("ascii") not in path.read_bytes()
        for path in valid_files
        for literal in ("192.0.2.9", "198.51.100.9", "203.0.113.9", "2001:db8::9")
    )


def test_package_contains_only_public_test_material() -> None:
    assert all(TEST_SEED not in path.read_bytes() for path in VECTORS.iterdir())
