import json
import subprocess
from pathlib import Path

import pytest

from nbsr.federation.profile import CoreBaselineError, assert_core_baseline_lock_authority, assert_p1p2_core_overlay


ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = ROOT / "docs/protocol/registries/core-v0.2-baseline-lock.json"
OVERLAY_PATH = ROOT / "docs/protocol/registries/core-v0.2-f75-overlay.json"
P1P2_OVERLAY_PATH = ROOT / "docs/protocol/registries/core-v0.2-p1p2-overlay.json"


def _git_blob(relative: str) -> bytes:
    return subprocess.run(
        ["git", "cat-file", "blob", f"HEAD:{relative}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout


def _write(destination: Path, relative: str, data: bytes) -> None:
    target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def _copy_locked_baseline(destination: Path) -> None:
    lock_relative = LOCK_PATH.relative_to(ROOT).as_posix()
    overlay_relative = OVERLAY_PATH.relative_to(ROOT).as_posix()
    p1p2_relative = P1P2_OVERLAY_PATH.relative_to(ROOT).as_posix()
    lock_bytes = _git_blob(lock_relative)
    lock = json.loads(lock_bytes)
    _write(destination, lock_relative, lock_bytes)
    _write(destination, overlay_relative, _git_blob(overlay_relative))
    _write(destination, p1p2_relative, P1P2_OVERLAY_PATH.read_bytes())
    for relative in lock["artifacts"]:
        _write(destination, relative, _git_blob(relative))


def test_core_v02_baseline_accepts_exact_110_artifact_inventory(tmp_path: Path) -> None:
    _copy_locked_baseline(tmp_path)
    assert assert_core_baseline_lock_authority(tmp_path) is None
    assert assert_p1p2_core_overlay(tmp_path) is None


def test_core_v02_baseline_rejects_modified_artifact(tmp_path: Path) -> None:
    _copy_locked_baseline(tmp_path)
    target = tmp_path / "docs/protocol/core-v0.1-wire.md"
    target.write_bytes(target.read_bytes() + b"mutation")
    with pytest.raises(CoreBaselineError, match="modified"):
        assert_p1p2_core_overlay(tmp_path)


def test_core_v02_baseline_rejects_removed_artifact(tmp_path: Path) -> None:
    _copy_locked_baseline(tmp_path)
    (tmp_path / "docs/protocol/core-v0.1-wire.md").unlink()
    with pytest.raises(CoreBaselineError, match="missing"):
        assert_p1p2_core_overlay(tmp_path)


def test_core_v02_baseline_rejects_added_artifact_in_locked_scope(tmp_path: Path) -> None:
    _copy_locked_baseline(tmp_path)
    extra = tmp_path / "nbsr/protocol/unlisted.py"
    extra.write_text("unlisted = True\n", encoding="utf-8")
    with pytest.raises(CoreBaselineError, match="unlisted"):
        assert_p1p2_core_overlay(tmp_path)
