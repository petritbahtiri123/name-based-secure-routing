import json
import os
import subprocess
import sys
from pathlib import Path


import pytest

from scripts.ci.check import command_groups, run_command, validate_workflow


def test_isolated_genesis_kar_target_selected_without_live_execution():
    rust = next(c for c in command_groups("rust") if c.name == "rust-connector")
    assert rust.argv.count("connector_kar") == 1
    assert "--ignored" not in rust.argv
    registry = json.loads(Path("docs/protocol/registries/connector-registration-development-v1.json").read_text())
    assert registry["runtime_authorized"] is False
    assert registry["live_trust_authorized"] is False


def test_inclusion_persistence_ci_is_memory_only():
    command = next(c for c in command_groups("python-protocol") if c.name == "inclusion-persistence-local")
    assert command.argv[1:] == (
        "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/federation/test_inclusion_persistence.py",
    )


def test_connected_authority_local_vectors_and_target_are_selected():
    rust = next(c for c in command_groups("rust") if c.name == "rust-connector")
    assert rust.argv.count("connector_authority") == 1
    vectors = next(c for c in command_groups("python-protocol") if c.name == "connected-authority-vectors")
    assert vectors.argv[1:] == ("-m", "scripts.check_connected_authority_vectors", "--check")
    assert "--ignored" not in rust.argv


def test_quick_profiles_are_bounded_and_do_not_run_ignored_soak():
    for profile in ("python-core", "python-protocol", "rust", "go", "node"):
        commands = command_groups(profile)
        assert commands
        assert all("--ignored" not in cmd.argv for cmd in commands)
    assert len([cmd for cmd in command_groups("go") if cmd.name.endswith("test")]) == 6
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


def test_node_cross_language_checks_install_constrained_python_dependencies():
    workflow = json.loads(Path(".github/workflows/ci.yml").read_text())
    steps = workflow["jobs"]["node-policy"]["steps"]
    install = next((i for i, step in enumerate(steps) if step.get("run") ==
                    "python -m pip install --constraint constraints/runtime.txt -e ."), None)
    verify = next(i for i, step in enumerate(steps) if step.get("name") == "Node independent verifiers")
    assert install is not None and install < verify


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


def test_federation_v2_commands_opt_in_explicitly():
    for profile, name in (("python-protocol", "federation-v2-vectors"), ("go", "go-federation-v2"), ("node", "node-federation-v2")):
        command = next(cmd for cmd in command_groups(profile) if cmd.name == name)
        index = command.argv.index("--version")
        assert command.argv[index + 1] == "federation-v0.1-development-v2"
        assert command.argv[-1].endswith("vectors/federation-v0.1-development-v2")


def test_connector_offline_suites_are_selected():
    core = command_groups("python-core")[0].argv
    for name in ("control_model", "federation_model", "registration_authority_offline", "authority_timer_offline"):
        assert f"tests/test_connector_{name}.py" in core
    assert "deploy/single-instance/test_validate_config.py" in core
    rust = next(c for c in command_groups("rust") if c.name == "rust-connector")
    for target in ("connector_control", "connector_registration", "connector_loopback"):
        assert target in rust.argv
    for kind in ("test", "vet"):
        go = next(c for c in command_groups("go") if c.name == f"go-connector-{kind}")
        assert "connector_development" in go.argv and "./connector" in go.argv
    assert any("scripts/verify_connector_registration_vectors.mjs" in c.argv for c in command_groups("node"))


def test_gateway_cli_process_contract_is_selected_with_its_neighbors():
    core = command_groups("python-core")[0].argv
    for name in ("cli", "plan", "profile", "verify", "journal"):
        assert core.count(f"tests/test_gateway_{name}.py") == 1


def test_native_signature_slice_and_python_oracle_are_selected_without_activation():
    rust = next(c for c in command_groups("rust") if c.name == "rust-connector")
    assert rust.argv.count("connector_signature") == 1
    oracle = next(c for c in command_groups("python-protocol") if c.name == "connector-signature-fixtures")
    assert oracle.argv[1:] == ("-m", "scripts.extract_connector_signature_fixtures", "--check")
    registry = json.loads(Path("docs/protocol/registries/connector-registration-development-v1.json").read_text())
    assert registry["runtime_authorized"] is False
    assert registry["live_trust_authorized"] is False


def test_connector_signature_ci_command_checks_fixtures_without_pythonpath():
    root = Path(__file__).resolve().parents[2]
    command = next(c for c in command_groups("python-protocol") if c.name == "connector-signature-fixtures")
    # A pytest import or an inherited repository PYTHONPATH must not hide a broken CLI.
    env = {key: value for key, value in os.environ.items() if key.upper() != "PYTHONPATH"}
    result = subprocess.run(command.argv, cwd=root / command.cwd, env=env,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "signature cases verified with Python; checked" in result.stdout


def test_normal_revocation_conformance_is_selected_without_runtime_activation():
    command = next(c for c in command_groups("python-protocol") if c.name == "normal-revocation-conformance")
    assert command.argv[1:] == ("-m", "scripts.normal_revocation_conformance", "--check")
    amendment = json.loads(Path("docs/protocol/registries/federation-v0.1-normal-revocation-conformance-v1.json").read_text())
    assert amendment["runtime_enabled"] is amendment["live_enabled"] is False


def test_revocation_inclusion_v2_selection_stays_local():
    command = next(c for c in command_groups("python-protocol") if c.name == "revocation-inclusion-v2")
    assert command.argv[1:] == ("-m", "scripts.revocation_inclusion_v2", "--check")
    amendment = json.loads(Path("docs/protocol/registries/revocation-inclusion-local-v2.json").read_text())
    assert amendment["runtime_enabled"] is amendment["live_enabled"] is False
    assert amendment["record_version"] == 2


def test_connector_loopback_is_manual_and_prebuilt():
    commands = command_groups("connector-loopback")
    assert "--no-run" in commands[0].argv
    assert "-c" in commands[1].argv
    assert "--ignored" in commands[2].argv and "--exact" in commands[2].argv
    workflow = json.loads(Path(".github/workflows/extended.yml").read_text())
    assert "connector-loopback" in workflow["on"]["workflow_dispatch"]["inputs"]["suite"]["options"]
    steps = workflow["jobs"]["extended"]["steps"]
    setup = next(s for s in steps if s.get("uses", "").startswith("actions/setup-go@"))
    assert setup["if"] == "inputs.suite == 'connector-loopback'"
    assert setup["with"]["go-version"] == "1.26.5"


@pytest.mark.parametrize("build_code,live_code", [(7, 0), (0, 124), (0, 0)])
def test_loopback_worker_is_owned_and_environment_restored(monkeypatch, tmp_path, build_code, live_code):
    from scripts.ci import check

    calls = []
    monkeypatch.setattr(check.tempfile, "tempdir", str(tmp_path.resolve()))
    monkeypatch.setattr(check, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["check.py", "connector-loopback"])
    monkeypatch.setenv("NBSR_CONNECTOR_GO_TEST", "prior-worker")

    def run(name, argv, cwd, seconds):
        calls.append((name, argv, seconds))
        if name == "connector-loopback-build":
            return {"exit_code": 0}
        if name == "connector-worker-build":
            worker = Path(argv[argv.index("-o") + 1])
            worker.write_text("synthetic worker")
            return {"exit_code": build_code}
        assert Path(os.environ["NBSR_CONNECTOR_GO_TEST"]).exists()
        assert "--exact" in argv and "--ignored" in argv
        return {"exit_code": live_code}

    monkeypatch.setattr(check, "run_command", run)
    assert check.main() == int(bool(build_code or live_code))
    assert len(calls) == (2 if build_code else 3)
    assert os.environ["NBSR_CONNECTOR_GO_TEST"] == "prior-worker"
    worker = Path(calls[1][1][calls[1][1].index("-o") + 1])
    assert not worker.parent.exists()
    assert all(c[2] == 90 for c in calls)
