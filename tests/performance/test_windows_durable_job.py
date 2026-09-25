"""Windows durable completion cannot accept a parent that leaves descendants."""

import os
import subprocess
import sys

import pytest
from scripts.performance.durable_memory import run_durable_memory_child, _windows_process_active


@pytest.mark.skipif(os.name != "nt", reason="Windows job containment")
def test_parent_exit_with_live_descendant_is_not_authoritative(tmp_path):
    pid_file = tmp_path / "descendant.pid"
    program = (
        "import subprocess,sys,pathlib,json; "
        "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); "
        f"pathlib.Path({str(pid_file)!r}).write_text(str(p.pid)); "
        "print(json.dumps(dict(event='request',sample_id=0,started=True,result='completed')),flush=True)"
    )
    try:
        value = run_durable_memory_child([sys.executable, "-c", program], output=tmp_path / "out", timeout_seconds=5, offered_requests=1)
        assert value["authoritative_pass_eligible"] is False
        assert value["terminal_state"] == "failed"
        assert value["cleanup_verified"] is True
        assert not _windows_process_active(int(pid_file.read_text()))
    finally:
        if pid_file.exists() and _windows_process_active(int(pid_file.read_text())):
            subprocess.run(["taskkill", "/PID", pid_file.read_text(), "/T", "/F"], capture_output=True, check=True)


@pytest.mark.skipif(os.name != "nt", reason="Windows job containment")
@pytest.mark.parametrize("stage", ["assign", "resume"])
def test_failed_containment_never_runs_child_and_reaps_parent(tmp_path, monkeypatch, stage):
    from scripts.performance import windows_job

    marker = tmp_path / "ran"
    captured = []

    def fail(self, process):
        captured.append(process)
        raise OSError("injected " + stage + " failure")

    monkeypatch.setattr(windows_job.WindowsJob, stage, fail)
    with pytest.raises(OSError, match="injected"):
        windows_job.spawn_owned([sys.executable, "-c", f"import pathlib;pathlib.Path({str(marker)!r}).write_text('ran')"])
    assert len(captured) == 1 and captured[0].poll() is not None
    assert not marker.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows job containment")
def test_job_query_failure_denies_cleanup_and_authority(tmp_path, monkeypatch):
    from scripts.performance import windows_job

    def fail(self):
        raise OSError("injected inventory failure")

    monkeypatch.setattr(windows_job.WindowsJob, "members", fail)
    program = "import json;print(json.dumps(dict(event='request',sample_id=0,started=True,result='completed')),flush=True)"
    value = run_durable_memory_child([sys.executable, "-c", program], output=tmp_path / "out", timeout_seconds=5, offered_requests=1)
    assert value["cleanup_verified"] is False
    assert value["authoritative_pass_eligible"] is False
    assert value["terminal_state"] == "failed"
    assert "inventory failure" in value["runner_error"]


@pytest.mark.skipif(os.name != "nt", reason="Windows job containment")
def test_failed_launch_does_not_report_verified_job_cleanup(tmp_path, monkeypatch):
    from scripts.performance import durable_memory

    def fail(*args, **kwargs):
        raise OSError("job launch failed")

    monkeypatch.setattr(durable_memory, "spawn_owned", fail)
    value = durable_memory.run_durable_memory_child(["unused"], output=tmp_path / "out", timeout_seconds=5, offered_requests=1)
    assert value["cleanup_verified"] is False
    assert value["cleanup_basis"] == "UNAVAILABLE: child launch failed"
    assert value["authoritative_pass_eligible"] is False


@pytest.mark.skipif(os.name != "nt", reason="Windows job containment")
def test_timeout_inventory_error_still_preserves_failed_manifest(tmp_path, monkeypatch):
    from scripts.performance import windows_job

    def fail(self):
        raise OSError("injected timeout inventory failure")

    monkeypatch.setattr(windows_job.WindowsJob, "members", fail)
    value = run_durable_memory_child(
        [sys.executable, "-c", "import time;time.sleep(60)"], output=tmp_path / "out", timeout_seconds=0.2, offered_requests=1
    )
    assert value["terminal_state"] == "failed"
    assert value["cleanup_verified"] is False
    assert value["authoritative_pass_eligible"] is False
    assert (tmp_path / "out/terminal-manifest.json").is_file()


def test_unprepared_child_still_hits_unchanged_deadline(tmp_path):
    value = run_durable_memory_child(
        [sys.executable, '-c', 'import time;time.sleep(60)'],
        output=tmp_path/'out', timeout_seconds=0.2, offered_requests=1,
    )
    assert value['terminal_state'] == 'timed_out'
    assert value['cleanup_verified'] is True
    assert value['authoritative_pass_eligible'] is False
    assert value['counters']['started'] == value['counters']['persisted'] == 0
    assert value['counters']['timed_out'] == 1
