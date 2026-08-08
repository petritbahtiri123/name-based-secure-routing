from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from nbsr.federation.profile import CoreBaselineError, assert_f75_core_overlay


ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "docs/protocol/registries/core-v0.2-baseline-lock.json"
OVERLAY = ROOT / "docs/protocol/registries/core-v0.2-f75-overlay.json"
APPROVED = {
    "crates/nbsr-transport/src/admission.rs",
    "crates/nbsr-transport/src/core_v02.rs",
    "crates/nbsr-transport/src/lib.rs",
    "crates/nbsr-transport/src/session.rs",
}


def _copy_authority(destination: Path) -> Path:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    for authority in (LOCK, OVERLAY):
        target = destination / authority.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(authority, target)
    for relative in lock["artifacts"]:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    return destination / OVERLAY.relative_to(ROOT)


def _rewrite_overlay(path: Path, mutate) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    mutate(value)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_original_lock_bytes_and_digest_remain_frozen() -> None:
    assert hashlib.sha256(LOCK.read_bytes()).hexdigest() == "21d60dc60ee1bc00bef882b63fabaaea9229768770912ed7c93e6ae4d54453ef"


def test_exact_approved_f75_overlay_passes() -> None:
    assert assert_f75_core_overlay(ROOT) is None


@pytest.mark.parametrize("relative", sorted(APPROVED))
def test_mutation_of_each_overlay_replacement_fails(tmp_path: Path, relative: str) -> None:
    _copy_authority(tmp_path)
    target = tmp_path / relative
    target.write_bytes(target.read_bytes() + b"mutation")
    with pytest.raises(CoreBaselineError, match="overlay replacement"):
        assert_f75_core_overlay(tmp_path)


def test_mutation_of_non_overlay_core_file_fails(tmp_path: Path) -> None:
    _copy_authority(tmp_path)
    target = tmp_path / "crates/nbsr-transport/src/quinn_adapter.rs"
    target.write_bytes(target.read_bytes() + b"mutation")
    with pytest.raises(CoreBaselineError, match="baseline artifact"):
        assert_f75_core_overlay(tmp_path)


def test_fifth_replacement_path_fails(tmp_path: Path) -> None:
    overlay = _copy_authority(tmp_path)
    _rewrite_overlay(overlay, lambda value: value["replacements"].append({"path": "crates/nbsr-transport/src/quinn_adapter.rs", "length": 1, "sha256": "0" * 64}))
    with pytest.raises(CoreBaselineError, match="exactly four"):
        assert_f75_core_overlay(tmp_path)


@pytest.mark.parametrize("change", ["remove", "replace"])
def test_original_baseline_digest_reference_is_mandatory(tmp_path: Path, change: str) -> None:
    overlay = _copy_authority(tmp_path)
    def mutate(value):
        if change == "remove":
            del value["original_baseline"]["sha256"]
        else:
            value["original_baseline"]["sha256"] = "0" * 64
    _rewrite_overlay(overlay, mutate)
    with pytest.raises(CoreBaselineError, match="original baseline"):
        assert_f75_core_overlay(tmp_path)


@pytest.mark.parametrize(
    "alias",
    [
        "../crates/nbsr-transport/src/admission.rs",
        "crates/nbsr-transport/src/../src/admission.rs",
        "crates\\nbsr-transport\\src\\admission.rs",
        "CRATES/nbsr-transport/src/admission.rs",
        "/crates/nbsr-transport/src/admission.rs",
    ],
)
def test_path_aliases_cannot_widen_overlay_scope(tmp_path: Path, alias: str) -> None:
    overlay = _copy_authority(tmp_path)
    _rewrite_overlay(overlay, lambda value: value["replacements"][0].update(path=alias))
    with pytest.raises(CoreBaselineError, match="replacement path"):
        assert_f75_core_overlay(tmp_path)


@pytest.mark.parametrize(
    "unauthorized",
    [
        "vectors/core-v0.2/manifest.json",
        "docs/protocol/registries/core-v0.2-baseline-lock.json",
        "docs/protocol/core-v0.2-session-route-schema-proposal.md",
        "scripts/verify_wp4_exporter_vectors.mjs",
        "crates/nbsr-transport/src/quinn_adapter.rs",
    ],
)
def test_overlay_cannot_authorize_unrelated_core_authority(tmp_path: Path, unauthorized: str) -> None:
    overlay = _copy_authority(tmp_path)
    _rewrite_overlay(overlay, lambda value: value["replacements"][0].update(path=unauthorized))
    with pytest.raises(CoreBaselineError, match="replacement path"):
        assert_f75_core_overlay(tmp_path)


def test_overlay_rejects_symlinked_replacement(tmp_path: Path) -> None:
    _copy_authority(tmp_path)
    target = tmp_path / sorted(APPROVED)[0]
    original = target.with_suffix(".original")
    target.rename(original)
    try:
        target.symlink_to(original)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    with pytest.raises(CoreBaselineError, match="symlink"):
        assert_f75_core_overlay(tmp_path)
