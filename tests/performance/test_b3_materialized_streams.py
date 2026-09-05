"""Explicit live gate; set both NBSR_B3_LIVE_TARGET and NBSR_B3_LIVE_OUTPUT.

This test is never part of ordinary unit runs. Every attempt retains its own
binaries, diagnostics and failed assertion before any stream-release marker.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil

import pytest

from scripts import run_b3_session_lifecycle as b3
from scripts.run_b4b_task4k import checksums


@pytest.mark.skipif(not (os.environ.get("NBSR_B3_LIVE_TARGET") and os.environ.get("NBSR_B3_LIVE_OUTPUT")),
                    reason="explicit isolated live B3 target/output required")
def test_four_destination_stream_handles_are_live_before_release(monkeypatch):
    root = Path(os.environ["NBSR_B3_LIVE_OUTPUT"])
    root.mkdir(parents=True, exist_ok=False)
    target = Path(os.environ["NBSR_B3_LIVE_TARGET"])
    (root / "binaries").mkdir()
    binaries = {}
    for role, filename in (("rust", "perf_rust_source.exe"), ("server", "wp8_interop_server.exe")):
        destination = root / "binaries" / filename
        shutil.copy2(target / "release" / filename, destination)
        binaries[role] = destination
    b3.write_json(root / "environment.json", {
        "classification": "LIVE_REGRESSION_ONLY",
        "expected_channels": 2, "expected_materialized_streams": 4,
        "binary_sha256": {role: hashlib.sha256(path.read_bytes()).hexdigest()
                          for role, path in binaries.items()},
    })
    spec = dict(name="materialized-2x2", kind="streams", active_count=4,
                sessions=1, channels=2, streams=2, cycles=1, start_rate=100,
                materialized_streams=True)
    cell_dir = root / "raw" / "rust-rust" / spec["name"]
    original_capture = b3.capture

    def capture(resources, server, clients, **kwargs):
        if kwargs["phase"] == "active":
            lifecycle = Path(server.args[server.args.index("--b3-report-gate") + 1])
            assert not (lifecycle / "connection-0.release").exists()
            marker = lifecycle / "destination-0.active"
            assert marker.is_file(), "destination must publish materialized ownership before release"
            observed = json.loads(marker.read_text())
            b3.write_json(root / "pre-release-destination.json", observed)
            assert not (lifecycle / "connection-0.release").exists()
            assert observed["quic_streams_current_live"] == 4
            assert observed["application_streams_current_live"] == 4
            assert observed["service_channels_current_live"] == 2
            assert observed["transport_sessions_current_live"] == 1
            source_rows = [json.loads(line) for line in (cell_dir / "source-0.stdout").read_text().splitlines()]
            ready = [row for row in source_rows if row.get("phase") == "b3_materialized_streams_ready"]
            assert len(ready) == 1
            assert ready[0]["quic_streams_current_live"] == 4
            assert ready[0]["service_channels_current_live"] == 2
            assert not any(row.get("success") is True for row in source_rows)
        original_capture(resources, server, clients, **kwargs)

    monkeypatch.setattr(b3, "capture", capture)
    try:
        row = b3.run_cell("rust-rust", spec, binaries, root,
                          idle_seconds=1, active_seconds=1, cooldown_seconds=1, cadence=0.25)
        assert row["cleanup"]["all_zero"]
        completed = [r for r in row["client_results"] if r.get("success") is True]
        assert len(completed) == 4
        assert all(r["bytes_transmitted"] == r["bytes_received"] for r in completed)
    finally:
        checksums(root)
