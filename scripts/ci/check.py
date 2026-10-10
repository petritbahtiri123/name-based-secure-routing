"""Explicit CI command profiles; no dependency installation or infrastructure startup."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
GO_MODULES = (
    "client/nbsr-go-client", "client/nbsr-go-client/demo", "interop/nbsr-go-peer",
    "verifiers/federation-go", "deploy/isp-federation-poc/adapter",
)
CORE_TESTS = (
    "test_control_plane", "test_destination_policy", "test_dns_stub", "test_name_node",
    "test_name_registry", "test_name_relay", "test_name_security", "test_originset",
    "test_resolution_state", "test_route_registry", "test_secure_files", "test_security",
    "test_service_tls", "test_services", "test_synthetic", "test_verifier",
    "test_gateway_plan", "test_gateway_profile", "test_gateway_verify", "test_gateway_journal",
    "test_wp6_continuity_state", "test_wp6_failover", "test_wp6_replication",
    "test_wp7_admission", "test_wp7_limits", "test_wp7_operator_model", "test_wp7_review_fixes",
)


@dataclass(frozen=True)
class Command:
    name: str
    argv: tuple[str, ...]
    cwd: str = "."


def command_groups(profile: str) -> list[Command]:
    py = sys.executable
    cargo = ("cargo", "test", "--locked", "--offline", "--manifest-path", "crates/nbsr-transport/Cargo.toml",
             "--features", "benchmark-harness", "--jobs", "2")
    if profile == "python-core":
        return [Command("python-core", (py, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/ci",
                                       *(f"tests/{name}.py" for name in CORE_TESTS))),
                Command("python-dependencies", (py, "-m", "pip", "check"))]
    if profile == "python-protocol":
        return [*(Command(f"python-{directory}", (py, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                                                 f"tests/{directory}",
                                                 "--ignore=tests/federation/test_independent_wire_peer.py"))
                  for directory in ("protocol", "federation")),
                Command("python-correctness-lint", (py, "-m", "ruff", "check", "--no-cache", "--select", "E9,F63,F7,F82",
                                                    "nbsr", "services", "gateway", "scripts", "tests")),
                Command("ci-lint", (py, "-m", "ruff", "check", "--no-cache", "scripts/ci", "tests/ci")),
                Command("repository-privacy", (py, "scripts/verify_wp8_repository_safety.py", "privacy", ".")),
                Command("core-vectors", (py, "scripts/generate_core_v02_vectors.py", "--check", "vectors/core-v0.2")),
                Command("exporter-vectors", (py, "scripts/generate_wp4_exporter_vectors.py", "--check"))]
    if profile == "rust":
        return [Command("rust-format", ("cargo", "fmt", "--manifest-path", "crates/nbsr-transport/Cargo.toml", "--check")),
                Command("rust-default", ("cargo", "check", "--locked", "--offline", "--manifest-path",
                                         "crates/nbsr-transport/Cargo.toml", "--jobs", "2", "--lib")),
                Command("rust-library", cargo + ("--lib",)),
                Command("rust-transport", cargo + tuple(part for name in ("handshake", "stream_credit_integration", "drain", "config")
                                                        for part in ("--test", name))),
                Command("rust-codec", cargo + ("--test", "p2a_benchmark", "frame")),
                Command("rust-doc", cargo + ("--doc",)),
                Command("rust-clippy", ("cargo", "clippy", *cargo[2:], "--all-targets", "--", "-D", "warnings"))]
    if profile == "rust-extended":
        return [Command("rust-extended", cargo + ("--tests",))]
    if profile == "soak":
        return [Command("rust-soak", cargo + ("--lib", "channel_streams::tests::adversarial_soak_holds_replay_history_at_ten_thousand",
                                             "--", "--ignored", "--exact", "--test-threads=1"))]
    if profile == "go":
        return [Command(f"go-{index}-{kind}", ("go", kind, "-mod=readonly", "-p=2",
                                               *(("-timeout=90s", "-parallel=2", "./...") if kind == "test" else ("./...",))), module)
                for index, module in enumerate(GO_MODULES) for kind in ("test", "vet")]
    if profile == "node":
        return [Command("node-core-tests", ("node", "--test", "test/verifier.test.mjs"), "tools/core-v02-node-verifier"),
                Command("node-core-vectors", ("node", "verify.mjs", "../../vectors/core-v0.2"), "tools/core-v02-node-verifier"),
                Command("node-federation-tests", ("node", "--test", *(str(p.relative_to(ROOT / "verifiers/federation-node")) for p in sorted((ROOT / "verifiers/federation-node/test").glob("*.test.js")))), "verifiers/federation-node"),
                Command("node-federation-vectors", ("node", "src/verifier.js", "../../vectors/federation-v0.1"), "verifiers/federation-node"),
                Command("node-exporter", ("node", "scripts/verify_wp4_exporter_vectors.mjs", "vectors/core-v0.2/wp4-exporter"))]
    raise ValueError(f"unknown profile: {profile}")


def run_command(name: str, argv: list[str] | tuple[str, ...], cwd: Path, seconds: float) -> dict:
    """Timeout owns and reaps the process tree; artifact never includes command output."""
    options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
    process = subprocess.Popen(argv, cwd=cwd, stdout=sys.stdout, stderr=sys.stderr, **options)
    timed_out = False
    try:
        code = process.wait(timeout=seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        code = 124
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            else:
                os.killpg(process.pid, signal.SIGKILL)
        except (OSError, subprocess.SubprocessError):
            # Report incomplete tree cleanup even if the direct child can be reaped.
            code = 125
        finally:
            try:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=10)
            except (OSError, subprocess.SubprocessError):
                code = 125
    return {"check": name, "exit_code": code, "timed_out": timed_out}


def validate_workflow(workflow: dict) -> None:
    events = set(workflow.get("on", {}))
    if not events or not events <= {"push", "pull_request", "workflow_dispatch"}:
        raise ValueError("unsafe or absent event")
    if workflow.get("permissions") != {"contents": "read"}:
        raise ValueError("workflow must have read-only permissions")
    if not workflow.get("concurrency", {}).get("cancel-in-progress"):
        raise ValueError("missing superseded-run cancellation")
    for job in workflow.get("jobs", {}).values():
        if not 1 <= job.get("timeout-minutes", 0) <= 30:
            raise ValueError("missing bounded job timeout")
        if "permissions" in job or "environment" in job:
            raise ValueError("job must not elevate access")
        for step in job.get("steps", []):
            action = step.get("uses", "")
            if action and not re.fullmatch(r"actions/[\w/-]+@[0-9a-f]{40}", action):
                raise ValueError("action must be official and SHA-pinned")
            if action.startswith("actions/checkout@") and step.get("with", {}).get("persist-credentials") is not False:
                raise ValueError("checkout credentials must not persist")
            if action.startswith("actions/cache/save@") and "github.event_name == 'push'" not in step.get("if", ""):
                raise ValueError("untrusted cache write")
            if action.startswith("actions/upload-artifact@"):
                if step.get("with", {}).get("path") != "ci-results/*.json" or step["with"].get("include-hidden-files", False):
                    raise ValueError("artifact path must be sanitized outcome JSON only")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=("python-core", "python-protocol", "rust", "go", "node", "rust-extended", "soak", "validate"))
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.timeout <= 1200:
        parser.error("timeout must be between 1 and 1200 seconds")
    if args.timeout > 90 and os.environ.get("GITHUB_ACTIONS") != "true":
        parser.error("timeouts above 90 seconds are reserved for hosted CI")
    if args.profile == "validate":
        for path in sorted((ROOT / ".github/workflows").glob("*.yml")):
            validate_workflow(json.loads(path.read_text(encoding="utf-8")))
        print("CI workflow security contracts passed (remote schema/execution still required)")
        return 0
    commands = command_groups(args.profile)
    if args.list:
        for cmd in commands:
            print(cmd.name, cmd.cwd, *cmd.argv)
        return 0
    os.environ.update(CARGO_BUILD_JOBS="2", RUST_TEST_THREADS="2", GOFLAGS="-mod=readonly -p=2", GOMAXPROCS="2", GOTOOLCHAIN="local")
    results = []
    destination = ROOT / "ci-results"
    destination.mkdir(exist_ok=True)
    for cmd in commands:
        print(f"Running {cmd.name}", flush=True)
        try:
            result = run_command(cmd.name, cmd.argv, ROOT / cmd.cwd, args.timeout)
        except (OSError, subprocess.SubprocessError):
            result = {"check": cmd.name, "exit_code": 125, "timed_out": False}
        results.append(result)
        (destination / f"{args.profile}.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
        if result["exit_code"]:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
