import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "docs/protocol/registries/core-v0.2-baseline-lock.json"
F75_REPLACEMENTS = {
    "crates/nbsr-transport/src/admission.rs",
    "crates/nbsr-transport/src/core_v02.rs",
    "crates/nbsr-transport/src/lib.rs",
    "crates/nbsr-transport/src/session.rs",
}


def _files_for_scope(scope: str) -> set[str]:
    path = ROOT / scope
    if path.is_file():
        return {scope}
    return {item.relative_to(ROOT).as_posix() for item in path.rglob("*") if item.is_file() and "__pycache__" not in item.parts}


def test_core_v02_lock_covers_exact_declared_inventory() -> None:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    assert lock["baseline_commit"] == "b1edfa8cd4bb9a2f280e14a2973e404dd8e4c914"
    expected = set().union(*(_files_for_scope(scope) for scope in lock["scopes"]))
    assert set(lock["artifacts"]) == expected


def test_core_v02_lock_detects_every_byte_or_length_change() -> None:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    for relative, expected in lock["artifacts"].items():
        if relative in F75_REPLACEMENTS:
            continue
        data = (ROOT / relative).read_bytes()
        assert len(data) == expected["length"], relative
        assert hashlib.sha256(data).hexdigest() == expected["sha256"], relative


def test_core_v02_lock_declares_separate_wp4_exporter_ownership() -> None:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    assert lock["external_packages"] == {
        "vectors/core-v0.2/wp4-exporter": {
            "owner": "scripts/verify_wp4_exporter_vectors.mjs",
            "inventory": "vectors/core-v0.2/wp4-exporter/manifest.json",
        }
    }


def test_core_v02_lock_includes_every_rust_transport_boundary() -> None:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    for relative in (
        "crates/nbsr-transport/src/lib.rs",
        "crates/nbsr-transport/src/session.rs",
        "crates/nbsr-transport/src/admission.rs",
        "crates/nbsr-transport/src/quinn_adapter.rs",
    ):
        assert relative in lock["artifacts"]


def test_non_amended_core_artifacts_are_identical_to_baseline_commit() -> None:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    amended = set(lock["task0_amended_paths"])
    assert amended == {
        "tools/core-v02-node-verifier/README.md",
        "tools/core-v02-node-verifier/lib/manifest.mjs",
        "tools/core-v02-node-verifier/test/verifier.test.mjs",
    }
    for relative, expected in lock["artifacts"].items():
        if relative in amended:
            continue
        baseline = subprocess.run(
            ["git", "show", f"{lock['baseline_commit']}:{relative}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout
        assert len(baseline) == expected["length"], relative
        assert hashlib.sha256(baseline).hexdigest() == expected["sha256"], relative
