from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sys
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nbsr.protocol.cbor import decode_deterministic, encode_deterministic  # noqa: E402
from nbsr.protocol.cose import sign1  # noqa: E402
from nbsr.protocol.models import (  # noqa: E402
    ControlEnvelope,
    ProtocolError,
    Revocation,
    RevocationMode,
    RevocationReason,
    RevocationTargetType,
    RouteGrant,
    RouteIntent,
    ServiceRecord,
)
from nbsr.protocol.registry import ErrorCode, MessageType  # noqa: E402
from nbsr.protocol.schemas import encode_model  # noqa: E402


OUTPUT = ROOT / "tests" / "vectors" / "core-v0.1"
TEST_SEED = bytes(range(32))
PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(TEST_SEED)
PUBLIC_KEY = PRIVATE_KEY.public_key()
KID = b"test-key-v01"
UNKNOWN_KID = b"unknown-key-v01"
ID16 = bytes(range(16))
REVERSED_ID16 = bytes(reversed(ID16))
DIGEST32 = sha256(b"NBSR Core v0.1 fixture digest").digest()
OTHER_DIGEST32 = sha256(b"NBSR Core v0.1 alternate digest").digest()
NOW = 1_785_000_100


@dataclass(frozen=True, slots=True)
class Vector:
    name: str
    kind: str
    valid: bool
    payload: bytes
    expected: dict[str, object]

    @property
    def file(self) -> str:
        return f"{self.name}.cbor"


def _service_record() -> ServiceRecord:
    return ServiceRecord(
        1,
        "api.example.com",
        42,
        KID,
        "svc_api",
        "op_destination",
        ("edge-a",),
        "connector-a",
        ("tcp",),
        (443,),
        ("nbsr-quic-1",),
        "nbsr-secure-only",
        1_785_000_000,
        1_785_003_600,
        "revset_2026_207",
    )


def _route_intent() -> RouteIntent:
    return RouteIntent(
        1,
        DIGEST32,
        "api.example.com",
        "svc_api",
        "op_source",
        "edge-source",
        "op_destination",
        ("edge-a",),
        ("tcp",),
        (443,),
        1_785_000_000,
        1_785_000_120,
        42,
        DIGEST32,
        ID16,
        REVERSED_ID16,
    )


def _route_grant() -> RouteGrant:
    return RouteGrant(
        1,
        ID16,
        DIGEST32,
        "svc_api",
        "op_source",
        "edge-source",
        "op_destination",
        ("edge-a",),
        ("tcp",),
        (443,),
        DIGEST32,
        1_785_000_000,
        1_785_000_120,
        REVERSED_ID16,
        42,
        DIGEST32,
        b"nonce-1234567890",
    )


def _revocation() -> Revocation:
    return Revocation(
        1,
        ID16,
        KID,
        7,
        RevocationTargetType.SERVICE_RECORD,
        DIGEST32,
        RevocationMode.TERMINATE_ACTIVE_USE,
        1_785_000_000,
        None,
        42,
        RevocationReason.KEY_COMPROMISE,
    )


def _protocol_error() -> ProtocolError:
    return ProtocolError(
        1,
        ErrorCode.NBSR_E_OVER_CAPACITY,
        ID16,
        True,
        30,
    )


def _control_envelope() -> ControlEnvelope:
    return ControlEnvelope(
        1,
        MessageType.PING,
        ID16,
        REVERSED_ID16,
        9,
        {0: b"ping"},
        extensions={1000: b"optional"},
    )


def _signed(model: object, kid: bytes = KID) -> bytes:
    return sign1(encode_model(model), kid, PRIVATE_KEY)


def _raw_sign1(
    protected_map: object,
    *,
    unprotected: object | None = None,
    payload: bytes,
) -> bytes:
    protected = encode_deterministic(protected_map)
    signature = PRIVATE_KEY.sign(encode_deterministic(["Signature1", protected, b"", payload]))
    return b"\xd2" + encode_deterministic(
        [
            protected,
            {} if unprotected is None else unprotected,
            payload,
            signature,
        ]
    )


def _with_map_value(wire: bytes, key: int, value: object) -> bytes:
    decoded = decode_deterministic(wire)
    if type(decoded) is not dict:
        raise TypeError("fixture payload must be a map")
    decoded[key] = value
    return encode_deterministic(decoded)


def _binding_expected(**changes: object) -> dict[str, object]:
    context: dict[str, object] = {
        "name_digest": DIGEST32.hex(),
        "service_id": "svc_api",
        "transport": "tcp",
        "port": 443,
        "destination_edge_id": "edge-a",
    }
    context.update(changes)
    return {
        "error": ErrorCode.NBSR_E_GRANT_INVALID.name,
        "context": context,
    }


def _vectors() -> tuple[Vector, ...]:
    record = _service_record()
    intent = _route_intent()
    grant = _route_grant()
    revocation = _revocation()
    error = _protocol_error()
    envelope = _control_envelope()
    record_payload = encode_model(record)
    grant_payload = encode_model(grant)
    envelope_payload = encode_model(envelope)
    valid_grant = _signed(grant)

    tampered_body = decode_deterministic(valid_grant[1:])
    tampered_payload_body = list(tampered_body)
    tampered_payload_body[2] = bytes(tampered_payload_body[2][:-1]) + bytes((tampered_payload_body[2][-1] ^ 1,))
    tampered_signature_body = list(tampered_body)
    tampered_signature_body[3] = bytes(tampered_signature_body[3][:-1]) + bytes((tampered_signature_body[3][-1] ^ 1,))

    reversed_grant = decode_deterministic(grant_payload)
    reversed_grant[11] = 1_785_000_120
    reversed_grant[12] = 1_785_000_000

    unknown_critical = decode_deterministic(envelope_payload)
    unknown_critical[6] = [1000]
    duplicate_critical = decode_deterministic(envelope_payload)
    duplicate_critical[6] = [1000, 1000]

    wrong_type_record = decode_deterministic(record_payload)
    wrong_type_record[2] = True
    unknown_core_record = decode_deterministic(record_payload)
    unknown_core_record[50] = b"unknown"

    vectors = [
        Vector(
            "control-envelope-valid-01",
            "control_envelope",
            True,
            envelope_payload,
            {
                "message_type": MessageType.PING.name,
                "monotonic_sequence": 9,
                "request_id": ID16.hex(),
            },
        ),
        Vector(
            "service-record-valid-01",
            "signed_service_record",
            True,
            _signed(record),
            {
                "canonical_name": record.canonical_name,
                "owner_key_id": KID.hex(),
                "sequence": record.sequence,
                "service_id": record.service_id,
            },
        ),
        Vector(
            "route-intent-valid-01",
            "route_intent",
            True,
            encode_model(intent),
            {
                "lease_id": intent.lease_id.hex(),
                "record_sequence": intent.record_sequence,
                "route_id": intent.route_id.hex(),
                "service_id": intent.service_id,
            },
        ),
        Vector(
            "route-grant-valid-01",
            "signed_route_grant",
            True,
            valid_grant,
            {
                "kid": KID.hex(),
                "record_sequence": grant.record_sequence,
                "route_id": grant.route_id.hex(),
                "service_id": grant.service_id,
            },
        ),
        Vector(
            "revocation-immediate-valid-01",
            "signed_revocation",
            True,
            _signed(revocation),
            {
                "generation": revocation.generation,
                "issuer_key_id": KID.hex(),
                "revocation_id": revocation.revocation_id.hex(),
            },
        ),
        Vector(
            "protocol-error-valid-01",
            "protocol_error",
            True,
            encode_model(error),
            {
                "error_code": error.error_code.name,
                "request_id": error.request_id.hex(),
                "retryable": error.retryable,
            },
        ),
        Vector(
            "cbor-non-shortest-integer",
            "invalid_cbor",
            False,
            b"\x18\x01",
            {"error": ErrorCode.NBSR_E_PROFILE_UNSUPPORTED.name},
        ),
        Vector(
            "cbor-indefinite-map",
            "invalid_cbor",
            False,
            b"\xbf\xff",
            {"error": ErrorCode.NBSR_E_PROFILE_UNSUPPORTED.name},
        ),
        Vector(
            "cbor-duplicate-key",
            "invalid_cbor",
            False,
            b"\xa2\x00\x01\x00\x02",
            {"error": ErrorCode.NBSR_E_PROFILE_UNSUPPORTED.name},
        ),
        Vector(
            "cbor-unsorted-map-key",
            "invalid_cbor",
            False,
            b"\xa2\x01\x01\x00\x00",
            {"error": ErrorCode.NBSR_E_PROFILE_UNSUPPORTED.name},
        ),
        Vector(
            "cbor-excessive-nesting",
            "invalid_cbor",
            False,
            b"\x81" * 17 + b"\x00",
            {"error": ErrorCode.NBSR_E_OVER_CAPACITY.name},
        ),
        Vector(
            "service-record-wrong-field-type",
            "invalid_service_record",
            False,
            encode_deterministic(wrong_type_record),
            {"error": ErrorCode.NBSR_E_PROFILE_UNSUPPORTED.name},
        ),
        Vector(
            "service-record-unknown-core-field",
            "invalid_service_record",
            False,
            encode_deterministic(unknown_core_record),
            {"error": ErrorCode.NBSR_E_PROFILE_UNSUPPORTED.name},
        ),
        Vector(
            "control-envelope-unknown-critical-extension",
            "invalid_control_envelope",
            False,
            encode_deterministic(unknown_critical),
            {"error": ErrorCode.NBSR_E_PROFILE_UNSUPPORTED.name},
        ),
        Vector(
            "control-envelope-duplicate-critical-extension",
            "invalid_control_envelope",
            False,
            encode_deterministic(duplicate_critical),
            {"error": ErrorCode.NBSR_E_PROFILE_UNSUPPORTED.name},
        ),
        Vector(
            "service-record-stale-sequence",
            "signed_service_record_state",
            False,
            _signed(record),
            {
                "error": ErrorCode.NBSR_E_RECORD_STALE.name,
                "highest_sequence": 42,
            },
        ),
        Vector(
            "service-record-expired",
            "signed_service_record_state",
            False,
            _signed(record),
            {
                "error": ErrorCode.NBSR_E_RECORD_UNTRUSTED.name,
                "now": record.not_after,
            },
        ),
        Vector(
            "service-record-not-yet-valid",
            "signed_service_record_state",
            False,
            _signed(record),
            {
                "error": ErrorCode.NBSR_E_RECORD_UNTRUSTED.name,
                "now": record.not_before - 1,
            },
        ),
        Vector(
            "route-grant-reversed-window",
            "invalid_route_grant",
            False,
            encode_deterministic(reversed_grant),
            {"error": ErrorCode.NBSR_E_GRANT_INVALID.name},
        ),
        Vector(
            "route-grant-wrong-name",
            "signed_route_grant_binding",
            False,
            valid_grant,
            _binding_expected(name_digest=OTHER_DIGEST32.hex()),
        ),
        Vector(
            "route-grant-wrong-service",
            "signed_route_grant_binding",
            False,
            valid_grant,
            _binding_expected(service_id="svc_other"),
        ),
        Vector(
            "route-grant-wrong-transport",
            "signed_route_grant_binding",
            False,
            valid_grant,
            _binding_expected(transport="udp"),
        ),
        Vector(
            "route-grant-wrong-port",
            "signed_route_grant_binding",
            False,
            valid_grant,
            _binding_expected(port=8443),
        ),
        Vector(
            "route-grant-wrong-edge",
            "signed_route_grant_binding",
            False,
            valid_grant,
            _binding_expected(destination_edge_id="edge-b"),
        ),
        Vector(
            "cose-missing-alg",
            "invalid_signed_route_grant",
            False,
            _raw_sign1({4: KID}, payload=grant_payload),
            {"error": ErrorCode.NBSR_E_GRANT_INVALID.name},
        ),
        Vector(
            "cose-wrong-alg",
            "invalid_signed_route_grant",
            False,
            _raw_sign1({1: -7, 4: KID}, payload=grant_payload),
            {"error": ErrorCode.NBSR_E_GRANT_INVALID.name},
        ),
        Vector(
            "cose-alg-unprotected",
            "invalid_signed_route_grant",
            False,
            _raw_sign1({4: KID}, unprotected={1: -8}, payload=grant_payload),
            {"error": ErrorCode.NBSR_E_GRANT_INVALID.name},
        ),
        Vector(
            "cose-wrong-kid",
            "invalid_signed_route_grant",
            False,
            _raw_sign1({1: -8, 4: UNKNOWN_KID}, payload=grant_payload),
            {"error": ErrorCode.NBSR_E_GRANT_INVALID.name},
        ),
        Vector(
            "cose-tampered-payload",
            "invalid_signed_route_grant",
            False,
            b"\xd2" + encode_deterministic(tampered_payload_body),
            {"error": ErrorCode.NBSR_E_GRANT_INVALID.name},
        ),
        Vector(
            "cose-tampered-signature",
            "invalid_signed_route_grant",
            False,
            b"\xd2" + encode_deterministic(tampered_signature_body),
            {"error": ErrorCode.NBSR_E_GRANT_INVALID.name},
        ),
    ]

    for name, literal in (
        ("origin-ipv4-192-0-2-9", "192.0.2.9"),
        ("origin-ipv4-198-51-100-9", "198.51.100.9"),
        ("origin-ipv4-203-0-113-9", "203.0.113.9"),
        ("origin-ipv6-2001-db8-9", "2001:db8::9"),
    ):
        vectors.append(
            Vector(
                name,
                "invalid_service_record_origin",
                False,
                _with_map_value(record_payload, 50, literal),
                {
                    "error": ErrorCode.NBSR_E_PROFILE_UNSUPPORTED.name,
                    "documentation_ip": literal,
                },
            )
        )

    return tuple(sorted(vectors, key=lambda vector: vector.name))


def build_package() -> dict[str, bytes]:
    vectors = _vectors()
    public_hex = (
        PUBLIC_KEY.public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        ).hex()
        + "\n"
    ).encode("ascii")
    files = {vector.file: vector.payload for vector in vectors}
    files["test-ed25519-public.hex"] = public_hex
    manifest = {
        "format_version": 1,
        "protocol_version": 1,
        "public_key": {
            "file": "test-ed25519-public.hex",
            "kid_hex": KID.hex(),
            "sha256": sha256(public_hex).hexdigest(),
        },
        "vectors": [
            {
                "name": vector.name,
                "file": vector.file,
                "kind": vector.kind,
                "valid": vector.valid,
                "sha256": sha256(vector.payload).hexdigest(),
                "expected": vector.expected,
            }
            for vector in vectors
        ],
    }
    files["manifest.json"] = (
        json.dumps(
            manifest,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    return files


def validate_target(output: Path) -> Path:
    target = output.resolve()
    if target != OUTPUT.resolve():
        raise ValueError("output must be tests/vectors/core-v0.1")
    if output.is_symlink():
        raise ValueError("vector output cannot be a symlink")
    return target


def _owned_existing(output: Path) -> bool:
    manifest_path = output / "manifest.json"
    if not output.exists():
        return False
    if not output.is_dir() or not manifest_path.is_file():
        raise ValueError("existing target is not an owned Core v0.1 vector package")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("existing target is not an owned Core v0.1 vector package") from exc
    if manifest.get("format_version") != 1 or manifest.get("protocol_version") != 1:
        raise ValueError("existing target is not an owned Core v0.1 vector package")
    return True


def _write_staging(root: Path, files: dict[str, bytes]) -> None:
    root.mkdir()
    for relative, payload in sorted(files.items()):
        target = root / relative
        target.write_bytes(payload)


def write_package(output: Path = OUTPUT) -> None:
    target = validate_target(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    owned = _owned_existing(target)
    expected = build_package()
    staging = target.parent / f".core-v0.1-write-{uuid4().hex}"
    _write_staging(staging, expected)
    try:
        if {path.name: path.read_bytes() for path in staging.iterdir() if path.is_file()} != expected:
            raise ValueError("staged Core v0.1 package is incomplete")
        target.mkdir(exist_ok=True)
        for relative, payload in sorted(expected.items()):
            destination = target / relative
            temporary = target / f".{relative}.{uuid4().hex}.tmp"
            temporary.write_bytes(payload)
            os.replace(temporary, destination)
        if owned:
            for path in target.iterdir():
                if path.is_file() and path.name not in expected:
                    path.unlink()
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def check_package(output: Path = OUTPUT) -> None:
    target = validate_target(output)
    expected = build_package()
    if not target.is_dir():
        raise ValueError("Core v0.1 vector package is missing")
    actual = {path.name: path.read_bytes() for path in target.iterdir() if path.is_file()}
    if actual != expected:
        differences = []
        for name in sorted(set(actual) | set(expected)):
            if actual.get(name) == expected.get(name):
                continue
            old = "missing" if name not in actual else sha256(actual[name]).hexdigest()
            new = "missing" if name not in expected else sha256(expected[name]).hexdigest()
            differences.append(f"{name}: {old} -> {new}")
        raise ValueError("Core v0.1 vector drift:\n" + "\n".join(differences))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate or verify NBSR Core v0.1 deterministic vectors.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed package instead of writing it",
    )
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    try:
        if arguments.check:
            check_package()
            print("verified tests/vectors/core-v0.1")
        else:
            write_package()
            print("wrote tests/vectors/core-v0.1")
    except ValueError as exc:
        print(str(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
