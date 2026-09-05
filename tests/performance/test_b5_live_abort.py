"""Live guard regressions; synthetic only, no process or benchmark execution."""

import hashlib
import json
from pathlib import Path

import pytest

from scripts import run_b5_sustained_capacity as b5
from scripts.performance import sustained_capacity


@pytest.mark.parametrize("goodput,p99,reason", [(94, 100, "goodput"), (100, 121, "p99"),
                                               (95, 120, None), (100, 100, None)])
def test_live_drift_uses_disjoint_thirds_and_strict_plan_thresholds(goodput, p99, reason):
    progress = [{"goodput_bytes_per_second": 100, "p99_latency_ns": 100} for _ in range(3)]
    progress += [{"goodput_bytes_per_second": goodput, "p99_latency_ns": p99} for _ in range(3)]
    assert sustained_capacity.live_drift_failure(progress) == reason
    assert sustained_capacity.live_drift_failure([progress[0], progress[-1]]) is None


def test_live_drift_does_not_invent_missing_latency_samples():
    progress = [{"goodput_bytes_per_second": 100, "p99_latency_ns": None} for _ in range(3)]
    assert sustained_capacity.live_drift_failure(progress) is None


@pytest.mark.parametrize("failure_field", ["errors", "timeouts", "goodput", "p99"])
def test_soak_aborts_on_first_error_window_and_preserves_evidence(
    monkeypatch, tmp_path, failure_field
):
    # Accepted v2 plan Task 6: abort on FAIL thresholds, including errors/timeouts;
    # preserve partial raw data. No elapsed-time or load threshold is introduced.
    class Peer:
        pid = 1
        returncode = None
        killed = False

        def poll(self):
            return self.returncode

        def kill(self):
            self.killed = True
            self.returncode = -1

        def wait(self, timeout):
            return self.returncode

    peer = Peer()
    monkeypatch.setattr(b5.subprocess, "Popen", lambda *args, **kwargs: peer)
    monkeypatch.setattr(b5, "wait_ready", lambda *args: {"endpoint": "127.0.0.1:12345"})
    progress = {
        "event": "p2a_progress", "schema": "nbsr-b5-progress-v1",
        "window_index": 1, "elapsed_ns": 1_000_000_000,
        "interval_ns": 1_000_000_000, "completed_operations": 1,
        "completed_total": 1, "goodput_bytes_per_second": 1024,
        "p50_latency_ns": 10, "p95_latency_ns": 20, "p99_latency_ns": 30,
        "errors": 0, "timeouts": 0,
    }
    if failure_field in ("errors", "timeouts"):
        progress[failure_field] = 1
    elif failure_field == "goodput":
        progress["goodput_bytes_per_second"] = 900
    else:
        progress["p99_latency_ns"] = 37
    continued_after_failure = []

    def measured(*args, output_line_sink, resource_sink, **kwargs):
        resource_sink({"role": "source", "timestamp_ns": 1})
        if failure_field in ("goodput", "p99"):
            for index in (1, 2):
                baseline = {**progress, "window_index": index, "goodput_bytes_per_second": 1024,
                            "p99_latency_ns": 30}
                output_line_sink(json.dumps(baseline))
            progress["window_index"] = 3
        output_line_sink(json.dumps(progress))
        continued_after_failure.append(True)
        raise AssertionError("workload continued after the first FAIL window")

    monkeypatch.setattr(b5, "measured_client", measured)
    with pytest.raises(RuntimeError, match="soak live abort"):
        b5._run_one(
            {"name": "abort", "duration_seconds": 3600, "payload_bytes": 1024, "streams": 8},
            binaries={"server": Path("server"), "nbsr": Path("source")},
            authority=tmp_path, output=tmp_path,
            warmup_seconds=10, cooldown_seconds=30, sample_seconds=1,
        )
    assert not continued_after_failure
    assert peer.killed
    root = tmp_path / "raw/abort"
    assert json.loads((root / "progress.ndjson").read_text().splitlines()[-1]) == progress
    assert json.loads((root / "resources.ndjson").read_text())["role"] == "source"
    failure = json.loads((root / "failure.json").read_text())
    assert failure["classification"] == "INCOMPLETE"
    assert failure_field in failure["message"]
    assert not (root / "analysis.json").exists()
    for line in (root / "checksums.sha256").read_text().splitlines():
        digest, relative = line.split("  ", 1)
        assert hashlib.sha256((root / relative).read_bytes()).hexdigest() == digest
