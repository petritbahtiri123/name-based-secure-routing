from __future__ import annotations

import json
from pathlib import Path

from nbsr.protocol.registry import ErrorCode, MessageType
from scripts.core_v02_vectors.generate import build_package


ROOT = Path(__file__).resolve().parents[2]
VERIFIER_ROOT = ROOT / "tools" / "core-v02-node-verifier"
PACKAGE_JSON = VERIFIER_ROOT / "package.json"
MANIFEST_JSON = ROOT / "vectors" / "core-v0.2" / "manifest.json"
VECTOR_README = ROOT / "vectors" / "core-v0.2" / "README.md"
DECISIONS = ROOT / "docs" / "protocol" / "v3.6-decisions.md"
ROADMAP = ROOT / "docs" / "superpowers" / "plans" / "2026-07-28-v3.6-protocol-roadmap.md"


def _production_sources() -> tuple[Path, ...]:
    return tuple(path for path in VERIFIER_ROOT.rglob("*.mjs") if "test" not in path.relative_to(VERIFIER_ROOT).parts)


def test_node_verifier_is_dependency_free_and_runtime_isolated() -> None:
    package = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    assert package["engines"]["node"] == ">=24 <25"
    assert "dependencies" not in package
    assert "devDependencies" not in package
    assert "preinstall" not in package.get("scripts", {})
    assert "postinstall" not in package.get("scripts", {})
    assert not (VERIFIER_ROOT / "package-lock.json").exists()

    for source in _production_sources():
        text = source.read_text(encoding="utf-8")
        assert "nbsr/" not in text
        assert "scripts/core_v02_vectors" not in text
        assert "node:child_process" not in text
        assert "writeFile" not in text
        assert "appendFile" not in text
        assert "createWriteStream" not in text


def test_node_verifier_never_reads_private_test_seeds() -> None:
    seed_names = (
        "test-only-route-grant-ed25519-seed.hex",
        "test-only-session-ed25519-seed.hex",
    )
    for source in VERIFIER_ROOT.rglob("*.mjs"):
        text = source.read_text(encoding="utf-8")
        if source.name == "manifest.mjs":
            assert all(text.count(name) == 1 for name in seed_names)
            continue
        assert all(name not in text for name in seed_names)


def test_node_verifier_freezes_current_package_coverage() -> None:
    manifest = json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))
    assert len([entry for entry in manifest["vectors"] if entry["class"] == "valid"]) == 14
    assert len([entry for entry in manifest["vectors"] if entry["class"] == "invalid"]) == 18
    assert len(manifest["scenarios"]) == 8


def test_frozen_message_and_error_registries_remain_unchanged() -> None:
    assert {item.name: item.value for item in MessageType} == {
        "CLIENT_HELLO": 1,
        "EDGE_HELLO": 2,
        "ROUTE_OPEN": 3,
        "ROUTE_ACCEPT": 4,
        "ROUTE_REJECT": 5,
        "STREAM_OPEN": 6,
        "STREAM_ACCEPT": 7,
        "STREAM_REJECT": 8,
        "LEASE_RENEW": 9,
        "LEASE_RESULT": 10,
        "KEY_UPDATE_NOTICE": 11,
        "ROUTE_DRAIN": 12,
        "ROUTE_REVOKE": 13,
        "ROUTE_CLOSE": 14,
        "PING": 15,
        "PONG": 16,
        "ERROR": 17,
    }
    assert {item.name: item.value for item in ErrorCode} == {
        "NBSR_E_NAME_INVALID": 1,
        "NBSR_E_NAME_NOT_FOUND": 2,
        "NBSR_E_RECORD_UNTRUSTED": 3,
        "NBSR_E_RECORD_STALE": 4,
        "NBSR_E_RECORD_REVOKED": 5,
        "NBSR_E_CONTEXT_REQUIRED": 6,
        "NBSR_E_HANDLE_EXHAUSTED": 7,
        "NBSR_E_ROUTE_DENIED": 8,
        "NBSR_E_GRANT_INVALID": 9,
        "NBSR_E_GRANT_EXPIRED": 10,
        "NBSR_E_PROOF_INVALID": 11,
        "NBSR_E_REPLAY": 12,
        "NBSR_E_PROFILE_UNSUPPORTED": 13,
        "NBSR_E_DOWNGRADE": 14,
        "NBSR_E_EDGE_UNAVAILABLE": 15,
        "NBSR_E_ORIGIN_UNAVAILABLE": 16,
        "NBSR_E_REVOKED": 17,
        "NBSR_E_OVER_CAPACITY": 18,
        "NBSR_E_INTERNAL": 19,
    }


def test_status_documents_record_cross_language_agreement_without_runtime_claim() -> None:
    vector_readme = " ".join(VECTOR_README.read_text(encoding="utf-8").split()).casefold()
    decisions = " ".join(DECISIONS.read_text(encoding="utf-8").split()).casefold()
    roadmap = " ".join(ROADMAP.read_text(encoding="utf-8").split()).casefold()

    assert "tools/core-v02-node-verifier/verify.mjs" in vector_readme
    assert "cross-language vector agreement" in vector_readme
    assert "does not prove production readiness" in vector_readme

    assert "dependency-free node.js 24 verifier passes" in decisions
    assert "runtime remains blocked" in decisions
    assert "does not authorize wp3" in decisions

    assert "second-language conformance gate is complete" in roadmap
    assert "wp3 runtime remains separately gated" in roadmap


def test_generated_vector_readme_preserves_node_verifier_status() -> None:
    support_files = dict(build_package().support_files)
    assert support_files["README.md"] == VECTOR_README.read_bytes()
    generated = support_files["README.md"].decode("utf-8")
    assert "tools/core-v02-node-verifier/verify.mjs" in generated
    assert "cross-language vector agreement" in generated
