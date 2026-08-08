from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_wp8_repository_safety.py"


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
