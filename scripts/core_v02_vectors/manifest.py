from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any

from nbsr.protocol.registry import ErrorCode, MessageType


VECTOR_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
SHA256_HEX = re.compile(r"[0-9a-f]{64}\Z")

VECTOR_CLASSES = frozenset({"valid", "invalid"})
ARTIFACT_TYPES = frozenset(
    {
        "core-object-cbor",
        "cose-sign1",
        "control-envelope-cbor",
        "proof-transcript-cbor",
        "ed25519-signature",
        "malformed-bytes",
    }
)
OUTCOMES = frozenset({"accept", "reject"})
VALIDATION_STAGES = frozenset(
    {
        "structural",
        "deterministic-cbor",
        "object-schema",
        "cose",
        "envelope-schema",
        "message-schema",
        "version-dispatch",
        "proof",
        "binding",
        "replay",
        "policy",
    }
)
FINAL_ASSERTIONS = frozenset(
    {
        "transport-session-active",
        "transport-session-closed",
        "route-context-active",
        "no-route-state",
        "stream-active",
        "no-stream-state",
        "replay-state-unchanged",
        "replay-tombstone-retained",
        "no-version-fallback",
        "no-origin-disclosure",
    }
)
ERROR_NAMES = frozenset(item.name for item in ErrorCode)
MESSAGE_NAMES = frozenset(item.name for item in MessageType)

TOP_LEVEL_KEYS = frozenset(
    {
        "format_version",
        "protocol",
        "protocol_version",
        "alpn",
        "hash",
        "vectors",
        "scenarios",
    }
)
VECTOR_KEYS = frozenset(
    {
        "id",
        "class",
        "artifact_type",
        "artifact_path",
        "length",
        "sha256",
        "expected_outcome",
        "expected_error",
        "validation_stage",
        "message_type",
        "scenario_only",
    }
)
SCENARIO_KEYS = frozenset({"id", "initial_core_version", "steps", "final_assertions"})
STEP_KEYS = frozenset({"sequence", "vector_id", "expected_outcome", "expected_error"})
SUPPORT_FILES = frozenset(
    {
        "keys/test-only-route-grant-ed25519-seed.hex",
        "keys/test-only-route-grant-ed25519-public.hex",
        "keys/test-only-session-ed25519-seed.hex",
        "keys/test-only-session-ed25519-public.hex",
    }
)


@dataclass(frozen=True, slots=True)
class VectorEntry:
    id: str
    vector_class: str
    artifact_type: str
    artifact_path: str
    length: int
    sha256: str
    expected_outcome: str
    expected_error: str | None
    validation_stage: str
    message_type: str | None
    scenario_only: bool


@dataclass(frozen=True, slots=True)
class ScenarioStep:
    sequence: int
    vector_id: str
    expected_outcome: str
    expected_error: str | None


@dataclass(frozen=True, slots=True)
class ScenarioEntry:
    id: str
    initial_core_version: int
    steps: tuple[ScenarioStep, ...]
    final_assertions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class VectorManifest:
    format_version: int
    protocol: str
    protocol_version: int
    alpn: str
    hash: str
    vectors: tuple[VectorEntry, ...]
    scenarios: tuple[ScenarioEntry, ...]


def _reject_unknown_keys(value: dict[str, object], expected: frozenset[str]) -> None:
    unknown = set(value) - expected
    missing = expected - set(value)
    if unknown:
        raise ValueError(f"unknown manifest keys: {sorted(unknown)}")
    if missing:
        raise ValueError(f"missing manifest keys: {sorted(missing)}")


def _require_int(value: object, name: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"invalid {name}")
    return value


def _require_string(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"invalid {name}")
    return value


def _require_id(value: object, name: str = "id") -> str:
    result = _require_string(value, name)
    if VECTOR_ID.fullmatch(result) is None:
        raise ValueError(f"invalid {name}")
    return result


def _validate_outcome(outcome: object, error: object) -> tuple[str, str | None]:
    valid_outcome = _require_string(outcome, "expected_outcome")
    if valid_outcome not in OUTCOMES:
        raise ValueError("invalid expected_outcome")
    if valid_outcome == "accept":
        if error is not None:
            raise ValueError("expected_error must be null for accept")
        return valid_outcome, None
    if not isinstance(error, str) or error not in ERROR_NAMES:
        raise ValueError("expected_error must name a frozen error")
    return valid_outcome, error


def _validate_artifact_path(value: object) -> str:
    path = _require_string(value, "artifact_path")
    if "\\" in path or "://" in path or re.match(r"^[A-Za-z]:", path) or path.startswith("/"):
        raise ValueError("invalid artifact path")
    parts = PurePosixPath(path).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("invalid artifact path")
    if parts[0] != "artifacts":
        raise ValueError("artifact path must be below artifacts")
    return path


def _parse_vector(raw: object) -> VectorEntry:
    if not isinstance(raw, dict):
        raise ValueError("vector entry must be an object")
    _reject_unknown_keys(raw, VECTOR_KEYS)
    vector_class = _require_string(raw["class"], "class")
    if vector_class not in VECTOR_CLASSES:
        raise ValueError("invalid class")
    artifact_type = _require_string(raw["artifact_type"], "artifact_type")
    if artifact_type not in ARTIFACT_TYPES:
        raise ValueError("invalid artifact_type")
    checksum = _require_string(raw["sha256"], "sha256")
    if SHA256_HEX.fullmatch(checksum) is None:
        raise ValueError("invalid sha256")
    stage = _require_string(raw["validation_stage"], "validation_stage")
    if stage not in VALIDATION_STAGES:
        raise ValueError("invalid validation_stage")
    message_type = raw["message_type"]
    if message_type is not None and (not isinstance(message_type, str) or message_type not in MESSAGE_NAMES):
        raise ValueError("invalid message_type")
    scenario_only = raw["scenario_only"]
    if type(scenario_only) is not bool:
        raise ValueError("invalid scenario_only")
    outcome, error = _validate_outcome(
        raw["expected_outcome"],
        raw["expected_error"],
    )
    return VectorEntry(
        id=_require_id(raw["id"]),
        vector_class=vector_class,
        artifact_type=artifact_type,
        artifact_path=_validate_artifact_path(raw["artifact_path"]),
        length=_require_int(raw["length"], "length"),
        sha256=checksum,
        expected_outcome=outcome,
        expected_error=error,
        validation_stage=stage,
        message_type=message_type,
        scenario_only=scenario_only,
    )


def _parse_step(raw: object) -> ScenarioStep:
    if not isinstance(raw, dict):
        raise ValueError("scenario step must be an object")
    _reject_unknown_keys(raw, STEP_KEYS)
    outcome, error = _validate_outcome(
        raw["expected_outcome"],
        raw["expected_error"],
    )
    return ScenarioStep(
        sequence=_require_int(raw["sequence"], "sequence", minimum=1),
        vector_id=_require_id(raw["vector_id"], "vector_id"),
        expected_outcome=outcome,
        expected_error=error,
    )


def _parse_scenario(raw: object) -> ScenarioEntry:
    if not isinstance(raw, dict):
        raise ValueError("scenario entry must be an object")
    _reject_unknown_keys(raw, SCENARIO_KEYS)
    raw_steps = raw["steps"]
    raw_assertions = raw["final_assertions"]
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError("scenario steps must be a nonempty array")
    if not isinstance(raw_assertions, list):
        raise ValueError("final_assertions must be an array")
    steps = tuple(_parse_step(step) for step in raw_steps)
    if tuple(step.sequence for step in steps) != tuple(range(1, len(steps) + 1)):
        raise ValueError("scenario sequence must be contiguous from one")
    assertions = tuple(_require_string(value, "final_assertion") for value in raw_assertions)
    if len(set(assertions)) != len(assertions) or any(value not in FINAL_ASSERTIONS for value in assertions):
        raise ValueError("invalid final_assertions")
    return ScenarioEntry(
        id=_require_id(raw["id"]),
        initial_core_version=_require_int(
            raw["initial_core_version"],
            "initial_core_version",
            minimum=1,
        ),
        steps=steps,
        final_assertions=assertions,
    )


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _parse_manifest(raw: object) -> VectorManifest:
    if not isinstance(raw, dict):
        raise ValueError("manifest must be an object")
    _reject_unknown_keys(raw, TOP_LEVEL_KEYS)
    if raw["format_version"] != 1 or type(raw["format_version"]) is not int:
        raise ValueError("invalid format_version")
    if raw["protocol"] != "NBSR":
        raise ValueError("invalid protocol")
    if raw["protocol_version"] != 2 or type(raw["protocol_version"]) is not int:
        raise ValueError("invalid protocol_version")
    if raw["alpn"] != "nbsr-quic-1":
        raise ValueError("invalid alpn")
    if raw["hash"] != "sha256":
        raise ValueError("invalid hash")
    if not isinstance(raw["vectors"], list) or not isinstance(raw["scenarios"], list):
        raise ValueError("vectors and scenarios must be arrays")
    vectors = tuple(_parse_vector(item) for item in raw["vectors"])
    scenarios = tuple(_parse_scenario(item) for item in raw["scenarios"])
    vector_ids = [item.id for item in vectors]
    artifact_paths = [item.artifact_path for item in vectors]
    scenario_ids = [item.id for item in scenarios]
    if len(set(vector_ids)) != len(vector_ids):
        raise ValueError("duplicate vector id")
    if len(set(artifact_paths)) != len(artifact_paths):
        raise ValueError("duplicate artifact path")
    if len(set(scenario_ids)) != len(scenario_ids):
        raise ValueError("duplicate scenario id")
    known_vectors = set(vector_ids)
    for scenario in scenarios:
        for step in scenario.steps:
            if step.vector_id not in known_vectors:
                raise ValueError("unknown scenario vector_id")
    return VectorManifest(
        format_version=1,
        protocol="NBSR",
        protocol_version=2,
        alpn="nbsr-quic-1",
        hash="sha256",
        vectors=vectors,
        scenarios=scenarios,
    )


def load_manifest(path: Path) -> VectorManifest:
    try:
        text = path.read_text(encoding="utf-8-sig")
        raw = json.loads(text, object_pairs_hook=_reject_duplicate_pairs)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid manifest JSON") from exc
    return _parse_manifest(raw)


def _manifest_dict(manifest: VectorManifest) -> dict[str, object]:
    vectors = []
    for entry in sorted(manifest.vectors, key=lambda item: item.id):
        value = asdict(entry)
        value["class"] = value.pop("vector_class")
        vectors.append(value)
    scenarios = [asdict(item) for item in sorted(manifest.scenarios, key=lambda item: item.id)]
    return {
        "format_version": manifest.format_version,
        "protocol": manifest.protocol,
        "protocol_version": manifest.protocol_version,
        "alpn": manifest.alpn,
        "hash": manifest.hash,
        "vectors": vectors,
        "scenarios": scenarios,
    }


def dump_manifest(manifest: VectorManifest) -> bytes:
    validated = _parse_manifest(_manifest_dict(manifest))
    return (
        json.dumps(
            _manifest_dict(validated),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")


def validate_package(root: Path, manifest: VectorManifest) -> None:
    resolved_root = root.resolve()
    expected = {entry.artifact_path for entry in manifest.vectors}
    for entry in manifest.vectors:
        artifact = (root / Path(*PurePosixPath(entry.artifact_path).parts)).resolve()
        if not artifact.is_relative_to(resolved_root):
            raise ValueError(f"artifact path escapes package: {entry.artifact_path}")
        if not artifact.is_file():
            raise ValueError(f"missing artifact: {entry.artifact_path}")
        payload = artifact.read_bytes()
        if len(payload) != entry.length:
            raise ValueError(f"length mismatch: {entry.artifact_path}")
        if sha256(payload).hexdigest() != entry.sha256:
            raise ValueError(f"sha mismatch: {entry.artifact_path}")
    actual: set[str] = set()
    for directory in ("artifacts", "keys"):
        base = root / directory
        if base.exists():
            actual.update(path.relative_to(root).as_posix() for path in base.rglob("*") if path.is_file())
    extras = actual - expected - SUPPORT_FILES
    if extras:
        raise ValueError(f"extra package files: {sorted(extras)}")
