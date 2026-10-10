"""Closed transport authority regressions using immutable raw Git blobs."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
import subprocess

import pytest

from nbsr.federation.profile import (
    CoreBaselineError,
    assert_demo_ack_core_overlay,
    assert_transport_lifecycle_core_overlay,
)


ROOT = Path(__file__).resolve().parents[2]
SOURCE = "99ac954e0c0d90a221b42492a59fa4d5b962ea5d"
REGISTRY = "docs/protocol/registries/"
LOCK = REGISTRY + "core-v0.2-baseline-lock.json"
ANCESTORS = (
    LOCK,
    REGISTRY + "core-v0.2-f75-overlay.json",
    REGISTRY + "core-v0.2-p1p2-overlay.json",
    REGISTRY + "core-v0.2-demo-ack-overlay.json",
)
ACTIVE = REGISTRY + "core-v0.2-transport-lifecycle-overlay.json"
CRATE = "crates/nbsr-transport/"
REPLACEMENTS = (CRATE + "src/lib.rs", CRATE + "src/quinn_adapter.rs")
DEPENDENCIES = tuple(CRATE + p for p in (
    "src/owned_send.rs", "src/udp_socket.rs", "src/benchmark_bind.rs", "Cargo.toml", "Cargo.lock",
))


@pytest.fixture(scope="module")
def canonical_files():
    lock_bytes = subprocess.check_output(
        ["git", "cat-file", "blob", f"{SOURCE}:{LOCK}"], cwd=ROOT, timeout=20,
    )
    lock = json.loads(lock_bytes)
    paths = sorted(set(lock["scopes"]) | set(ANCESTORS) | set(DEPENDENCIES))
    tree = subprocess.check_output(
        ["git", "ls-tree", "-rz", SOURCE, "--", *paths], cwd=ROOT, timeout=20,
    )
    selected = []
    for record in tree.split(b"\0"):
        if not record:
            continue
        metadata, name = record.split(b"\t", 1)
        mode, kind, object_id = metadata.split()
        relative = name.decode("utf-8")
        path = PurePosixPath(relative)
        assert mode in {b"100644", b"100755"} and kind == b"blob"
        assert not path.is_absolute() and ".." not in path.parts
        selected.append((relative, object_id))
    batch = subprocess.run(
        ["git", "cat-file", "--batch"], input=b"".join(oid + b"\n" for _, oid in selected),
        cwd=ROOT, capture_output=True, check=True, timeout=20,
    ).stdout
    files = {}
    offset = 0
    for relative, object_id in selected:
        end = batch.index(b"\n", offset)
        actual_id, kind, length = batch[offset:end].split()
        assert actual_id == object_id and kind == b"blob"
        size = int(length)
        files[relative] = batch[end + 1:end + 1 + size]
        offset = end + size + 2
    assert offset == len(batch)
    files[ACTIVE] = (ROOT / ACTIVE).read_bytes()
    return files


@pytest.fixture
def authority_root(tmp_path, canonical_files):
    for relative, wire in canonical_files.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(wire)
    return tmp_path


def test_exact_approved_transport_snapshot_passes(authority_root):
    assert assert_transport_lifecycle_core_overlay(authority_root) is None


def test_historical_ack_validator_still_rejects_later_source(authority_root):
    with pytest.raises(CoreBaselineError, match="parent P1/P2 overlay replacement"):
        assert_demo_ack_core_overlay(authority_root)


def test_verification_sources_are_evidence_not_new_runtime_gate(authority_root):
    evidence_source = authority_root / (CRATE + "src/control_read_tests.rs")
    evidence_source.write_bytes(b"review evidence is not an extra runtime authority input\n")
    assert assert_transport_lifecycle_core_overlay(authority_root) is None


@pytest.mark.parametrize("relative", ANCESTORS + REPLACEMENTS + DEPENDENCIES)
def test_each_bound_file_mutation_rejected(authority_root, relative):
    target = authority_root / relative
    target.write_bytes(target.read_bytes() + b"\nmutation")
    with pytest.raises(CoreBaselineError):
        assert_transport_lifecycle_core_overlay(authority_root)


@pytest.mark.parametrize("relative", REPLACEMENTS + DEPENDENCIES)
def test_missing_bound_source_rejected(authority_root, relative):
    (authority_root / relative).unlink()
    with pytest.raises(CoreBaselineError):
        assert_transport_lifecycle_core_overlay(authority_root)


@pytest.mark.parametrize("operation", ["mutate", "remove", "add"])
def test_legacy_inventory_remains_enforced(authority_root, operation):
    target = authority_root / "nbsr/protocol/cbor.py"
    assert target.is_file()
    if operation == "mutate":
        target.write_bytes(target.read_bytes() + b"\nmutation")
    elif operation == "remove":
        target.unlink()
    else:
        (target.parent / "unapproved_transport_helper.py").write_bytes(b"unapproved = True\n")
    with pytest.raises(CoreBaselineError):
        assert_transport_lifecycle_core_overlay(authority_root)


@pytest.mark.parametrize("mutation", [
    "wrong_parent", "extra_field", "duplicate", "missing", "extra", "unsafe_path",
    "absolute_path", "backslash_path", "case_alias", "bool_length", "negative_length",
    "bad_hash", "wrong_hash", "dependency_duplicate", "dependency_missing", "verification_gate",
])
def test_modified_active_document_rejected(authority_root, mutation):
    # The pinned document digest must reject all edits, even before schema validation.
    path = authority_root / ACTIVE
    value = json.loads(path.read_bytes())
    entry = value["replacements"][0]
    if mutation == "wrong_parent":
        value["parent_overlay"]["sha256"] = "0" * 64
    elif mutation == "extra_field":
        value["allow_fallback"] = True
    elif mutation == "duplicate":
        value["replacements"][1] = dict(entry)
    elif mutation == "missing":
        value["replacements"].pop()
    elif mutation == "extra":
        value["replacements"].append(dict(entry))
    elif mutation == "unsafe_path":
        entry["path"] = "../lib.rs"
    elif mutation == "absolute_path":
        entry["path"] = "/lib.rs"
    elif mutation == "backslash_path":
        entry["path"] = entry["path"].replace("/", "\\")
    elif mutation == "case_alias":
        entry["path"] = entry["path"].upper()
    elif mutation == "bool_length":
        entry["length"] = True
    elif mutation == "negative_length":
        entry["length"] = -1
    elif mutation == "bad_hash":
        entry["sha256"] = "invalid"
    elif mutation == "wrong_hash":
        entry["sha256"] = "0" * 64
    elif mutation == "dependency_duplicate":
        value["supplemental_dependencies"][1] = dict(value["supplemental_dependencies"][0])
    elif mutation == "dependency_missing":
        value["supplemental_dependencies"].pop()
    else:
        value["verification_sources"] = []
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")
    with pytest.raises(CoreBaselineError):
        assert_transport_lifecycle_core_overlay(authority_root)


@pytest.mark.parametrize("relative", [ACTIVE, REPLACEMENTS[0], DEPENDENCIES[0]])
def test_symlink_bound_file_rejected(authority_root, relative):
    target = authority_root / relative
    backing = authority_root / "symlink-backing.bin"
    backing.write_bytes(target.read_bytes())
    target.unlink()
    try:
        target.symlink_to(backing)
    except OSError as error:
        if getattr(error, "winerror", None) == 1314:
            pytest.skip("Windows account lacks symbolic-link creation privilege")
        raise
    with pytest.raises(CoreBaselineError):
        assert_transport_lifecycle_core_overlay(authority_root)
