from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from nbsr.federation.profile import CoreBaselineError, assert_p1p2_core_overlay


ROOT = Path(__file__).resolve().parents[2]
LOCK = "docs/protocol/registries/core-v0.2-baseline-lock.json"
F75 = "docs/protocol/registries/core-v0.2-f75-overlay.json"
P1P2 = "docs/protocol/registries/core-v0.2-p1p2-overlay.json"
APPROVED = {
    "crates/nbsr-transport/src/admission.rs",
    "crates/nbsr-transport/src/lib.rs",
    "crates/nbsr-transport/src/quinn_adapter.rs",
    "crates/nbsr-transport/src/session.rs",
}
P1P2_AUTHORITY_COMMIT = "aa48b24f277a7c388e6916c45c983ee2c15fc730"


def _git_blob(relative: str, revision: str = "HEAD") -> bytes:
    return subprocess.run(
        ["git", "cat-file", "blob", f"{revision}:{relative}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout


def _write(destination: Path, relative: str, data: bytes) -> None:
    target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def _copy_canonical_authority(destination: Path) -> Path:
    lock_bytes = _git_blob(LOCK)
    lock = json.loads(lock_bytes)
    _write(destination, LOCK, lock_bytes)
    _write(destination, F75, _git_blob(F75))
    shutil.copyfile(ROOT / P1P2, destination / P1P2)
    for relative in lock["artifacts"]:
        _write(destination, relative, _git_blob(relative, P1P2_AUTHORITY_COMMIT))
    return destination / P1P2


def _rewrite(path: Path, mutate) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    mutate(value)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", newline="\n")


def test_exact_approved_p1p2_overlay_passes(tmp_path: Path) -> None:
    _copy_canonical_authority(tmp_path)
    assert assert_p1p2_core_overlay(tmp_path) is None


@pytest.mark.parametrize("relative", sorted(APPROVED))
def test_each_approved_digest_is_exact(tmp_path: Path, relative: str) -> None:
    _copy_canonical_authority(tmp_path)
    target = tmp_path / relative
    target.write_bytes(target.read_bytes() + b"mutation")
    with pytest.raises(CoreBaselineError, match="P1/P2 overlay replacement"):
        assert_p1p2_core_overlay(tmp_path)


def test_original_baseline_and_parent_f75_are_both_mandatory(tmp_path: Path) -> None:
    _copy_canonical_authority(tmp_path)
    _rewrite(tmp_path / F75, lambda value: value.update({"unexpected": True}))
    with pytest.raises(CoreBaselineError, match="parent F75 overlay"):
        assert_p1p2_core_overlay(tmp_path)


def test_overlay_document_digest_is_authoritative(tmp_path: Path) -> None:
    overlay = _copy_canonical_authority(tmp_path)
    _rewrite(overlay, lambda value: value.update({"unexpected": True}))
    with pytest.raises(CoreBaselineError, match="P1/P2 overlay digest"):
        assert_p1p2_core_overlay(tmp_path)


def test_missing_extra_and_duplicate_paths_fail_closed(tmp_path: Path) -> None:
    for mutation in ("missing", "extra", "duplicate"):
        case = tmp_path / mutation
        overlay = _copy_canonical_authority(case)
        if mutation == "missing":
            _rewrite(overlay, lambda value: value["replacements"].pop())
        elif mutation == "extra":
            _rewrite(
                overlay,
                lambda value: value["replacements"].append(
                    {"path": "crates/nbsr-transport/src/core_v02.rs", "length": 1, "sha256": "00" * 32}
                ),
            )
        else:
            _rewrite(overlay, lambda value: value["replacements"].append(value["replacements"][0]))
        with pytest.raises(CoreBaselineError, match="P1/P2 overlay digest"):
            assert_p1p2_core_overlay(case)


@pytest.mark.parametrize(
    "alias",
    [
        "../crates/nbsr-transport/src/admission.rs",
        "crates\\nbsr-transport\\src\\admission.rs",
        "/crates/nbsr-transport/src/admission.rs",
        "CRATES/nbsr-transport/src/admission.rs",
    ],
)
def test_path_aliases_cannot_widen_authority(tmp_path: Path, alias: str) -> None:
    overlay = _copy_canonical_authority(tmp_path)
    _rewrite(overlay, lambda value: value["replacements"][0].update({"path": alias}))
    with pytest.raises(CoreBaselineError, match="P1/P2 overlay digest"):
        assert_p1p2_core_overlay(tmp_path)


def test_replacement_symlink_is_rejected(tmp_path: Path) -> None:
    _copy_canonical_authority(tmp_path)
    relative = sorted(APPROVED)[0]
    target = tmp_path / relative
    original = tmp_path / "original.rs"
    target.replace(original)
    try:
        target.symlink_to(original)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    with pytest.raises(CoreBaselineError, match="symlink"):
        assert_p1p2_core_overlay(tmp_path)
