from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from nbsr.gateway_journal import OwnershipJournal
from nbsr.gateway_plan import build_gateway_plan
from nbsr.gateway_profile import GatewayProfile, PlatformSnapshot

from tests.test_gateway_profile import profile_data, snapshot_data


ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "nbsr.gateway_cli", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def cli_files(tmp_path: Path, *, passing: bool = True) -> dict[str, Path]:
    profile_value = profile_data()
    profile = GatewayProfile.from_dict(profile_value)
    empty_value = snapshot_data()
    plan = build_gateway_plan(profile, PlatformSnapshot.from_dict(empty_value))
    observed = [operation.operation_id for operation in plan.operations]
    snapshot_value = snapshot_data(
        [{"kind": "route", "prefix": profile.synthetic_ipv4, "owner": profile.instance_id}],
        observed_operation_ids=observed,
        name_plane_healthy=passing,
        route_plane_healthy=True,
        resolver_parity=True,
        service_attribution=True,
        fair_share=True,
    )
    journal = OwnershipJournal.create(plan, ("nameserver", "192.0.2.53"), observed)
    paths = {name: tmp_path / f"{name}.json" for name in ("profile", "empty", "plan", "snapshot", "journal")}
    write_json(paths["profile"], profile_value)
    write_json(paths["empty"], empty_value)
    write_json(paths["plan"], plan.to_dict())
    write_json(paths["snapshot"], snapshot_value)
    write_json(paths["journal"], journal.to_dict())
    return paths


def test_plan_output_is_deterministic_and_inputs_are_not_mutated(tmp_path: Path) -> None:
    paths = cli_files(tmp_path)
    before = {name: path.read_bytes() for name, path in paths.items()}

    first = run_cli("plan", "--profile", str(paths["profile"]), "--snapshot", str(paths["empty"]))
    second = run_cli("plan", "--profile", str(paths["profile"]), "--snapshot", str(paths["empty"]))

    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout
    assert json.loads(first.stdout)["phase"] == "install"
    assert not first.stderr
    assert before == {name: path.read_bytes() for name, path in paths.items()}


def test_verify_uses_stable_success_and_failure_exit_codes(tmp_path: Path) -> None:
    passing = cli_files(tmp_path / "pass", passing=True)
    failing = cli_files(tmp_path / "fail", passing=False)

    success = run_cli(
        "verify",
        "--profile",
        str(passing["profile"]),
        "--plan",
        str(passing["plan"]),
        "--journal",
        str(passing["journal"]),
        "--snapshot",
        str(passing["snapshot"]),
    )
    failure = run_cli(
        "verify",
        "--profile",
        str(failing["profile"]),
        "--plan",
        str(failing["plan"]),
        "--journal",
        str(failing["journal"]),
        "--snapshot",
        str(failing["snapshot"]),
    )

    assert success.returncode == 0
    assert json.loads(success.stdout)["passed"] is True
    assert failure.returncode == 1
    assert json.loads(failure.stdout)["passed"] is False


def test_rollback_plan_is_deterministic_and_resolver_restore_is_last(tmp_path: Path) -> None:
    paths = cli_files(tmp_path)
    result = run_cli(
        "rollback-plan",
        "--profile",
        str(paths["profile"]),
        "--plan",
        str(paths["plan"]),
        "--journal",
        str(paths["journal"]),
    )

    assert result.returncode == 0
    value = json.loads(result.stdout)
    assert value["phase"] == "rollback"
    assert value["operations"][-1]["kind"] == "resolver_restore"


def test_rejected_input_is_bounded_closed_and_never_echoed(tmp_path: Path) -> None:
    secret = "credential-do-not-echo"
    oversized = tmp_path / "oversized.json"
    oversized.write_text(secret + ("x" * 65536), encoding="utf-8")
    empty = tmp_path / "empty.json"
    write_json(empty, snapshot_data())

    result = run_cli("plan", "--profile", str(oversized), "--snapshot", str(empty))
    assert result.returncode == 2
    assert result.stdout == ""
    assert "NBSR_GATEWAY_INPUT_REJECTED" in result.stderr
    assert secret not in result.stderr

    unknown = tmp_path / "unknown.json"
    write_json(unknown, profile_data(extra=secret))
    result = run_cli("plan", "--profile", str(unknown), "--snapshot", str(empty))
    assert result.returncode == 2
    assert secret not in result.stderr


def test_bounded_loader_reads_one_handle_without_preflight_stat(tmp_path: Path, monkeypatch) -> None:
    from nbsr import gateway_cli

    path = tmp_path / "small.json"
    write_json(path, profile_data())

    def forbidden_stat(self):
        raise AssertionError("separate stat creates a check/read race")

    monkeypatch.setattr(Path, "stat", forbidden_stat)
    assert gateway_cli._load_json(str(path))["instance_id"] == "lab-edge-01"


def test_cli_requires_explicit_paths_and_package_registers_entrypoint() -> None:
    result = run_cli("plan")
    assert result.returncode == 2
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'nbsr-gateway-plan = "nbsr.gateway_cli:main"' in pyproject


def test_example_profile_is_documentation_only_and_accepted() -> None:
    path = ROOT / "config" / "wp5-linux-gateway-lab.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    profile = GatewayProfile.from_dict(value)
    assert profile.synthetic_ipv4 == "192.0.2.0/24"
    assert profile.synthetic_ipv6 == "fd00:6e62:7372:5::/64"
