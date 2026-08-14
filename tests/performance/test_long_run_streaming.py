from __future__ import annotations

import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
import sys
import time

import pytest

from scripts.performance.durable_memory import _windows_process_active
from scripts.run_performance_load_cell import durable_request_event, resource_phase, validate_memory_duration
from scripts.run_performance_validation import dirty_paths_outside, measured_client


FIXTURE = Path(__file__).parent / "fixtures" / "long_run_child.py"


def test_resource_phase_distinguishes_post_load_drain() -> None:
    assert resource_phase(29_999_999_999, warmup_ns=30_000_000_000, total_ns=90_000_000_000) == "warmup"
    assert resource_phase(30_000_000_000, warmup_ns=30_000_000_000, total_ns=90_000_000_000) == "steady"
    assert resource_phase(90_000_000_000, warmup_ns=30_000_000_000, total_ns=90_000_000_000) == "drain"


def test_durable_request_event_preserves_identity_and_terminal_result() -> None:
    assert durable_request_event({"sample_id": 7, "success": True}) == {
        "event": "request",
        "sample_id": 7,
        "started": True,
        "result": "completed",
    }


def test_short_memory_duration_requires_explicit_durable_validation_profile() -> None:
    validate_memory_duration(
        memory=True,
        durable_events=True,
        validation_profile=True,
        warmup_seconds=1,
        steady_seconds=8,
    )
    with pytest.raises(ValueError, match="at least 1 warm-up second and 8 steady seconds"):
        validate_memory_duration(
            memory=True,
            durable_events=True,
            validation_profile=True,
            warmup_seconds=1,
            steady_seconds=2,
        )
    with pytest.raises(ValueError, match="primary memory evidence requires"):
        validate_memory_duration(
            memory=True,
            durable_events=True,
            validation_profile=False,
            warmup_seconds=1,
            steady_seconds=2,
        )


def test_clean_tree_gate_excludes_only_the_exact_durable_output_root(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    durable = repository / "evidence" / "new-run"
    status = "?? evidence/new-run/raw.ndjson\n M scripts/runner.py\n?? unrelated.txt\n"

    assert dirty_paths_outside(repository, durable, status) == ["scripts/runner.py", "unrelated.txt"]
    with pytest.raises(ValueError, match="validation profile requires durable memory events"):
        validate_memory_duration(
            memory=False,
            durable_events=True,
            validation_profile=True,
            warmup_seconds=1,
            steady_seconds=2,
        )
    assert durable_request_event({"sample_id": 8, "success": False, "error_type": "timeout"}) == {
        "event": "request",
        "sample_id": 8,
        "started": True,
        "result": "failed",
        "error_type": "timeout",
    }


def test_measured_client_streams_output_lines_and_resources_during_execution(tmp_path: Path) -> None:
    lines: list[str] = []
    resources = []
    raw_path = tmp_path / "client.ndjson"

    stdout, retained = measured_client(
        [sys.executable, str(FIXTURE), "--mode", "completed"],
        cwd=tmp_path,
        server=SimpleNamespace(pid=os.getpid()),
        timeout=5,
        stdout_path=raw_path,
        output_line_sink=lines.append,
        resource_sink=resources.append,
        sampling_interval_seconds=0.01,
    )

    assert stdout == ""
    assert len(lines) == 12
    assert raw_path.read_text(encoding="utf-8").splitlines(keepends=True) == lines
    assert len(resources) >= 3
    assert resources == retained


def test_measured_client_timeout_terminates_the_client(tmp_path: Path) -> None:
    pid_path = tmp_path / "client.pid"
    with pytest.raises(subprocess.TimeoutExpired):
        measured_client(
            [sys.executable, str(FIXTURE), "--mode", "timeout", "--self-pid", str(pid_path)],
            cwd=tmp_path,
            server=SimpleNamespace(pid=os.getpid()),
            timeout=0.4,
            stdout_path=tmp_path / "client.ndjson",
            output_line_sink=lambda _line: None,
            sampling_interval_seconds=0.01,
        )
    pid = int(pid_path.read_text(encoding="ascii"))
    deadline = time.monotonic() + 2
    while process_exists(pid) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert process_exists(pid) is False


def process_exists(pid: int) -> bool:
    if os.name == "nt":
        return _windows_process_active(pid)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True
