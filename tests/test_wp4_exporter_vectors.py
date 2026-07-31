import hashlib
import hmac
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "vectors" / "core-v0.2" / "wp4-exporter"
LABEL = b"EXPORTER-NBSR-Service-Channel-v2"
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
ARTIFACT_FIELDS = (
    "context_cbor",
    "context_hash",
    "derived_secret",
    "exporter_master_secret",
    "exporter_value",
)


def _encode_argument(major: int, value: int) -> bytes:
    if value < 24:
        return bytes([(major << 5) | value])
    if value <= 0xFF:
        return bytes([(major << 5) | 24, value])
    if value <= 0xFFFF:
        return bytes([(major << 5) | 25]) + value.to_bytes(2, "big")
    raise AssertionError("test encoder only supports profile-sized values")


def _encode_item(value: object) -> bytes:
    if isinstance(value, int):
        return _encode_argument(0, value)
    if isinstance(value, bytes):
        return _encode_argument(2, len(value)) + value
    if isinstance(value, str):
        encoded = value.encode("ascii")
        return _encode_argument(3, len(encoded)) + encoded
    raise AssertionError(f"unsupported test value: {value!r}")


def _canonical_context(context: dict[str, object]) -> bytes:
    values = []
    for field in CONTEXT_FIELDS:
        value = context[field]
        if field in {
            "session_id",
            "channel_id",
            "route_id",
            "route_grant_digest",
            "policy_hash",
            "client_nonce",
            "edge_nonce",
        }:
            value = bytes.fromhex(str(value))
        values.append(value)
    return _encode_argument(4, len(values)) + b"".join(_encode_item(value) for value in values)


def _hkdf_expand(secret: bytes, info: bytes, length: int) -> bytes:
    output = bytearray()
    block = b""
    counter = 1
    while len(output) < length:
        block = hmac.new(secret, block + info + bytes([counter]), hashlib.sha256).digest()
        output.extend(block)
        counter += 1
    return bytes(output[:length])


def _expand_label(secret: bytes, label: bytes, context: bytes, length: int) -> bytes:
    full_label = b"tls13 " + label
    info = (
        length.to_bytes(2, "big")
        + bytes([len(full_label)])
        + full_label
        + bytes([len(context)])
        + context
    )
    return _hkdf_expand(secret, info, length)


def _read_artifact(metadata: dict[str, object]) -> bytes:
    assert set(metadata) == {"length", "path", "sha256"}
    path = PACKAGE / str(metadata["path"])
    data = path.read_bytes()
    assert len(data) == metadata["length"]
    assert hashlib.sha256(data).hexdigest() == metadata["sha256"]
    return data


def test_generator_check_and_independent_python_vectors() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/generate_wp4_exporter_vectors.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    manifest = json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest) == {"invalid_cases", "profile", "schema", "valid_vectors", "version"}
    assert manifest["schema"] == "nbsr-wp4-exporter-vectors"
    assert manifest["version"] == 1
    assert set(manifest["profile"]) == {
        "context_array_items",
        "context_profile",
        "exporter_label",
        "hash",
        "output_length",
    }
    assert manifest["profile"] == {
        "context_array_items": 14,
        "context_profile": "NBSR-SERVICE-CHANNEL-CONTEXT-v2",
        "exporter_label": LABEL.decode("ascii"),
        "hash": "SHA-256",
        "output_length": 32,
    }
    assert len(manifest["valid_vectors"]) >= 2

    outputs = set()
    for vector in manifest["valid_vectors"]:
        assert set(vector) == {"artifacts", "context", "id"}
        assert set(vector["context"]) == set(CONTEXT_FIELDS)
        assert set(vector["artifacts"]) == set(ARTIFACT_FIELDS)
        context_cbor = _read_artifact(vector["artifacts"]["context_cbor"])
        context_hash = _read_artifact(vector["artifacts"]["context_hash"])
        master_secret = _read_artifact(vector["artifacts"]["exporter_master_secret"])
        derived_secret = _read_artifact(vector["artifacts"]["derived_secret"])
        exporter_value = _read_artifact(vector["artifacts"]["exporter_value"])

        assert context_cbor == _canonical_context(vector["context"])
        assert context_hash == hashlib.sha256(context_cbor).digest()
        assert len(master_secret) == 32
        empty_hash = hashlib.sha256(b"").digest()
        assert derived_secret == _expand_label(master_secret, LABEL, empty_hash, 32)
        assert exporter_value == _expand_label(derived_secret, b"exporter", context_hash, 32)
        outputs.add(exporter_value)
    assert len(outputs) == len(manifest["valid_vectors"])


def test_invalid_manifest_cases_are_closed_and_cover_required_mutations() -> None:
    manifest = json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8"))
    cases = manifest["invalid_cases"]
    categories = {case["category"] for case in cases}
    assert {f"context-item-{index}" for index in range(14)} <= categories
    assert {
        "array-reordering",
        "different-master-secret",
        "non-canonical-cbor",
        "wrong-cbor-type",
        "wrong-fixed-length",
        "wrong-label",
        "wrong-output-length",
    } <= categories

    valid_ids = {vector["id"] for vector in manifest["valid_vectors"]}
    for case in cases:
        assert set(case) == {
            "artifact",
            "artifact_type",
            "basis_vector",
            "category",
            "expected_result",
            "id",
            "reason",
        }
        assert case["basis_vector"] in valid_ids
        assert case["artifact_type"] in {
            "context-cbor",
            "exporter-label-ascii",
            "exporter-master-secret",
            "output-length-u16be",
        }
        assert case["expected_result"] in {"different", "reject"}
        assert case["reason"]
        _read_artifact(case["artifact"])
