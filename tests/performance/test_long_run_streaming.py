from __future__ import annotations

import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
import sys
import time

import pytest

from scripts.performance.durable_memory import _windows_process_active
from scripts.run_performance_load_cell import durable_request_event
from scripts.run_performance_validation import measured_client


FIXTURE = Path(__file__).parent / "fixtures" / "long_run_child.py"


def test_durable_request_event_preserves_identity_and_terminal_result() -> None:
    assert durable_request_event({"sample_id": 7, "success": True}) == {
        "event": "request", "sample_id": 7, "started": True, "result": "completed",
    }
    assert durable_request_event({"sample_id": 8, "success": False, "error_type": "timeout"}) == {
        "event": "request", "sample_id": 8, "started": True, "result": "failed",
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
    assert len(lines) == 9
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
