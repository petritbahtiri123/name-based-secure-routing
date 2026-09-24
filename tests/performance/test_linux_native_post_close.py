import json
from pathlib import Path

import pytest

from scripts.performance.linux_b5_placement import seal_output
from scripts.performance.post_close_cleanup import FIELDS
from tests.performance.test_linux_native_pair import fixture, SHA, put


def report(role="source", pid=123):
    return dict(
        schema="nbsr-p2a-post-close-v1",
        role=role,
        pid=pid,
        diagnostics_enabled_before_run=True,
        runtime_state="runtime_alive",
        ownership=dict.fromkeys(FIELDS, 0),
    )


def test_cohort_comparison_distinguishes_post_close_observer_mode(tmp_path):
    from scripts.performance.linux_native_cohort import comparison_identity
    source, _ = fixture(tmp_path)
    env = json.loads((source / 'environment.json').read_text())
    assert comparison_identity(env) != comparison_identity(env | {'post_close_reports': True})


@pytest.mark.parametrize("role", ["source", "destination"])
def test_requested_report_is_bound_to_owned_role_pid_and_zero_counters(tmp_path, role):
    from scripts.performance.linux_native_peer import validate_post_close

    cell = dict(path="nbsr")
    with pytest.raises(FileNotFoundError):
        validate_post_close(tmp_path, cell, role, 123, True)
    value = report(role)
    put(tmp_path, "cleanup.json", value)
    assert validate_post_close(tmp_path, cell, role, 123, True) == "ALL_11_ZERO"
    for changed in [dict(pid=999), dict(role="wrong"), dict(ownership={**value["ownership"], FIELDS[0]: 1})]:
        put(tmp_path, "cleanup.json", {**value, **changed})
        with pytest.raises(ValueError):
            validate_post_close(tmp_path, cell, role, 123, True)


def test_direct_and_default_do_not_invent_owned_resource_evidence(tmp_path):
    from scripts.performance.linux_native_peer import validate_post_close

    assert validate_post_close(tmp_path, dict(path="direct"), "source", 123, True) == "NOT_APPLICABLE_DIRECT"
    assert validate_post_close(tmp_path, dict(path="nbsr"), "source", 123, False) == "NOT_MEASURED"
    with pytest.raises(ValueError):
        validate_post_close(tmp_path, dict(path="nbsr"), "source", 123, 1)


@pytest.mark.parametrize("role", ["source", "destination"])
def test_report_flag_uses_existing_nbsr_benchmark_contract(tmp_path, role):
    from scripts.performance.linux_native_peer import native_command

    cell = dict(path="nbsr", cores=1, payload_bytes=1024, streams=8, outstanding=1)
    endpoint = "192.0.2.2:4444" if role == "source" else None
    argv, _ = native_command(
        cell, role, Path("/bins"), Path("/private"), tmp_path, bind="192.0.2.1:0", endpoint=endpoint, post_close_reports=True
    )
    assert argv[argv.index("--p2a-cleanup-report") + 1] == str(tmp_path / "cleanup.json")


def enable_reports(root, role):
    env = json.loads((root / "environment.json").read_text())
    env.update(post_close_reports=True, output_root="/evidence/" + role)
    put(root, "environment.json", env)
    command = json.loads((root / "command.json").read_text())
    command["argv"] += ["--p2a-cleanup-report", "/evidence/" + role + "/cleanup.json"]
    put(root, "command.json", command)
    result = json.loads((root / "result.json").read_text())
    result["runtime_ownership_cleanup"] = "ALL_11_ZERO"
    put(root, "result.json", result)
    put(root, "cleanup.json", report(role))
    seal_output(root)


def test_pair_gate_revalidates_reports_instead_of_trusting_resealed_claim(tmp_path):
    from scripts.performance.linux_native_pair import analyze_pair

    source, destination = fixture(tmp_path)
    enable_reports(source, "source")
    enable_reports(destination, "destination")
    assert analyze_pair(source, destination, source_sha=SHA)["runtime_ownership_cleanup"] == "ALL_11_ZERO"
    value = report("destination")
    value["ownership"][FIELDS[3]] = 1
    put(destination, "cleanup.json", value)
    seal_output(destination)
    with pytest.raises(ValueError):
        analyze_pair(source, destination, source_sha=SHA)


def test_pair_gate_rejects_asymmetric_mode_and_missing_executed_flag(tmp_path):
    from scripts.performance.linux_native_pair import analyze_pair

    source, destination = fixture(tmp_path)
    enable_reports(source, "source")
    with pytest.raises(ValueError):
        analyze_pair(source, destination, source_sha=SHA)
    enable_reports(destination, "destination")
    command = json.loads((source / "command.json").read_text())
    command["argv"] = command["argv"][:-2]
    put(source, "command.json", command)
    seal_output(source)
    with pytest.raises(ValueError):
        analyze_pair(source, destination, source_sha=SHA)


def test_coordinator_declares_requested_mode_on_both_peers():
    from scripts.performance.linux_native_finite_run import validate_config, endpoint_arguments
    from tests.performance.test_linux_native_finite_run import config

    value = config()
    value["post_close_reports"] = True
    validate_config(value)
    assert all("--post-close-reports" in endpoint_arguments(value, role) for role in ("source", "destination"))
    value["post_close_reports"] = 1
    with pytest.raises(ValueError):
        validate_config(value)


def test_requested_true_cannot_accept_collected_false_mode(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from scripts.performance import linux_native_finite_run as run
    from tests.performance.test_linux_native_finite_run import config

    value = config()
    value["post_close_reports"] = True

    class Manager:
        def __init__(self, *args, **kwargs):
            self.children = dict.fromkeys(("source", "destination"), object())
            self.ledger = SimpleNamespace(positions=dict(source=1, destination=1), received={})

        start_command = wait = send = finish = lambda *args: None

        def close(self):
            return {role: dict(exit_code=0, local_relay_forced=False) for role in self.children}

    def collect(target, role, output, **kwargs):
        peer = output / role / "peer"
        peer.mkdir(parents=True)
        put(peer, "environment.json", dict(bind=target["bind"], post_close_reports=False))

    monkeypatch.setattr(run, "Manager", Manager)
    monkeypatch.setattr(run, "drive", lambda *args: None)
    monkeypatch.setattr(run, "collect", collect)
    monkeypatch.setattr(run, "check_endpoint", lambda *args: dict(events={}, index_sha256="unused"))
    monkeypatch.setattr(
        run, "analyze_pair", lambda *args, **kwargs: dict(cell=dict(path="direct", payload_bytes=1024, streams=8, outstanding=1, cores=1))
    )
    with pytest.raises(ValueError, match="requested/actual cleanup mode"):
        run.execute(value, tmp_path / "out")
    assert not (tmp_path / "out/result.json").exists()
