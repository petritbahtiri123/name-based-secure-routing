from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import importlib.util

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_wp8_repository_safety.py"


def _module():
    spec = importlib.util.spec_from_file_location("wp8_safety", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dependency_inventory_is_closed_and_unchanged() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "dependencies", str(ROOT)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "dependency inspection: PASS" in result.stdout



@pytest.fixture
def demo_dependency_tree(tmp_path, monkeypatch):
    import hashlib
    import json
    from types import SimpleNamespace

    module = _module()
    paths = (module.ORIGINAL_DEPENDENCY_FILES | module.TASK10B_DEPENDENCY_FILES
             | module.TRANCHE2B_DEPENDENCY_FILES | module.DEMO_DEPENDENCY_FILES
             | {module.ISP_ADAPTER_MANIFEST, "tools/demo-lab/fixturegen/go.mod"})
    for relative in paths:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}" if path.suffix == ".json" else "")
    (tmp_path / "pyproject.toml").write_text("[project]\ndependencies = []\n")
    (tmp_path / module.ISP_ADAPTER_MANIFEST).write_text(
        "module nbsr.local/isp-federation-poc/adapter\ngo 1.26.5\n")
    manifest = tmp_path / "tools/demo-lab/fixturegen/go.mod"
    manifest.write_text("module nbsr.local/demo-lab/fixturegen\ngo 1.26.5\n")
    entries = []
    for relative in sorted(module.TASK10B_DEPENDENCY_FILES):
        wire = (tmp_path / relative).read_bytes()
        entries.append({"path": relative, "length": len(wire),
                        "sha256": hashlib.sha256(wire).hexdigest()})
    (tmp_path / "interop/nbsr-go-peer/dependency-lock.json").write_text(json.dumps({
        "schema": "nbsr-wp8-task10b-isolated-go-dependencies-v1",
        "reason": "synthetic regression fixture", "files": entries,
    }))
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=""))
    return module, tmp_path, manifest


def test_demo_stdlib_manifest_is_registered(demo_dependency_tree):
    module, root, _ = demo_dependency_tree
    assert "dependency inspection: PASS" in module.dependency_inspection(root)


@pytest.mark.parametrize("contents", [
    "module nbsr.local/demo-lab/fixturegen\ngo 1.26.5\nrequire example.invalid/lib v1.0.0\n",
    "module nbsr.local/demo-lab/fixturegen\ngo 1.26.5\nreplace example.invalid/lib => ../lib\n",
    "module nbsr.local/demo-lab/fixturegen\ngo 1.26.5\ntoolchain go1.27.0\n",
    "module unexpected/module\ngo 1.26.5\n",
    "module nbsr.local/demo-lab/fixturegen\ngo 1.27.0\n",
])
def test_demo_manifest_rejects_extra_dependencies_and_changed_pins(demo_dependency_tree, contents):
    module, root, manifest = demo_dependency_tree
    manifest.write_text(contents)
    with pytest.raises(ValueError, match="Demo Lab.*stdlib-only"):
        module.dependency_inspection(root)


def test_demo_manifest_rejects_added_go_sum(demo_dependency_tree):
    module, root, manifest = demo_dependency_tree
    manifest.with_name("go.sum").write_text("unexpected dependency")
    with pytest.raises(ValueError, match="inventory differs"):
        module.dependency_inspection(root)


def test_demo_registration_preserves_historical_dependency_hashes(demo_dependency_tree):
    module, root, _ = demo_dependency_tree
    (root / "interop/nbsr-go-peer/go.mod").write_text("changed historical dependency")
    with pytest.raises(ValueError, match="Task 10B dependency digest differs"):
        module.dependency_inspection(root)


def test_task10_repository_and_evidence_privacy_scan_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "privacy", str(ROOT)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "repository privacy/secret scan: PASS" in result.stdout


@pytest.mark.parametrize(
    ("name", "wire"),
    (
        ("credential.env", b"safe"),
        ("marker.txt", b"-----BEGIN PRIVATE KEY-----"),
        ("address.txt", b"198.51.100.8"),
        ("origin.txt", b"origin.internal"),
        ("subscriber.txt", b"subscriber"),
        ("payload.txt", b"NBSR-WP8-TASK10B-INDEPENDENT-WIRE"),
    ),
)
def test_task10b_privacy_scope_mutations_fail_closed(tmp_path: Path, monkeypatch, name: str, wire: bytes) -> None:
    evidence = tmp_path / "evidence" / "wp8-task10b"
    evidence.mkdir(parents=True)
    candidate = evidence / name
    candidate.write_bytes(wire)
    module = _module()
    monkeypatch.setattr(module, "_privacy_paths", lambda _root: [candidate])
    with pytest.raises(ValueError):
        module.privacy_scan(tmp_path)
