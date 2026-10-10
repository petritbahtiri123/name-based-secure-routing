"""Review-only proposal checks. Not imported by CI or production authority code.

These checks bind a proposal to an immutable Git snapshot and exercise its closed
inventories. They do not activate it or test a future production validator.
"""

import copy
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = "99ac954e0c0d90a221b42492a59fa4d5b962ea5d"
CI_PARENT = "f6400959e93f32f3eec32372c60773c115344583"
PROPOSAL = Path(__file__).with_name("2026-10-10-corrected-transport-authority.candidate.json")
REGISTRY = "docs/protocol/registries/"
ANCESTORS = {
    REGISTRY + "core-v0.2-baseline-lock.json": "21d60dc60ee1bc00bef882b63fabaaea9229768770912ed7c93e6ae4d54453ef",
    REGISTRY + "core-v0.2-f75-overlay.json": "e095efd18e2d6ca154bfa5c49ae4e41362856e5054349040ca20ddc151c9ab1a",
    REGISTRY + "core-v0.2-p1p2-overlay.json": "7a33b7d6dd87031018563da0e8d2b1857515bc3ae2427094a6967d9e6329d3e4",
    REGISTRY + "core-v0.2-demo-ack-overlay.json": "99fe7153f251c4d68d836596bb532cf7bb32eb55f41d6c69b6fc04b281167801",
}
CRATE = "crates/nbsr-transport/"
REPLACEMENTS = {CRATE + "src/lib.rs", CRATE + "src/quinn_adapter.rs"}
DEPENDENCIES = {CRATE + p for p in (
    "src/owned_send.rs", "src/udp_socket.rs", "src/benchmark_bind.rs", "Cargo.toml", "Cargo.lock",
)}
VERIFICATION = {CRATE + p for p in (
    "src/control_read_tests.rs", "tests/application_stream.rs", "tests/stream_credit_integration.rs",
    "tests/handshake.rs", "tests/control.rs", "tests/benchmark_connect_from_tests.rs",
)}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def blob(path):
    return subprocess.check_output(["git", "cat-file", "blob", f"{SOURCE}:{path}"], cwd=ROOT)


def snapshot():
    lock = json.loads(blob(next(iter(ANCESTORS))))
    paths = sorted(set(lock["scopes"]) | set(ANCESTORS) | DEPENDENCIES | VERIFICATION)
    archive = subprocess.check_output(["git", "archive", "--format=tar", SOURCE, "--", *paths], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(archive)) as source:
        members = [m for m in source if not m.isdir()]
        assert all(m.isfile() for m in members), "non-regular candidate source"
        return {m.name: source.extractfile(m).read() for m in members}


def entries(paths, files):
    return [{"path": p, "length": len(files[p]), "sha256": digest(files[p])} for p in sorted(paths)]


def validate_entries(values, allowed, files):
    assert type(values) is list and len(values) == len(allowed), "closed entry count"
    seen = set()
    result = {}
    for entry in values:
        assert type(entry) is dict and set(entry) == {"path", "length", "sha256"}, "entry schema"
        path = entry["path"]
        assert type(path) is str and path in allowed and path not in seen, "closed unique path"
        assert type(entry["length"]) is int and entry["length"] >= 0, "length type"
        assert type(entry["sha256"]) is str and re.fullmatch("[0-9a-f]{64}", entry["sha256"]), "digest type"
        assert path in files, "missing supplemental source"
        assert len(files[path]) == entry["length"] and digest(files[path]) == entry["sha256"], "source bytes"
        seen.add(path)
        result[path] = entry
    assert seen == allowed, "closed paths"
    return result


def validate(proposal, files):
    assert set(proposal) == {"format_version", "status", "candidate_id", "source_commit", "ci_parent_commit", "ancestors", "parent_overlay", "replacements", "supplemental_dependencies", "verification_sources"}, "proposal schema"
    assert type(proposal["format_version"]) is int and proposal["format_version"] == 1
    assert proposal["status"] == "CANDIDATE_NOT_AUTHORITY"
    assert proposal["candidate_id"] == "NBSR-CORRECTED-TRANSPORT-2026-10-10"
    assert proposal["source_commit"] == SOURCE and proposal["ci_parent_commit"] == CI_PARENT, "source binding"
    assert proposal["ancestors"] == ANCESTORS, "ancestor binding"
    parent = REGISTRY + "core-v0.2-demo-ack-overlay.json"
    assert proposal["parent_overlay"] == {"path": parent, "sha256": ANCESTORS[parent]}, "parent binding"
    for path, expected in ANCESTORS.items():
        assert path in files and digest(files[path]) == expected, "ancestor bytes"
    lock = json.loads(files[next(iter(ANCESTORS))])
    expected = copy.deepcopy(lock["artifacts"])
    assert len(expected) == 110
    actual = {p for p in files if any(p == scope or p.startswith(scope + "/") for scope in lock["scopes"])}
    assert actual == set(expected), "legacy inventory"
    for path in list(ANCESTORS)[1:]:
        for entry in json.loads(files[path])["replacements"]:
            expected[entry["path"]] = entry
    expected.update(validate_entries(proposal["replacements"], REPLACEMENTS, files))
    for path, entry in expected.items():
        assert len(files[path]) == entry["length"] and digest(files[path]) == entry["sha256"], "legacy bytes"
    validate_entries(proposal["supplemental_dependencies"], DEPENDENCIES, files)
    validate_entries(proposal["verification_sources"], VERIFICATION, files)
    assert set(files) == actual | set(ANCESTORS) | DEPENDENCIES | VERIFICATION, "supplemental inventory"


@pytest.fixture(scope="module")
def candidate():
    return json.loads(PROPOSAL.read_text()), snapshot()


def test_exact_corrected_snapshot(candidate):
    validate(*candidate)


@pytest.mark.parametrize("path", sorted(ANCESTORS | {p: "" for p in REPLACEMENTS | DEPENDENCIES | VERIFICATION}))
def test_rejects_each_changed_bound_file(candidate, path):
    proposal, source = candidate
    files = dict(source)
    files[path] += b"\n"
    with pytest.raises(AssertionError):
        validate(proposal, files)


@pytest.mark.parametrize("kind", ["missing_legacy", "extra_legacy", "missing_dependency", "extra_supplemental", "unchanged_legacy_mutated"])
def test_inventory_rejections(candidate, kind):
    proposal, source = candidate
    files = dict(source)
    if kind == "missing_legacy":
        del files[CRATE + "src/lib.rs"]
    elif kind == "extra_legacy":
        files["vectors/core-v0.2/unapproved-extra.json"] = b"{}"
    elif kind == "missing_dependency":
        del files[CRATE + "src/owned_send.rs"]
    elif kind == "extra_supplemental":
        files[CRATE + "src/unapproved_helper.rs"] = b""
    else:
        files[CRATE + "src/session.rs"] += b"\n"
    with pytest.raises(AssertionError):
        validate(proposal, files)


@pytest.mark.parametrize("kind", ["wrong_source", "wrong_parent", "wrong_ancestor", "active", "extra_key", "duplicate", "missing", "extra", "unsafe", "bool_length", "negative_length", "bad_hash", "wrong_hash", "dependency_duplicate"])
def test_proposal_mutations(candidate, kind):
    original, files = candidate
    proposal = copy.deepcopy(original)
    if kind == "wrong_source": proposal["source_commit"] = CI_PARENT
    elif kind == "wrong_parent": proposal["parent_overlay"]["sha256"] = "0" * 64
    elif kind == "wrong_ancestor": proposal["ancestors"][next(iter(ANCESTORS))] = "0" * 64
    elif kind == "active": proposal["status"] = "ACTIVE_AUTHORITY"
    elif kind == "extra_key": proposal["allow_fallback"] = True
    elif kind == "duplicate": proposal["replacements"][1] = proposal["replacements"][0]
    elif kind == "missing": proposal["replacements"].pop()
    elif kind == "extra": proposal["replacements"].append(proposal["replacements"][0])
    elif kind == "unsafe": proposal["replacements"][0]["path"] = "../lib.rs"
    elif kind == "bool_length": proposal["replacements"][0]["length"] = True
    elif kind == "negative_length": proposal["replacements"][0]["length"] = -1
    elif kind == "bad_hash": proposal["replacements"][0]["sha256"] = "bad"
    elif kind == "wrong_hash": proposal["replacements"][0]["sha256"] = "0" * 64
    else: proposal["supplemental_dependencies"][1] = proposal["supplemental_dependencies"][0]
    with pytest.raises(AssertionError):
        validate(proposal, files)
