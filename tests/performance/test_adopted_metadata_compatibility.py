"""Recorded public Docker metadata compatibility; no live inspection or credentials."""

import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.performance import windows_adopted_campaign as mod
from tests.performance.test_windows_adopted_campaign import fixture

RECORDED_LABEL = {"org.opencontainers.image.source": "https://github.com/rust-lang/docker-rust"}


def test_exact_pinned_inherited_labels_and_task_labels():
    _, _, base, ids, _ = fixture()
    engine = mod.AdoptedEndpoints(
        base.command,
        campaign="offline",
        image=base.image,
        specs=base.specs,
        network_id="f" * 64,
        handoff=ids,
        expected_environment=base.environment,
        inherited_labels=RECORDED_LABEL,
    )
    owner = mod.Container("normal", "source", ids["normal"]["source"], True)
    assert engine._labels(owner) == dict(RECORDED_LABEL, **{"nbsr.campaign": "offline", "nbsr.run": "normal", "nbsr.role": "source"})
    with pytest.raises(ValueError):
        mod.AdoptedEndpoints(
            base.command,
            campaign="offline",
            image=base.image,
            specs=base.specs,
            network_id="f" * 64,
            handoff=ids,
            expected_environment=base.environment,
            inherited_labels={"nbsr.run": "evil"},
        )


@pytest.mark.skipif(os.name != "nt", reason="materialized Windows path semantics")
def test_recorded_windows_mapping_preserves_source_and_rejects_change(tmp_path):
    assert hasattr(mod, "MountMapping"), "explicit recorded source mapping missing"
    source = tmp_path.resolve() / "PublicInput"
    source.mkdir()
    observed = str(source)
    mapping = mod.MountMapping(str(source), observed, "a" * 64)
    assert mod.validate_mapping(mapping) == source
    with pytest.raises(ValueError):
        mod.validate_mapping(mod.MountMapping(str(source).lower(), observed, "a" * 64))


@pytest.mark.parametrize("suffix", ["/../escape", "\\..\\escape", "\\alias.", "\\alias ", "\\x:stream", "\\PROGRA~1"])
def test_windows_mapping_rejects_ambiguous_paths(tmp_path, suffix):
    assert hasattr(mod, "MountMapping"), "explicit recorded source mapping missing"
    with pytest.raises(ValueError):
        mod.validate_mapping(mod.MountMapping(str(tmp_path.resolve()) + suffix, "/recorded/source", "a" * 64))


def test_windows_mapping_rejects_share_and_missing_path():
    assert hasattr(mod, "MountMapping"), "explicit recorded source mapping missing"
    for value in [r"\\server\share\input", r"\\?\C:\input", r"C:\uncreated-nbsr-mapping-file"]:
        with pytest.raises((ValueError, OSError)):
            mod.validate_mapping(mod.MountMapping(value, "/recorded/source", "a" * 64))


def test_actual_saved_metadata_label_and_path_contract():
    record = Path("tests/performance/fixtures/adoption-public-metadata.json")
    assert record.exists(), "retained public fixture missing"
    row = json.loads(record.read_bytes())
    assert row["inherited_labels"] == RECORDED_LABEL
    assert row["recorded_mounts"][0]["Source"].startswith("C:\\Users\\example\\")
    assert row["image"] == "sha256:7d59795425e21fc5ff09eabea1aad314806e8f20d3a505c5e47cc2df0e20e53d"


def mapped_engine(tmp_path, observed_windows=False):
    _, docker, base, ids, now = fixture()
    root = tmp_path.resolve()
    inputs = root / "Inputs"
    inputs.mkdir()
    outputs = root / "Outputs"
    outputs.mkdir()
    specs = {}
    mappings = {}
    fields = ("checkout_source", "binaries_source", "manifest_source", "ca_source", "certificate_source", "key_source", "evidence_source")
    for role, spec in base.specs.items():
        values = {}
        for field in fields:
            name = role + "-" + field if field in ("certificate_source", "key_source", "evidence_source") else field
            path = (outputs if field == "evidence_source" else inputs) / name
            path.mkdir(exist_ok=True)
            controller = str(path)
            observed = controller if observed_windows else "/recorded/" + name
            mappings[controller] = mod.MountMapping(controller, observed, "a" * 64)
            values[field] = controller
        specs[role] = replace(spec, **values)
    engine = mod.AdoptedEndpoints(
        base.command,
        campaign="offline",
        image=base.image,
        specs=specs,
        network_id="f" * 64,
        handoff=ids,
        expected_environment=base.environment,
        mount_mappings=tuple(mappings.values()),
    )
    return docker, engine, mappings


@pytest.mark.parametrize("windows", [True, False])
@pytest.mark.skipif(os.name != "nt", reason="materialized Windows path semantics")
def test_mapping_uses_exact_observed_source_for_inspection(tmp_path, windows):
    _, engine, mappings = mapped_engine(tmp_path, windows)
    mounts = engine._mounts("source")
    assert {m["Source"] for m in mounts} == {
        mappings[getattr(engine.specs["source"], f)].observed
        for f in (
            "checkout_source",
            "binaries_source",
            "manifest_source",
            "ca_source",
            "certificate_source",
            "key_source",
            "evidence_source",
        )
    }


@pytest.mark.skipif(os.name != "nt", reason="materialized Windows path semantics")
def test_mapping_rejects_overlapping_observed_output(tmp_path):
    _, engine, mappings = mapped_engine(tmp_path)
    key = engine.specs["source"].evidence_source
    mappings[key] = mod.MountMapping(key, "/recorded", "a" * 64)
    with pytest.raises(ValueError):
        mod.AdoptedEndpoints(
            engine.command,
            campaign="offline",
            image=engine.image,
            specs=engine.specs,
            network_id="f" * 64,
            handoff=engine.handoff,
            expected_environment=engine.environment,
            mount_mappings=tuple(mappings.values()),
        )


@pytest.mark.skipif(os.name != "nt", reason="materialized Windows path semantics")
def test_reparse_metadata_is_rejected_without_creating_link(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import stat

    path = tmp_path.resolve() / "Public"
    path.mkdir()
    original = Path.lstat

    def lstat(p, *a, **kw):
        if str(p) == str(path):
            return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
        return original(p, *a, **kw)

    monkeypatch.setattr(Path, "lstat", lstat)
    with pytest.raises(ValueError):
        mod.validate_mapping(mod.MountMapping(str(path), "/recorded/public", "a" * 64))


@pytest.mark.parametrize("extra", [{"nbsr.extra": "unexpected"}, {"foreign": "unexpected"}, {"org.opencontainers.image.source": "changed"}])
def test_exact_labels_reject_unpinned_or_changed_values(extra):
    _, docker, base, ids, now = fixture()
    engine = mod.AdoptedEndpoints(
        base.command,
        campaign="offline",
        image=base.image,
        specs=base.specs,
        network_id="f" * 64,
        handoff=ids,
        expected_environment=base.environment,
        inherited_labels=RECORDED_LABEL,
    )
    original = engine.command

    def command(args, *, timeout):
        result = original(args, timeout=timeout)
        if args[0] == "inspect" and result.code == 0:
            row = json.loads(result.stdout)
            actual = {**row["Labels"], **RECORDED_LABEL, **extra}
            owner = mod.Container(row["Labels"]["nbsr.run"], row["Labels"]["nbsr.role"], row["Id"], True)
            row["LabelsOK"] = actual == engine._labels(owner)
            return type(result)(0, json.dumps(row), "")
        return result

    engine.command = command
    with pytest.raises(mod.Unconfirmed):
        engine.prepare(remaining=50)
    assert not any(c[0] == "start" for c in docker.calls)


@pytest.mark.skipif(os.name != "nt", reason="materialized Windows path semantics")
def test_literal_mount_mismatch_is_not_normalized_away(tmp_path):
    docker, engine, _ = mapped_engine(tmp_path)
    for row in docker.containers.values():
        row["Mounts"] = engine._mounts(row["Labels"]["nbsr.role"])
    docker.containers[engine.handoff["normal"]["source"]]["Mounts"][0]["Source"] += "/unexpected"
    with pytest.raises(mod.Unconfirmed):
        engine.prepare(remaining=50)
    assert not any(c[0] == "start" for c in docker.calls)


@pytest.mark.skipif(os.name != "nt", reason="materialized Windows path semantics")
def test_complete_mapping_prepares_without_reading_file_contents(tmp_path):
    docker, engine, _ = mapped_engine(tmp_path)
    for row in docker.containers.values():
        row["Mounts"] = engine._mounts(row["Labels"]["nbsr.role"])
    engine.prepare(remaining=50)
    assert engine.prepared and not engine.unresolved_ids


@pytest.mark.skipif(os.name != "nt", reason="materialized Windows path semantics")
def test_pinned_mapping_record_rejects_tampering(tmp_path):
    import hashlib

    assert hasattr(mod, "load_mount_mappings"), "pinned record parser missing"
    source = tmp_path.resolve() / "Public"
    source.mkdir()
    wire = json.dumps(
        {"schema": "nbsr-local-mount-mapping-v1", "bindings": [{"controller": str(source), "observed": "/recorded/public"}]}
    ).encode()
    pin = hashlib.sha256(wire).hexdigest()
    rows = mod.load_mount_mappings(wire, pin)
    assert rows[0].controller == str(source) and rows[0].record_sha256 == pin
    with pytest.raises(ValueError):
        mod.load_mount_mappings(wire + b" ", pin)


@pytest.mark.skipif(os.name != "nt", reason="materialized Windows path semantics")
def test_observed_double_slash_alias_rejected(tmp_path):
    source = tmp_path.resolve() / "Public"
    source.mkdir()
    with pytest.raises(ValueError):
        mod.validate_mapping(mod.MountMapping(str(source), "//recorded/input", "a" * 64))
