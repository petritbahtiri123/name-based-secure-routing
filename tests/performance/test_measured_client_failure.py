"""Regressions for long-run child ownership and diagnostic backpressure."""
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import pytest

from scripts.run_performance_validation import measured_client
from tests.performance.test_long_run_streaming import process_exists


def test_streaming_child_can_write_more_than_stderr_pipe_capacity(tmp_path: Path):
    lines = []
    measured_client(
        [sys.executable, "-c", "import sys; sys.stderr.write('x'*1048576); print('done',flush=True)"],
        cwd=tmp_path, server=SimpleNamespace(pid=os.getpid()), timeout=2,
        output_line_sink=lines.append,
    )
    assert lines == ["done\n"]


def test_callback_failure_stops_owned_child_without_waiting_for_workload_timeout(tmp_path: Path):
    pids = []

    def reject(_line):
        raise ValueError("invalid progress")

    started = time.monotonic()
    with pytest.raises(RuntimeError, match="output reader failed"):
        measured_client(
            [sys.executable, "-c", "import time; print('bad',flush=True); time.sleep(30)"],
            cwd=tmp_path, server=SimpleNamespace(pid=os.getpid()), timeout=3,
            output_line_sink=reject, client_started=pids.append,
        )
    assert time.monotonic() - started < 2
    assert len(pids) == 1 and not process_exists(pids[0])


def test_start_callback_failure_reaps_owned_child(tmp_path: Path):
    pids = []

    def reject(pid):
        pids.append(pid)
        raise ValueError("start rejected")

    try:
        with pytest.raises(ValueError, match="start rejected"):
            measured_client(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                cwd=tmp_path, server=SimpleNamespace(pid=os.getpid()), timeout=2,
                client_started=reject,
            )
        assert len(pids) == 1 and not process_exists(pids[0])
    finally:
        # The literal RED exposes an orphan; terminate only this test-owned PID.
        if pids and process_exists(pids[0]):
            os.kill(pids[0], 9)
