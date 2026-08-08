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
