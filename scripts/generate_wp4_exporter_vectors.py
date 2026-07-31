#!/usr/bin/env python3
"""Generate deterministic WP4 TLS 1.3 Service Channel exporter vectors."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
from pathlib import Path
import tempfile


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "vectors" / "core-v0.2" / "wp4-exporter"
LABEL = b"EXPORTER-NBSR-Service-Channel-v2"
CONTEXT_PROFILE = "NBSR-SERVICE-CHANNEL-CONTEXT-v2"
CONTEXT_FIELDS = (
    "profile",
    "version",
    "session_id",
    "source_edge_id",
    "destination_edge_id",
    "channel_id",
    "route_id",
    "route_grant_digest",
    "service_id",
    "transport",
    "port",
    "policy_hash",
    "client_nonce",
    "edge_nonce",
)
BYTE_FIELDS = {
    "session_id",
    "channel_id",
    "route_id",
    "route_grant_digest",
    "policy_hash",
    "client_nonce",
    "edge_nonce",
}


def encode_argument(major: int, value: int) -> bytes:
    if value < 0:
        raise ValueError("negative CBOR argument")
    if value < 24:
        return bytes([(major << 5) | value])
    if value <= 0xFF:
        return bytes([(major << 5) | 24, value])
    if value <= 0xFFFF:
        return bytes([(major << 5) | 25]) + value.to_bytes(2, "big")
    if value <= 0xFFFF_FFFF:
        return bytes([(major << 5) | 26]) + value.to_bytes(4, "big")
    return bytes([(major << 5) | 27]) + value.to_bytes(8, "big")


def encode_item(value: object) -> bytes:
    if isinstance(value, int):
        return encode_argument(0, value)
    if isinstance(value, bytes):
        return encode_argument(2, len(value)) + value
    if isinstance(value, str):
        encoded = value.encode("utf-8")
        return encode_argument(3, len(encoded)) + encoded
    raise TypeError(f"unsupported CBOR fixture value: {value!r}")


def context_values(context: dict[str, object]) -> list[object]:
    values: list[object] = []
    for field in CONTEXT_FIELDS:
        value = context[field]
        values.append(bytes.fromhex(str(value)) if field in BYTE_FIELDS else value)
    return values


def encode_context_values(values: list[object]) -> bytes:
    return encode_argument(4, len(values)) + b"".join(encode_item(value) for value in values)


def encode_context(context: dict[str, object]) -> bytes:
    return encode_context_values(context_values(context))


def hkdf_expand(secret: bytes, info: bytes, length: int) -> bytes:
    if length < 0 or length > 255 * hashlib.sha256().digest_size:
        raise ValueError("HKDF output length out of range")
    output = bytearray()
    block = b""
    for counter in range(1, 256):
        if len(output) >= length:
            break
        block = hmac.new(secret, block + info + bytes([counter]), hashlib.sha256).digest()
        output.extend(block)
    return bytes(output[:length])


def expand_label(secret: bytes, label: bytes, context: bytes, length: int) -> bytes:
    full_label = b"tls13 " + label
    if length < 0 or length > 0xFFFF:
        raise ValueError("TLS label output length does not fit uint16")
    if len(full_label) > 0xFF:
        raise ValueError("TLS label does not fit uint8")
    if len(context) > 0xFF:
        raise ValueError("TLS label context does not fit uint8")
    info = (
        length.to_bytes(2, "big")
        + bytes([len(full_label)])
        + full_label
        + bytes([len(context)])
        + context
    )
    return hkdf_expand(secret, info, length)


def derive(master_secret: bytes, context_cbor: bytes) -> tuple[bytes, bytes, bytes]:
    if len(master_secret) != 32:
        raise ValueError("fixture exporter master secret must be 32 bytes")
    context_hash = hashlib.sha256(context_cbor).digest()
    derived_secret = expand_label(master_secret, LABEL, hashlib.sha256(b"").digest(), 32)
    exporter_value = expand_label(derived_secret, b"exporter", context_hash, 32)
    return context_hash, derived_secret, exporter_value


def vector_inputs() -> list[tuple[str, bytes, dict[str, object]]]:
    return [
        (
            "service-channel-tcp-01",
            bytes(range(32)),
            {
                "profile": CONTEXT_PROFILE,
                "version": 2,
                "session_id": "00112233445566778899aabbccddeeff",
                "source_edge_id": "edge.source.alpha",
                "destination_edge_id": "edge.destination.beta",
                "channel_id": "102132435465768798a9bacbdcedfe0f",
                "route_id": "ffeeddccbbaa99887766554433221100",
                "route_grant_digest": "00" * 32,
                "service_id": "service.example.web",
                "transport": "tcp",
                "port": 443,
                "policy_hash": "11" * 32,
                "client_nonce": "22" * 32,
                "edge_nonce": "33" * 32,
            },
        ),
        (
            "service-channel-udp-02",
            bytes(range(255, 223, -1)),
            {
                "profile": CONTEXT_PROFILE,
                "version": 2,
                "session_id": "fedcba98765432100123456789abcdef",
                "source_edge_id": "edge.source.gamma",
                "destination_edge_id": "edge.destination.delta",
                "channel_id": "8899aabbccddeeff0011223344556677",
                "route_id": "7766554433221100ffeeddccbbaa9988",
                "route_grant_digest": "44" * 32,
                "service_id": "service.example.dns",
                "transport": "udp",
                "port": 5353,
                "policy_hash": "55" * 32,
                "client_nonce": "66" * 32,
                "edge_nonce": "77" * 32,
            },
        ),
    ]


def write_artifact(package: Path, relative_path: str, data: bytes) -> dict[str, object]:
    destination = package / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return {
        "length": len(data),
        "path": relative_path,
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def invalid_context_cases(base_context: dict[str, object]) -> list[tuple[str, str, bytes, str, str]]:
    base_values = context_values(base_context)
    replacements: list[tuple[object, str]] = [
        ("NBSR-SERVICE-CHANNEL-CONTEXT-v3", "profile-mismatch"),
        (3, "version-mismatch"),
        (b"\x00" * 15, "session-id-length"),
        ("", "source-edge-id-invalid"),
        ("edge.destination.\N{LATIN SMALL LETTER E WITH ACUTE}", "destination-edge-id-invalid"),
        (b"\x00" * 15, "channel-id-length"),
        (b"\x00" * 15, "route-id-length"),
        (b"\x00" * 31, "route-grant-digest-length"),
        ("", "service-id-invalid"),
        ("sctp", "transport-invalid"),
        (0, "port-invalid"),
        (b"\x00" * 31, "policy-hash-length"),
        (b"\x00" * 31, "client-nonce-length"),
        (b"\x00" * 31, "edge-nonce-length"),
    ]
    cases = []
    for index, (replacement, reason) in enumerate(replacements):
        values = list(base_values)
        values[index] = replacement
        cases.append(
            (
                f"context-item-{index:02d}",
                f"context-item-{index}",
                encode_context_values(values),
                "reject",
                reason,
            )
        )
    return cases


def build_package(package: Path) -> None:
    valid_vectors = []
    source_vectors = vector_inputs()
    for vector_id, master_secret, context in source_vectors:
        context_cbor = encode_context(context)
        context_hash, derived_secret, exporter_value = derive(master_secret, context_cbor)
        base = f"valid/{vector_id}"
        artifacts = {
            "context_cbor": write_artifact(package, f"{base}/context.cbor", context_cbor),
            "context_hash": write_artifact(package, f"{base}/context-hash.bin", context_hash),
            "derived_secret": write_artifact(package, f"{base}/derived-secret.bin", derived_secret),
            "exporter_master_secret": write_artifact(
                package, f"{base}/exporter-master-secret.bin", master_secret
            ),
            "exporter_value": write_artifact(package, f"{base}/exporter-value.bin", exporter_value),
        }
        valid_vectors.append({"artifacts": artifacts, "context": context, "id": vector_id})

    basis_id, basis_secret, basis_context = source_vectors[0]
    invalid_specs = invalid_context_cases(basis_context)
    base_values = context_values(basis_context)

    reordered = list(base_values)
    reordered[3], reordered[4] = reordered[4], reordered[3]
    invalid_specs.append(
        (
            "array-reordered-source-destination",
            "array-reordering",
            encode_context_values(reordered),
            "different",
            "context-hash-differs",
        )
    )
    wrong_type = list(base_values)
    wrong_type[2] = str(basis_context["session_id"])
    invalid_specs.append(
        (
            "wrong-cbor-type-session-id",
            "wrong-cbor-type",
            encode_context_values(wrong_type),
            "reject",
            "session-id-type",
        )
    )
    wrong_length = list(base_values)
    wrong_length[6] = b"\x00" * 17
    invalid_specs.append(
        (
            "wrong-fixed-length-route-id",
            "wrong-fixed-length",
            encode_context_values(wrong_length),
            "reject",
            "route-id-length",
        )
    )
    encoded_items = [encode_item(value) for value in base_values]
    encoded_items[10] = b"\x1a\x00\x00\x01\xbb"
    invalid_specs.append(
        (
            "non-canonical-port",
            "non-canonical-cbor",
            encode_argument(4, 14) + b"".join(encoded_items),
            "reject",
            "non-canonical-cbor",
        )
    )

    invalid_cases = []
    for case_id, category, data, expected_result, reason in invalid_specs:
        invalid_cases.append(
            {
                "artifact": write_artifact(package, f"invalid/{case_id}.cbor", data),
                "artifact_type": "context-cbor",
                "basis_vector": basis_id,
                "category": category,
                "expected_result": expected_result,
                "id": case_id,
                "reason": reason,
            }
        )

    parameter_cases = [
        (
            "wrong-exporter-label",
            "wrong-label",
            "exporter-label-ascii",
            b"EXPORTER-NBSR-Service-Channel-v1",
            "reject",
            "wrong-label",
            "txt",
        ),
        (
            "wrong-output-length-31",
            "wrong-output-length",
            "output-length-u16be",
            (31).to_bytes(2, "big"),
            "reject",
            "wrong-output-length",
            "bin",
        ),
        (
            "different-exporter-master-secret",
            "different-master-secret",
            "exporter-master-secret",
            basis_secret[:-1] + bytes([basis_secret[-1] ^ 1]),
            "different",
            "exporter-value-differs",
            "bin",
        ),
    ]
    for case_id, category, artifact_type, data, expected_result, reason, suffix in parameter_cases:
        invalid_cases.append(
            {
                "artifact": write_artifact(package, f"invalid/{case_id}.{suffix}", data),
                "artifact_type": artifact_type,
                "basis_vector": basis_id,
                "category": category,
                "expected_result": expected_result,
                "id": case_id,
                "reason": reason,
            }
        )

    manifest = {
        "invalid_cases": invalid_cases,
        "profile": {
            "context_array_items": 14,
            "context_profile": CONTEXT_PROFILE,
            "exporter_label": LABEL.decode("ascii"),
            "hash": "SHA-256",
            "output_length": 32,
        },
        "schema": "nbsr-wp4-exporter-vectors",
        "valid_vectors": valid_vectors,
        "version": 1,
    }
    manifest_bytes = json.dumps(
        manifest, indent=2, sort_keys=True, ensure_ascii=True, separators=(",", ": ")
    ).encode("utf-8") + b"\n"
    write_artifact(package, "manifest.json", manifest_bytes)


def files_under(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def check_package() -> int:
    with tempfile.TemporaryDirectory(prefix="nbsr-wp4-exporter-") as temporary:
        generated = Path(temporary) / "wp4-exporter"
        build_package(generated)
        expected_files = files_under(generated)
        checked_files = files_under(PACKAGE)
        if expected_files != checked_files:
            missing = sorted(expected_files.keys() - checked_files.keys())
            extra = sorted(checked_files.keys() - expected_files.keys())
            changed = sorted(
                path
                for path in expected_files.keys() & checked_files.keys()
                if expected_files[path] != checked_files[path]
            )
            print(f"WP4 exporter vectors are stale: missing={missing}, extra={extra}, changed={changed}")
            return 1
    print("WP4 exporter vectors are current (2 valid, 21 invalid/mutation cases)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        return check_package()
    build_package(PACKAGE)
    print(f"wrote {PACKAGE} (2 valid, 21 invalid/mutation cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
