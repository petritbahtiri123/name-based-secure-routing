import json
import shutil
from pathlib import Path

import pytest

from nbsr.federation.profile import CoreBaselineError, assert_core_baseline


ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = ROOT / "docs/protocol/registries/core-v0.2-baseline-lock.json"


def _copy_locked_baseline(destination: Path) -> None:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    target_lock = destination / LOCK_PATH.relative_to(ROOT)
    target_lock.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(LOCK_PATH, target_lock)
    for relative in lock["artifacts"]:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)


def test_core_v02_baseline_accepts_exact_110_artifact_inventory() -> None:
    assert assert_core_baseline(ROOT) is None


def test_core_v02_baseline_rejects_modified_artifact(tmp_path: Path) -> None:
    _copy_locked_baseline(tmp_path)
    target = tmp_path / "docs/protocol/core-v0.1-wire.md"
    target.write_bytes(target.read_bytes() + b"mutation")
    with pytest.raises(CoreBaselineError, match="modified"):
        assert_core_baseline(tmp_path)


def test_core_v02_baseline_rejects_removed_artifact(tmp_path: Path) -> None:
    _copy_locked_baseline(tmp_path)
    (tmp_path / "docs/protocol/core-v0.1-wire.md").unlink()
    with pytest.raises(CoreBaselineError, match="missing"):
        assert_core_baseline(tmp_path)


def test_core_v02_baseline_rejects_added_artifact_in_locked_scope(tmp_path: Path) -> None:
    _copy_locked_baseline(tmp_path)
    extra = tmp_path / "nbsr/protocol/unlisted.py"
    extra.write_text("unlisted = True\n", encoding="utf-8")
    with pytest.raises(CoreBaselineError, match="unlisted"):
        assert_core_baseline(tmp_path)
