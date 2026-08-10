from __future__ import annotations

import gzip
import json
import os
from pathlib import Path
import sys
import time

from scripts.performance.durable_memory import _windows_process_active, run_durable_memory_child


FIXTURE = Path(__file__).parent / "fixtures" / "long_run_child.py"


def documents(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def process_exists(pid: int) -> bool:
    if os.name == "nt":
        return _windows_process_active(pid)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def command(mode: str, descendant_pid: Path | None = None) -> list[str]:
    result = [sys.executable, str(FIXTURE), "--mode", mode]
    if descendant_pid is not None:
        result.extend(["--descendant-pid", str(descendant_pid)])
    return result


def test_completed_run_flushes_incremental_request_resource_and_runtime_evidence(tmp_path: Path) -> None:
    output = tmp_path / "completed"
    result = run_durable_memory_child(
        command("completed"), output=output, timeout_seconds=5, offered_requests=3,
        buffer_capacity=2, flush_records=1, flush_interval_seconds=0.01,
    )

    with gzip.open(output / "raw.ndjson.gz", "rt", encoding="utf-8") as handle:
        request_records = [json.loads(line) for line in handle]
    assert [item["sample_id"] for item in request_records] == [0, 1, 2]
    assert (output / "raw.ndjson").exists() is False
    assert len(documents(output / "resources.ndjson")) == 3
    assert len(documents(output / "runtime.ndjson")) == 3
    assert result["terminal_state"] == "completed"
    assert result["partial_but_durable"] is False
    assert result["authoritative_pass_eligible"] is True
    assert result["counters"] == {
        "offered": 3, "started": 3, "completed": 3, "failed": 0,
        "timed_out": 0, "persisted": 3,
    }
    assert result["request_evidence"]["path"] == "raw.ndjson.gz"
    assert len(result["request_evidence"]["uncompressed_sha256"]) == 64
    assert json.loads((output / "terminal-manifest.json").read_text(encoding="utf-8")) == result


def test_timeout_retains_partial_series_reconciles_counts_and_denies_authority(tmp_path: Path) -> None:
    output = tmp_path / "timeout"
    result = run_durable_memory_child(
        command("timeout"), output=output, timeout_seconds=0.4, offered_requests=5,
        buffer_capacity=2, flush_records=1, flush_interval_seconds=0.01,
    )

    assert len(documents(output / "raw.ndjson")) == 3
    assert len(documents(output / "resources.ndjson")) == 3
    assert len(documents(output / "runtime.ndjson")) == 3
    assert result["terminal_state"] == "timed_out"
    assert result["partial_but_durable"] is True
    assert result["authoritative_pass_eligible"] is False
    assert result["cleanup_verified"] is True
    assert result["counters"] == {
        "offered": 5, "started": 3, "completed": 3, "failed": 0,
        "timed_out": 2, "persisted": 3,
    }


def test_failure_flushes_all_buffered_series_and_records_failed_terminal_state(tmp_path: Path) -> None:
    output = tmp_path / "failed"
    result = run_durable_memory_child(
        command("failed"), output=output, timeout_seconds=5, offered_requests=3,
        buffer_capacity=8, flush_records=8, flush_interval_seconds=10,
    )

    assert len(documents(output / "raw.ndjson")) == 3
    assert len(documents(output / "resources.ndjson")) == 3
    assert len(documents(output / "runtime.ndjson")) == 3
    assert result["terminal_state"] == "failed"
    assert result["child_return_code"] == 7
    assert result["partial_but_durable"] is True
    assert result["authoritative_pass_eligible"] is False
    assert result["counters"] == {
        "offered": 3, "started": 3, "completed": 2, "failed": 1,
        "timed_out": 0, "persisted": 3,
    }


def test_failed_run_without_records_is_not_labeled_partial_but_durable(tmp_path: Path) -> None:
    result = run_durable_memory_child(
        command("empty-failed"), output=tmp_path / "empty-failed", timeout_seconds=5,
        offered_requests=3, buffer_capacity=2, flush_records=1, flush_interval_seconds=0.01,
    )

    assert result["terminal_state"] == "failed"
    assert result["child_return_code"] == 9
    assert result["partial_but_durable"] is False
    assert result["authoritative_pass_eligible"] is False


def test_completed_validation_profile_cannot_be_authoritative(tmp_path: Path) -> None:
    result = run_durable_memory_child(
        command("completed"), output=tmp_path / "validation", timeout_seconds=5,
        offered_requests=3, authoritative_run=False,
        buffer_capacity=2, flush_records=1, flush_interval_seconds=0.01,
    )

    assert result["terminal_state"] == "completed"
    assert result["authoritative_run"] is False
    assert result["authoritative_pass_eligible"] is False


def test_timeout_terminates_and_verifies_descendant_process_cleanup(tmp_path: Path) -> None:
    descendant_pid_path = tmp_path / "descendant.pid"
    result = run_durable_memory_child(
        command("timeout", descendant_pid_path), output=tmp_path / "tree-timeout",
        timeout_seconds=0.4, offered_requests=5, buffer_capacity=2,
        flush_records=1, flush_interval_seconds=0.01,
    )
    descendant_pid = int(descendant_pid_path.read_text(encoding="ascii"))

    deadline = time.monotonic() + 2
    while process_exists(descendant_pid) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert process_exists(descendant_pid) is False
    assert result["cleanup_verified"] is True
    assert descendant_pid in result["terminated_process_ids"]
