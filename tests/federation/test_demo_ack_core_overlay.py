from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from nbsr.federation.profile import CoreBaselineError, assert_demo_ack_core_overlay


ROOT = Path(__file__).resolve().parents[2]
LOCK = "docs/protocol/registries/core-v0.2-baseline-lock.json"
F75 = "docs/protocol/registries/core-v0.2-f75-overlay.json"
P1P2 = "docs/protocol/registries/core-v0.2-p1p2-overlay.json"
ACK = "docs/protocol/registries/core-v0.2-demo-ack-overlay.json"
REPLACEMENT = "crates/nbsr-transport/src/quinn_adapter.rs"


def _head_blob(relative: str) -> bytes:
    return subprocess.run(
        ["git", "cat-file", "blob", f"HEAD:{relative}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout


def _candidate_blob(relative: str) -> bytes:
    object_id = subprocess.run(
        ["git", "hash-object", "--path", relative, relative],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return subprocess.run(
        ["git", "cat-file", "blob", object_id],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout


def _write(root: Path, relative: str, data: bytes) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def _copy_authority(root: Path) -> Path:
    lock_bytes = _head_blob(LOCK)
    lock = json.loads(lock_bytes)
    _write(root, LOCK, lock_bytes)
    _write(root, F75, _head_blob(F75))
    _write(root, P1P2, _head_blob(P1P2))
    _write(root, ACK, (ROOT / ACK).read_bytes())
    for relative in lock["artifacts"]:
        _write(root, relative, _candidate_blob(relative))
    return root / ACK


def _rewrite(path: Path, mutate) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    mutate(value)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", newline="\n")


def test_exact_approved_demo_ack_overlay_passes(tmp_path: Path) -> None:
    _copy_authority(tmp_path)
    assert assert_demo_ack_core_overlay(tmp_path) is None


@pytest.mark.parametrize("authority", [P1P2, ACK])
def test_authority_mutation_is_rejected(tmp_path: Path, authority: str) -> None:
    _copy_authority(tmp_path)
    target = tmp_path / authority
    target.write_bytes(target.read_bytes() + b"mutation")
    with pytest.raises(CoreBaselineError, match="authority|overlay"):
        assert_demo_ack_core_overlay(tmp_path)


def test_replacement_mutation_is_rejected(tmp_path: Path) -> None:
    _copy_authority(tmp_path)
    target = tmp_path / REPLACEMENT
    target.write_bytes(target.read_bytes() + b"mutation")
    with pytest.raises(CoreBaselineError, match="ACK overlay replacement"):
        assert_demo_ack_core_overlay(tmp_path)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["parent_overlay"].update(path=F75),
        lambda value: value["parent_overlay"].update(sha256="00" * 32),
        lambda value: value["replacements"][0].update(path="crates/nbsr-transport/src/session.rs"),
        lambda value: value["replacements"].append(dict(value["replacements"][0])),
        lambda value: value.update(replacements=[]),
        lambda value: value.update(extra="unauthorized"),
    ],
)
def test_parent_substitution_and_scope_expansion_are_rejected(tmp_path: Path, mutation) -> None:
    overlay = _copy_authority(tmp_path)
    _rewrite(overlay, mutation)
    with pytest.raises(CoreBaselineError):
        assert_demo_ack_core_overlay(tmp_path)


@pytest.mark.parametrize(
    "path",
    [
        "crates/nbsr-transport/src",
        "crates/nbsr-transport/src/*.rs",
        "crates/nbsr-transport/src/../src/quinn_adapter.rs",
        "crates\\nbsr-transport\\src\\quinn_adapter.rs",
        "C:/crates/nbsr-transport/src/quinn_adapter.rs",
    ],
)
def test_directory_wildcard_and_path_aliases_cannot_expand_authority(
    tmp_path: Path, path: str
) -> None:
    overlay = _copy_authority(tmp_path)
    _rewrite(overlay, lambda value: value["replacements"][0].update(path=path))
    with pytest.raises(CoreBaselineError):
        assert_demo_ack_core_overlay(tmp_path)


def test_rollback_to_historical_quinn_adapter_is_rejected(tmp_path: Path) -> None:
    _copy_authority(tmp_path)
    _write(tmp_path, REPLACEMENT, _head_blob(REPLACEMENT).replace(
        b"    /// Waits until the peer acknowledges every byte queued before the\n"
        b"    /// send-side FIN. Callers that close the whole QUIC connection immediately\n"
        b"    /// after a final response use this to avoid discarding that response.\n"
        b"    pub async fn wait_for_send_ack(&self) -> Result<(), TransportError> {\n"
        b"        let inner = self.shared.inner.lock().await;\n"
        b"        match inner.send.stopped().await {\n"
        b"            Ok(None) => Ok(()),\n"
        b"            Ok(Some(_)) | Err(_) => Err(TransportError::ApplicationStreamFailed),\n"
        b"        }\n"
        b"    }\n\n",
        b"",
    ))
    with pytest.raises(CoreBaselineError, match="ACK overlay replacement"):
        assert_demo_ack_core_overlay(tmp_path)
