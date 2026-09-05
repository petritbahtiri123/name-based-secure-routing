import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import run_b5_sustained_capacity as b5
from scripts.performance import resources, sustained_capacity


def test_sampler_records_actual_per_role_monotonic_point(monkeypatch):
    ticks = iter((100, 200, 300))
    monkeypatch.setattr(resources.time, "perf_counter_ns", lambda: next(ticks))
    monkeypatch.setattr(resources, "sample_windows_process", lambda pid: resources.ProcessResourceSample(pid, 0, 0, 10, 10, 10, 1, 1))
    sampler = resources.ProcessResourceSampler({"source": 1, "destination": 2}, assigned_logical_processors=1)
    sampler.record_sink = lambda sample: sampler._stop.set() if sample.role == "destination" else None
    sampler._run()
    assert [r.monotonic_timestamp_ns for r in sampler._records] == [200, 300]
    assert [r.timestamp_ns for r in sampler._records] == [100, 200]


def test_live_growth_excludes_warmup_and_after_progress_and_requires_both_roles():
    rows = [dict(role=role, monotonic_timestamp_ns=t, private_bytes=value)
            for role in ("source", "destination")
            for t, value in ((1, 10), (2, 20), (3, 30), (4, 40), (10, 100), (11, 100), (12, 100), (13, 100), (20, 10000))]
    assert sustained_capacity.live_private_growth(rows, 10, 13) is None
    for row in rows:
        if 10 <= row["monotonic_timestamp_ns"] <= 13:
            row["private_bytes"] += (row["monotonic_timestamp_ns"] - 10) * 10
    assert sustained_capacity.live_private_growth(rows, 10, 12) is None
    assert sustained_capacity.live_private_growth(rows, 10, 13) == "source"


def test_resource_phase_uses_absolute_sample_clock_not_relative_origin():
    rows = [dict(timestamp_ns=999999, monotonic_timestamp_ns=t) for t in (99, 100, 105, 110, 111)]
    b5.tag_resource_phases(rows, [(100, 10), (110, 20)])
    assert [r["phase"] for r in rows] == ["pre_first_progress", "steady", "steady", "steady", "cooldown"]
    assert rows[2]["measurement_relative_ns"] == 15


def test_live_growth_aborts_from_progress_and_preserves_raw(monkeypatch, tmp_path):
    peer = SimpleNamespace(pid=1, returncode=None)
    peer.poll = lambda: peer.returncode
    peer.kill = lambda: setattr(peer, "returncode", -1)
    peer.wait = lambda timeout: peer.returncode
    monkeypatch.setattr(b5.subprocess, "Popen", lambda *a, **k: peer)
    monkeypatch.setattr(b5, "wait_ready", lambda *a: {"endpoint": "127.0.0.1:12345"})
    monkeypatch.setattr(b5.time, "perf_counter_ns", lambda: 10_000_000_000)

    def measured(*args, output_line_sink, resource_sink, **kwargs):
        progress = {"event": "p2a_progress", "elapsed_ns": 1, "completed_operations": 1}
        output_line_sink(json.dumps(progress))
        for role in ("source", "destination"):
            for index in range(4):
                resource_sink(dict(role=role, timestamp_ns=index, monotonic_timestamp_ns=10_000_000_000 + index,
                                   private_bytes=100 + index * 10))
        monkeypatch.setattr(b5.time, "perf_counter_ns", lambda: 11_000_000_000)
        output_line_sink(json.dumps({**progress, "elapsed_ns": 2}))
        raise AssertionError("continued after resource growth")

    monkeypatch.setattr(b5, "measured_client", measured)
    with pytest.raises(RuntimeError, match="soak live abort: source private memory growth"):
        b5._run_one(dict(name="growth", duration_seconds=30, payload_bytes=1024, streams=1),
                    binaries={"server": Path("server"), "nbsr": Path("source")}, authority=tmp_path,
                    output=tmp_path, warmup_seconds=1, cooldown_seconds=1, sample_seconds=1)
    root = tmp_path / "raw/growth"
    assert len((root / "resources.ndjson").read_text().splitlines()) == 8
    assert len((root / "progress.ndjson").read_text().splitlines()) == 2
    assert (root / "failure.json").exists() and (root / "checksums.sha256").exists()
    assert peer.returncode == -1
