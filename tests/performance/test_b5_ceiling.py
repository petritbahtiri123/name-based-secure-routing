"""Soak load must consume a matching stable cohort, never a rounded peak."""

import hashlib
import json
from fractions import Fraction
from pathlib import Path

import pytest

from scripts.performance.b5_ceiling import load_ceiling

SHA = "a" * 40
BINARIES = dict(direct="b" * 64, nbsr="c" * 64, server="d" * 64)
SHAPE = dict(physical_cores=1, endpoint_groups=1, streams_per_group=1, payload_bytes=1024, runtime_workers=1)


def fixture(root, *, status="", sha=SHA, counts=(1001, 1002, 1003)):
    env = dict(
        repository_sha=sha,
        git_status=status,
        binary_sha256=BINARIES,
        physical_cores=1,
        smt_siblings_used=False,
        topology=dict(verified=True),
    )
    records = [
        dict(
            path="nbsr",
            repeat=i + 1,
            payload_bytes=1024,
            streams_per_group=1,
            endpoint_groups=1,
            runtime_workers=1,
            outstanding_per_stream=1,
            valid=True,
            cleanup_pass=True,
            errors=0,
            timeouts=0,
            configured_total_outstanding=1,
            max_observed_total_outstanding=1,
            completed_operations=count,
            measured_ns=1_000_000_000,
            operations_per_second=float(count),
            aggregate_application_gbps=count * 16384 / 1e9,
            p99_latency_ns=1000,
        )
        for i, count in enumerate(counts)
    ]
    write(root, env, records)
    return env, records


def write(root, env, records):
    for name, value in (("environment.json", env), ("records.json", records)):
        (root / name).write_text(json.dumps(value), encoding="utf-8")
    (root / "checksums.sha256").write_text(
        "".join(f"{hashlib.sha256((root / name).read_bytes()).hexdigest()}  {name}\n" for name in ("environment.json", "records.json")),
        encoding="utf-8",
    )


def load(root, **kwargs):
    return load_ceiling(root, current_sha=SHA, binary_sha256=BINARIES, shape=SHAPE, percent=kwargs.get("percent", 70), depth=1)


def test_load_uses_exact_median_operation_counts(tmp_path):
    fixture(tmp_path)
    result = load(tmp_path)
    assert Fraction(result["rate_numerator"], result["rate_denominator"]) == Fraction(1002 * 7, 10)
    assert result["reference_repeats"] == 3
    assert result["reference_sha"] == SHA
    assert len(result["manifest_sha256"]) == 64


@pytest.mark.parametrize("change", ["sha", "dirty", "binary", "shape", "topology", "smt", "peak", "count", "short"])
def test_unqualified_or_mismatched_reference_rejected(tmp_path, change):
    env, rows = fixture(tmp_path)
    if change == "sha":
        env["repository_sha"] = "e" * 40
    if change == "dirty":
        env["git_status"] = " M source.rs"
    if change == "binary":
        env["binary_sha256"] = {**BINARIES, "nbsr": "f" * 64}
    if change == "shape":
        rows[0]["runtime_workers"] = 2
    if change == "topology":
        env["topology"]["verified"] = False
    if change == "smt":
        env["smt_siblings_used"] = True
    if change == "peak":
        rows[0]["p99_latency_ns"] = 4000
    if change == "count":
        rows[0]["completed_operations"] += 50
    if change == "short":
        rows.pop()
    write(tmp_path, env, rows)
    with pytest.raises(ValueError):
        load(tmp_path)


def test_modified_artifact_rejected(tmp_path):
    fixture(tmp_path)
    with (tmp_path / "records.json").open("a") as stream:
        stream.write(" ")
    with pytest.raises(ValueError, match="checksum"):
        load(tmp_path)


def test_parses_the_bytes_that_were_verified(tmp_path, monkeypatch):
    _, records = fixture(tmp_path)
    changed = []
    for row in records:
        changed.append(
            {
                **row,
                "completed_operations": row["completed_operations"] + 100,
                "operations_per_second": row["operations_per_second"] + 100,
                "aggregate_application_gbps": (row["completed_operations"] + 100) * 16384 / 1e9,
            }
        )
    original_read = Path.read_text

    def replaced_read(path, *args, **kwargs):
        if path.name == "records.json":
            return json.dumps(changed)
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", replaced_read)
    result = load(tmp_path)
    assert Fraction(result["rate_numerator"], result["rate_denominator"]) == Fraction(1002 * 7, 10)


@pytest.mark.parametrize("percent", [0, 69, 81, 100, True, 70.0])
def test_only_declared_integer_load_range_allowed(tmp_path, percent):
    fixture(tmp_path)
    with pytest.raises(ValueError):
        load(tmp_path, percent=percent)
