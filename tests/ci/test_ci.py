import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.ci.check import command_groups, run_command, validate_workflow


def test_quick_profiles_are_bounded_and_do_not_run_ignored_soak():
    for profile in ("python-core", "python-protocol", "rust", "go", "node"):
        commands = command_groups(profile)
        assert commands
        assert all("--ignored" not in cmd.argv for cmd in commands)
    assert len([cmd for cmd in command_groups("go") if cmd.name.endswith("test")]) == 5
    assert "--ignored" in command_groups("soak")[0].argv


def test_failure_summary_contains_only_fixed_metadata():
    result = run_command("synthetic", [sys.executable, "-c", "raise SystemExit(7)"], Path.cwd(), 5)
    assert set(result) == {"check", "exit_code", "timed_out"}
    assert result == {"check": "synthetic", "exit_code": 7, "timed_out": False}
    assert "argv" not in json.dumps(result)


def test_timeout_is_failure_and_reaps_descendant(tmp_path):
    pid_file = tmp_path / "child.pid"
    script = (
        "import subprocess,sys,time; from pathlib import Path; "
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
        "Path(sys.argv[1]).write_text(str(child.pid)); time.sleep(60)"
    )
    result = run_command("timeout", [sys.executable, "-c", script, str(pid_file)], Path.cwd(), 2)
    assert result["timed_out"]
    assert result["exit_code"] == 124
    pid = int(pid_file.read_text())
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.OpenProcess(0x1000, False, pid)
        if handle:
            try:
                code = wintypes.DWORD()
                assert kernel.GetExitCodeProcess(handle, ctypes.byref(code))
                assert code.value != 259  # STILL_ACTIVE
            finally:
                kernel.CloseHandle(handle)
    else:
        stat = Path(f"/proc/{pid}/stat")
        # A killed orphan may remain a zombie until the runner's init reaps it.
        assert not stat.exists() or stat.read_text().split(") ", 1)[1].startswith("Z ")


@pytest.mark.parametrize("final_cleanup_fails", [False, True])
def test_tree_cleanup_failure_still_reaps_and_records_timeout(monkeypatch, final_cleanup_fails):
    from scripts.ci import check

    class Process:
        pid = 123
        killed = False

        def wait(self, timeout):
            if not self.killed:
                raise subprocess.TimeoutExpired("synthetic", timeout)
            return -9

        def poll(self):
            return None

        def kill(self):
            self.killed = True
            if final_cleanup_fails:
                raise OSError("synthetic final cleanup failure")

    def fail(*args, **kwargs):
        raise OSError("synthetic cleanup failure")

    process = Process()
    monkeypatch.setattr(check.subprocess, "Popen", lambda *a, **kw: process)
    if os.name == "nt":
        monkeypatch.setattr(check.subprocess, "run", fail)
    else:
        monkeypatch.setattr(check.os, "killpg", fail)
    assert run_command("failure", ["unused"], Path.cwd(), 1) == {
        "check": "failure", "exit_code": 125, "timed_out": True,
    }
    assert process.killed


def test_validator_rejects_privileged_event():
    with pytest.raises(ValueError, match="event"):
        validate_workflow({"on": {"pull_request_target": {}}})


def test_checked_in_workflows_have_security_contract():
    paths = sorted(Path(".github/workflows").glob("*.yml"))
    assert len(paths) == 2
    for path in paths:
        validate_workflow(json.loads(path.read_text(encoding="utf-8")))


@pytest.mark.parametrize("filename,job_id", [
    ("ci.yml", "python"), ("ci.yml", "rust"), ("ci.yml", "go"),
    ("extended.yml", "extended"),
])
def test_job_environment_rejects_runner_context(filename, job_id):
    workflow = json.loads((Path(".github/workflows") / filename).read_text())
    workflow["jobs"][job_id].setdefault("env", {})["CACHE"] = "${{ runner.temp }}/cache"
    with pytest.raises(ValueError, match="runner context"):
        validate_workflow(workflow)


@pytest.mark.parametrize("mutation", ["permissions", "action", "credentials", "cache", "artifact"])
def test_security_contract_rejects_unsafe_workflow_mutations(mutation):
    workflow = json.loads(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["python"]["steps"]
    if mutation == "permissions":
        workflow["permissions"]["contents"] = "write"
    elif mutation == "action":
        steps[0]["uses"] = "actions/checkout@main"
    elif mutation == "credentials":
        steps[0]["with"]["persist-credentials"] = True
    elif mutation == "cache":
        next(s for s in steps if s.get("uses", "").startswith("actions/cache/save@"))["if"] = "success()"
    else:
        next(s for s in steps if s.get("uses", "").startswith("actions/upload-artifact@"))["with"]["path"] = "**/*"
    with pytest.raises(ValueError):
        validate_workflow(workflow)
