"""Exact approved receive/ACK successor, preserving historical authority."""
import json
from pathlib import Path, PurePosixPath
import subprocess

import pytest
from nbsr.federation import profile
from nbsr.federation.profile import CoreBaselineError, assert_transport_lifecycle_core_overlay

ROOT = Path(__file__).resolve().parents[2]
SOURCE = "2cc01bede62b43535ef5f69e241e8d9e79bc9b26"
REGISTRY = "docs/protocol/registries/"
LOCK = REGISTRY + "core-v0.2-baseline-lock.json"
ANCESTORS = (LOCK, REGISTRY + "core-v0.2-f75-overlay.json", REGISTRY + "core-v0.2-p1p2-overlay.json", REGISTRY + "core-v0.2-demo-ack-overlay.json")
ACTIVE = REGISTRY + "core-v0.2-transport-lifecycle-overlay.json"
SUCCESSOR = REGISTRY + "core-v0.2-receive-ack-drop-overlay.json"
CRATE = "crates/nbsr-transport/"
REPLACEMENTS = (CRATE + "src/lib.rs", CRATE + "src/quinn_adapter.rs")
DEPENDENCIES = tuple(CRATE + p for p in ("src/owned_send.rs", "src/udp_socket.rs", "src/benchmark_bind.rs", "Cargo.toml", "Cargo.lock"))


def verify(root):
    validator = getattr(profile, "assert_receive_ack_drop_core_overlay", None)
    assert validator is not None, "approved successor validator must exist"
    return validator(root)

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
    files[SUCCESSOR] = (ROOT / SUCCESSOR).read_bytes()
    return files


@pytest.fixture
def authority_root(tmp_path, canonical_files):
    for relative, wire in canonical_files.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(wire)
    return tmp_path


def test_approved_successor_accepts_exact_source(authority_root):
    assert verify(authority_root) is None


def test_historical_validator_rejects_new_adapter(authority_root):
    with pytest.raises(CoreBaselineError):
        assert_transport_lifecycle_core_overlay(authority_root)


def test_successor_rejects_old_adapter(authority_root):
    wire = subprocess.check_output(["git", "cat-file", "blob", "99ac954e0c0d90a221b42492a59fa4d5b962ea5d:" + REPLACEMENTS[1]], cwd=ROOT, timeout=20)
    (authority_root / REPLACEMENTS[1]).write_bytes(wire)
    with pytest.raises(CoreBaselineError):
        verify(authority_root)


@pytest.mark.parametrize("relative", ANCESTORS + (ACTIVE, SUCCESSOR) + REPLACEMENTS + DEPENDENCIES)
def test_bound_mutation_rejected(authority_root, relative):
    path = authority_root / relative
    path.write_bytes(path.read_bytes() + b"mutation")
    with pytest.raises(CoreBaselineError):
        verify(authority_root)


@pytest.mark.parametrize("relative", (ACTIVE, SUCCESSOR) + REPLACEMENTS + DEPENDENCIES)
def test_missing_bound_file_rejected(authority_root, relative):
    (authority_root / relative).unlink()
    with pytest.raises(CoreBaselineError):
        verify(authority_root)


@pytest.mark.parametrize("mutation", ["duplicate", "missing", "extra", "alias", "parent", "source", "field"])
def test_modified_successor_rejected(authority_root, mutation):
    p = authority_root / SUCCESSOR
    d = json.loads(p.read_bytes())
    if mutation == "duplicate":
        d["replacements"].append(dict(d["replacements"][0]))
    elif mutation == "missing":
        d["replacements"] = []
    elif mutation == "extra":
        d["replacements"].append({"path": REPLACEMENTS[0], "length": 0, "sha256": "0" * 64})
    elif mutation == "alias":
        d["replacements"][0]["path"] = "../quinn_adapter.rs"
    elif mutation == "parent":
        d["parent_overlay"]["sha256"] = "0" * 64
    elif mutation == "source":
        d["source_commit"] = "0" * 40
    else:
        d["fallback"] = True
    p.write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(CoreBaselineError):
        verify(authority_root)


@pytest.mark.parametrize("operation", ["mutate", "remove", "add"])
def test_original_inventory_enforced(authority_root, operation):
    p = authority_root / "nbsr/protocol/cbor.py"
    if operation == "mutate":
        p.write_bytes(p.read_bytes() + b"mutation")
    elif operation == "remove":
        p.unlink()
    else:
        (p.parent / "unapproved.py").write_bytes(b"x=1")
    with pytest.raises(CoreBaselineError):
        verify(authority_root)


def test_test_source_is_evidence_only(authority_root):
    (authority_root / (CRATE + "src/control_read_tests.rs")).write_bytes(b"evidence only")
    assert verify(authority_root) is None


@pytest.mark.parametrize("relative", [SUCCESSOR, ACTIVE, REPLACEMENTS[1], DEPENDENCIES[0]])
def test_symlink_rejected(authority_root, relative):
    p = authority_root / relative
    backing = authority_root / "backing"
    backing.write_bytes(p.read_bytes())
    p.unlink()
    try:
        p.symlink_to(backing)
    except OSError as error:
        if getattr(error, "winerror", None) == 1314:
            pytest.skip("Windows account lacks symbolic-link creation privilege")
        raise
    with pytest.raises(CoreBaselineError):
        verify(authority_root)
