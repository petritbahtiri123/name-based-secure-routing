from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

from scripts.core_v02_vectors.manifest import (
    VectorManifest,
    dump_manifest,
    load_manifest,
    validate_package,
)


ARTIFACT = b"\xa1\x00\x02"


def _manifest_dict(*, artifact_path: str = "artifacts/valid/example.cbor") -> dict[str, object]:
    return {
        "format_version": 1,
        "protocol": "NBSR",
        "protocol_version": 2,
        "alpn": "nbsr-quic-1",
        "hash": "sha256",
        "vectors": [
            {
                "id": "example-valid",
                "class": "valid",
                "artifact_type": "control-envelope-cbor",
                "artifact_path": artifact_path,
                "length": len(ARTIFACT),
                "sha256": sha256(ARTIFACT).hexdigest(),
                "expected_outcome": "accept",
                "expected_error": None,
                "validation_stage": "message-schema",
                "message_type": "CLIENT_HELLO",
                "scenario_only": False,
            }
        ],
        "scenarios": [],
    }


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_manifest_dump_is_sorted_utf8_lf_and_round_trips(tmp_path: Path) -> None:
    source = tmp_path / "manifest.json"
    _write_json(source, _manifest_dict())
    manifest = load_manifest(source)

    dumped = dump_manifest(manifest)

    assert dumped.startswith(b'{\n  "alpn":')
    assert dumped.endswith(b"\n")
    assert not dumped.endswith(b"\n\n")
    assert not dumped.startswith(b"\xef\xbb\xbf")
    round_trip = tmp_path / "round-trip.json"
    round_trip.write_bytes(dumped)
    assert load_manifest(round_trip) == manifest


@pytest.mark.parametrize("location", ["top", "vector", "scenario", "step"])
def test_manifest_rejects_unknown_keys(tmp_path: Path, location: str) -> None:
    raw = _manifest_dict()
    if location == "top":
        raw["unknown"] = True
    elif location == "vector":
        raw["vectors"][0]["unknown"] = True  # type: ignore[index]
    else:
        raw["scenarios"] = [
            {
                "id": "scenario-one",
                "initial_core_version": 2,
                "steps": [
                    {
                        "sequence": 1,
                        "vector_id": "example-valid",
                        "expected_outcome": "accept",
                        "expected_error": None,
                    }
                ],
                "final_assertions": ["transport-session-active"],
            }
        ]
        target = raw["scenarios"][0]  # type: ignore[index]
        if location == "step":
            target = target["steps"][0]  # type: ignore[index]
        target["unknown"] = True  # type: ignore[index]
    path = tmp_path / "manifest.json"
    _write_json(path, raw)

    with pytest.raises(ValueError, match="unknown"):
        load_manifest(path)


def test_manifest_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        '{"format_version":1,"format_version":1}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate"):
        load_manifest(path)


def test_manifest_rejects_duplicate_ids_and_paths(tmp_path: Path) -> None:
    for field in ("id", "artifact_path"):
        raw = _manifest_dict()
        duplicate = dict(raw["vectors"][0])  # type: ignore[index]
        duplicate["id"] = "second-valid"
        duplicate["artifact_path"] = "artifacts/valid/second.cbor"
        duplicate[field] = raw["vectors"][0][field]  # type: ignore[index]
        raw["vectors"].append(duplicate)  # type: ignore[union-attr]
        path = tmp_path / f"{field}.json"
        _write_json(path, raw)

        with pytest.raises(ValueError, match="duplicate"):
            load_manifest(path)


@pytest.mark.parametrize(
    "unsafe",
    [
        "../escape.cbor",
        "artifacts\\valid\\escape.cbor",
        "C:/escape.cbor",
        "file:///escape.cbor",
        "/absolute.cbor",
    ],
)
def test_manifest_rejects_path_escape_backslash_drive_and_uri(
    tmp_path: Path,
    unsafe: str,
) -> None:
    path = tmp_path / "manifest.json"
    _write_json(path, _manifest_dict(artifact_path=unsafe))

    with pytest.raises(ValueError, match="path"):
        load_manifest(path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("class", "maybe"),
        ("artifact_type", "packet-capture"),
        ("expected_outcome", "maybe"),
        ("validation_stage", "transport"),
        ("message_type", "NOT_A_MESSAGE"),
    ],
)
def test_manifest_rejects_unknown_enums(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    raw = _manifest_dict()
    raw["vectors"][0][field] = value  # type: ignore[index]
    path = tmp_path / "manifest.json"
    _write_json(path, raw)

    with pytest.raises(ValueError, match=field):
        load_manifest(path)


@pytest.mark.parametrize(
    ("outcome", "error"),
    [
        ("accept", "NBSR_E_REPLAY"),
        ("reject", None),
        ("reject", "NBSR_E_NOT_REAL"),
    ],
)
def test_manifest_rejects_invalid_error_pairing(
    tmp_path: Path,
    outcome: str,
    error: str | None,
) -> None:
    raw = _manifest_dict()
    raw["vectors"][0]["expected_outcome"] = outcome  # type: ignore[index]
    raw["vectors"][0]["expected_error"] = error  # type: ignore[index]
    path = tmp_path / "manifest.json"
    _write_json(path, raw)

    with pytest.raises(ValueError, match="expected_error"):
        load_manifest(path)


@pytest.mark.parametrize("field", ["format_version", "protocol_version", "length"])
def test_manifest_rejects_booleans_as_integers(tmp_path: Path, field: str) -> None:
    raw = _manifest_dict()
    if field == "length":
        raw["vectors"][0][field] = True  # type: ignore[index]
    else:
        raw[field] = True
    path = tmp_path / "manifest.json"
    _write_json(path, raw)

    with pytest.raises(ValueError, match=field):
        load_manifest(path)


@pytest.mark.parametrize("failure", ["missing", "extra", "length", "sha"])
def test_package_rejects_missing_extra_length_or_sha_mismatch(
    tmp_path: Path,
    failure: str,
) -> None:
    root = tmp_path / "core-v0.2"
    artifact = root / "artifacts" / "valid" / "example.cbor"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(ARTIFACT)
    raw = _manifest_dict()
    if failure == "missing":
        artifact.unlink()
    elif failure == "extra":
        (artifact.parent / "extra.cbor").write_bytes(b"x")
    elif failure == "length":
        raw["vectors"][0]["length"] = len(ARTIFACT) + 1  # type: ignore[index]
    elif failure == "sha":
        raw["vectors"][0]["sha256"] = "00" * 32  # type: ignore[index]
    manifest_path = root / "manifest.json"
    _write_json(manifest_path, raw)
    manifest = load_manifest(manifest_path)

    with pytest.raises(ValueError, match=failure):
        validate_package(root, manifest)


def test_package_accepts_exact_manifest_artifact_set(tmp_path: Path) -> None:
    root = tmp_path / "core-v0.2"
    artifact = root / "artifacts" / "valid" / "example.cbor"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(ARTIFACT)
    manifest_path = root / "manifest.json"
    _write_json(manifest_path, _manifest_dict())
    manifest: VectorManifest = load_manifest(manifest_path)

    validate_package(root, manifest)
