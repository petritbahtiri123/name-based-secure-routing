import json
import argparse
from pathlib import Path

import pytest

from scripts import run_b5_sustained_capacity as b5


def test_failed_soak_preserves_partial_telemetry_commands_and_failure(monkeypatch, tmp_path):
    class Peer:
        pid = 1
        returncode = 0

        def wait(self, timeout):
            return 0

        def poll(self):
            return 0

    monkeypatch.setattr(b5.subprocess, "Popen", lambda *a, **k: Peer())
    monkeypatch.setattr(b5, "wait_ready", lambda *a: {"endpoint": "127.0.0.1:12345"})
    progress = {"event": "p2a_progress", "elapsed_ns": 1_000_000_000, "completed_operations": 1}

    def fail(*args, output_line_sink, resource_sink, **kwargs):
        output_line_sink(json.dumps(progress))
        resource_sink({"role": "source", "timestamp_ns": 1})
        raise RuntimeError("synthetic child failure")

    monkeypatch.setattr(b5, "measured_client", fail)
    with pytest.raises(RuntimeError, match="synthetic child failure"):
        b5._run_one(
            {"name": "partial", "duration_seconds": 10, "payload_bytes": 1024, "streams": 8},
            binaries={"server": Path("server"), "nbsr": Path("source")},
            authority=tmp_path, output=tmp_path,
            warmup_seconds=1, cooldown_seconds=1, sample_seconds=1,
        )
    root = tmp_path / "raw/partial"
    assert json.loads((root / "progress.ndjson").read_text()) == progress
    assert json.loads((root / "resources.ndjson").read_text())["role"] == "source"
    assert json.loads((root / "commands.json").read_text())["client"]
    assert json.loads((root / "failure.json").read_text())["classification"] == "INCOMPLETE"


def test_soak_accepts_existing_bounded_outstanding_workload_shape():
    assert b5._parse_run("near:3600:16384:1:2")["outstanding_per_stream"] == 2
    assert b5._parse_run("old:3600:1024:64")["outstanding_per_stream"] == 1
    for value in ("bad:3600:1024:65:1", "bad:3600:1024:1:65", "../bad:3600:1024:1:1"):
        with pytest.raises(argparse.ArgumentTypeError):
            b5._parse_run(value)


@pytest.mark.parametrize("schema,count", [("nbsr-p2a-repeat-v2", 1), ("nbsr-p2a-repeat-v1", 1),
                                         ("nbsr-p2a-repeat-v2", 2)])
def test_current_v2_result_reaches_soak_accounting(monkeypatch, tmp_path, schema, count):
    class Peer:
        pid = 1
        returncode = 0

        def wait(self, timeout):
            return 0

        def poll(self):
            return 0

    monkeypatch.setattr(b5.subprocess, "Popen", lambda *a, **k: Peer())
    monkeypatch.setattr(b5, "wait_ready", lambda *a: {"endpoint": "127.0.0.1:12345"})
    monkeypatch.setattr(b5, "analyze_soak_run", lambda *a, **k: {"checked": True})

    def measured(*args, output_line_sink, **kwargs):
        directory = tmp_path / "raw" / "current"
        (directory / "destination-diagnostics.ndjson").write_text("{}\n")
        output_line_sink(json.dumps({"event": "p2a_progress", "elapsed_ns": 10_000_000_000,
                                     "completed_operations": 1}))
        for _ in range(count):
            output_line_sink(json.dumps({"schema": schema, "completed_operations": 1}))
        return "", []

    monkeypatch.setattr(b5, "measured_client", measured)

    def run():
        return b5._run_one(
            {"name": "current", "duration_seconds": 10, "payload_bytes": 1024, "streams": 8},
            binaries={"server": Path("server"), "nbsr": Path("source")},
            authority=tmp_path, output=tmp_path,
            warmup_seconds=1, cooldown_seconds=1, sample_seconds=1,
        )

    if schema == "nbsr-p2a-repeat-v2" and count == 1:
        assert run()["checked"]
    else:
        with pytest.raises(RuntimeError, match="missing unique final P2A result"):
            run()
