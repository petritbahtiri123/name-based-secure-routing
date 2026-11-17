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
import tempfile

ROOT = Path(__file__).resolve().parents[2]
GO_MODULES = (
    "client/nbsr-go-client", "client/nbsr-go-client/demo", "interop/nbsr-go-peer",
    "verifiers/federation-go", "deploy/isp-federation-poc/adapter", "tools/demo-lab/fixturegen",
)
CORE_TESTS = (
    "test_control_plane", "test_dependency_security", "test_destination_policy", "test_dns_stub", "test_name_node",
    "test_name_node_dns", "test_name_node_observability",
    "test_deployment_tls", "test_kind_security",
    "test_legacy_origin",
    "test_name_service",
    "test_demo",
    "test_wp4_exporter_vectors",
    "test_release_packaging",
    "test_name_registry", "test_name_relay", "test_name_security", "test_originset",
    "test_resolution_state", "test_route_registry", "test_secure_files", "test_security",
    "test_service_tls", "test_services", "test_synthetic", "test_verifier",
    "test_gateway_plan", "test_gateway_profile", "test_gateway_verify", "test_gateway_journal", "test_gateway_cli",
    "test_wp6_continuity_state", "test_wp6_failover", "test_wp6_replication",
    "test_wp7_admission", "test_wp7_limits", "test_wp7_operator_model", "test_wp7_review_fixes",
    "test_connector_control_model", "test_connector_federation_model",
    "test_connector_registration_authority_offline", "test_connector_authority_timer_offline",
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
                                       *(f"tests/{name}.py" for name in CORE_TESTS),
                                       "deploy/single-instance/test_validate_config.py",
                                       "tests/security/test_adversarial_campaign.py",
                                       "tests/test_wp6_continuity_snapshot.py::test_snapshot_encoding_is_canonical_stable_and_round_trips",
                                       "tests/test_wp6_continuity_snapshot.py::test_decoder_rejects_unknown_missing_corrupt_unsorted_or_duplicate_state",
                                       "tests/test_wp6_continuity_snapshot.py::test_decoder_rejects_noncanonical_partial_and_oversized_input",
                                       "tests/test_wp7_conformance.py::test_audit_logs_are_operator_owned_bounded_and_monotonic",
                                       "tests/test_wp7_conformance.py::test_audit_sequence_exhaustion_fails_closed_before_recording",
                                       "tests/test_wp7_conformance.py::test_safe_operator_report_and_errors_exclude_private_destination",
                                       "tests/test_wp7_conformance.py::test_connector_receipt_cannot_be_used_as_a_private_destination_guessing_or_linkage_oracle",
                                       "tests/test_wp7_conformance.py::test_audit_overload_has_no_fallback_log_or_unbounded_growth",
                                       "tests/test_wp7_conformance.py::test_audit_capacity_is_preflighted_before_admission_success_or_peer_audit_mutation",
                                       "tests/test_wp7_conformance.py::test_public_admission_cannot_bypass_full_or_missing_operator_audits",
                                       "tests/test_wp7_conformance.py::test_closed_topology_rejects_direct_operator_edge_and_oversized_collections",
                                       "tests/test_wp7_conformance.py::test_raw_scan_is_deterministic_reaches_service_only_through_connector_and_discovers_no_private_destination",
                                       "tests/test_wp7_conformance.py::test_verifier_rejects_duplicate_json_members_at_every_object",
                                       "tests/test_documentation.py::test_core_v01_wire_contract_is_complete_and_non_claiming",
                                       "tests/test_documentation.py::test_core_v01_wire_contract_contains_every_frozen_numeric_mapping",
                                       "tests/test_documentation.py::test_protocol_package_exports_only_stable_wp1_surface",
                                       "tests/performance/test_b3_cleanup_gate.py",
                                       "tests/performance/test_b3_accept_window.py",
                                       "tests/performance/test_post_close_cleanup.py",
                                       "tests/performance/test_session_lifecycle_closure.py",
                                       "tests/performance/test_b3_failure_markers.py",
                                       "tests/performance/test_physical_core_classification.py",
                                       "tests/performance/test_wpr_trace_quality.py",
                                       "tests/performance/test_failure_evidence.py",
                                       "tests/performance/test_evidence_verifier.py",
                                       "tests/performance/test_grouped_progress.py",
                                       "tests/performance/test_statistics.py",
                                       "tests/performance/test_cpu_efficiency.py",
                                       "tests/performance/test_linux_native_packet_accounting.py",
                                       "tests/performance/test_native_packet_markers.py",
                                       "tests/performance/test_native_packet_phases.py",
                                       "tests/performance/test_mixed_workload.py",
                                       "tests/performance/test_sustained_capacity.py",
                                       "tests/performance/test_benchmark_model.py",
                                       "tests/performance/test_bounded_replay_model.py",
                                       "tests/performance/test_session_rotation_model.py",
                                       "tests/performance/test_evidence_writer.py",
                                       "tests/performance/test_completion_evidence.py",
                                       "tests/performance/test_b3_linux_analysis.py",
                                       "tests/performance/test_b3_v2_analysis.py",
                                       "tests/test_transport_fixture_inventory.py",
                                       "tests/test_wp3_rust_transport_isolation.py::test_no_certificate_or_private_key_fixture_is_committed",
                                       "tests/test_wp6_continuity_snapshot.py::test_replica_config_requires_sorted_unique_bounded_majority")),
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
                Command("federation-v2-vectors", (py, "scripts/generate_federation_v01_vectors.py", "--version", "federation-v0.1-development-v2", "--check", "vectors/federation-v0.1-development-v2")),
                Command("connector-signature-fixtures", (py, "-m", "scripts.extract_connector_signature_fixtures", "--check")),
                Command("connector-kar-positive", (py, "-m", "scripts.check_connector_kar_positive", "--check")),
                Command("normal-revocation-conformance", (py, "-m", "scripts.normal_revocation_conformance", "--check")),
                Command("revocation-inclusion-v2", (py, "-m", "scripts.revocation_inclusion_v2", "--check")),
                Command("connected-authority-vectors", (py, "-m", "scripts.check_connected_authority_vectors", "--check")),
                Command("inclusion-persistence-local", (py, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                                                        "tests/federation/test_inclusion_persistence.py")),
                Command("exporter-vectors", (py, "scripts/generate_wp4_exporter_vectors.py", "--check"))]
    if profile == "rust":
        return [Command("rust-format", ("cargo", "fmt", "--manifest-path", "crates/nbsr-transport/Cargo.toml", "--check")),
                Command("rust-default", ("cargo", "check", "--locked", "--offline", "--manifest-path",
                                         "crates/nbsr-transport/Cargo.toml", "--jobs", "2", "--lib")),
                Command("rust-library", cargo + ("--lib",)),
                Command("rust-transport", cargo + tuple(part for name in ("handshake", "stream_credit_integration", "drain", "config")
                                                        for part in ("--test", name))),
                Command("rust-codec", cargo + ("--test", "p2a_benchmark", "frame")),
                Command("rust-connector", cargo + ("--test", "connector_control", "--test", "connector_registration",
                                                   "--test", "connector_loopback", "--test", "connector_signature",
                                                   "--test", "connector_authority", "--test", "connector_kar",
                                                   "--test", "connector_genesis")),
                Command("rust-dispatch-boundary", cargo + ("--bin", "wp8_interop_server", "connector_refusal_tests::connector_unavailable_refuses_actual_dispatch_before_supervisor", "--", "--exact", "--test-threads=1")),
                Command("rust-direct-boundary", cargo + ("--bin", "wp8_interop_server", "connector_refusal_tests::direct_demo_keeps_request_validation_before_supervisor", "--", "--exact", "--test-threads=1")),
                Command("rust-wrapper-refusal", cargo + ("--test", "demo_backend", "connector_mode_refuses_through_private_route_wrapper_before_supervisor", "--", "--exact", "--test-threads=1")),
                Command("rust-wrapper-direct", cargo + ("--test", "demo_backend", "main_connector_function_relays_positive_federated_credit", "--", "--exact", "--test-threads=1")),
                Command("rust-private-carrier", cargo + ("--test", "private_carrier_refusal", "--", "--test-threads=1")),
                Command("rust-doc", cargo + ("--doc",)),
                Command("rust-clippy", ("cargo", "clippy", *cargo[2:], "--all-targets", "--", "-D", "warnings"))]
    if profile == "rust-extended":
        return [Command("rust-extended", cargo + ("--tests",))]
    if profile == "connector-loopback":
        return [Command("connector-loopback-build", cargo + ("--test", "connector_loopback", "--no-run")),
                Command("connector-worker-build", ("go", "test", "-mod=readonly", "-p=2", "-tags", "connector_development",
                                                    "-c", "-o", os.environ.get("NBSR_CONNECTOR_GO_TEST", "<task-owned-worker>"),
                                                    "./connector"), "interop/nbsr-go-peer"),
                Command("connector-loopback", cargo + ("--test", "connector_loopback", "isolated_go_rust_control_registration",
                                                       "--", "--ignored", "--exact", "--nocapture"))]
    if profile == "soak":
        return [Command("rust-soak", cargo + ("--lib", "channel_streams::tests::adversarial_soak_holds_replay_history_at_ten_thousand",
                                             "--", "--ignored", "--exact", "--test-threads=1"))]
    if profile == "go":
        return [Command(f"go-{index}-{kind}", ("go", kind, "-mod=readonly", "-p=2",
                                               *(("-timeout=90s", "-parallel=2", "./...") if kind == "test" else ("./...",))), module)
                for index, module in enumerate(GO_MODULES) for kind in ("test", "vet")] + [
                    Command(f"go-connector-{kind}", ("go", kind, "-mod=readonly", "-p=2", "-tags", "connector_development",
                                                    *(("-timeout=90s", "-parallel=2", "-count=1") if kind == "test" else ()),
                                                    "./connector"), "interop/nbsr-go-peer") for kind in ("test", "vet")] + [
                    Command("go-federation-v2", ("go", "run", "-mod=readonly", "-p=2", "./cmd/verify", "--version", "federation-v0.1-development-v2", "../../vectors/federation-v0.1-development-v2"), "verifiers/federation-go")]
    if profile == "node":
        return [Command("node-connector-vectors", ("node", "scripts/verify_connector_registration_vectors.mjs")),
                Command("node-core-tests", ("node", "--test", "test/verifier.test.mjs"), "tools/core-v02-node-verifier"),
                Command("node-core-vectors", ("node", "verify.mjs", "../../vectors/core-v0.2"), "tools/core-v02-node-verifier"),
                Command("node-federation-tests", ("node", "--test", *(str(p.relative_to(ROOT / "verifiers/federation-node")) for p in sorted((ROOT / "verifiers/federation-node/test").glob("*.test.js")))), "verifiers/federation-node"),
                Command("node-federation-vectors", ("node", "src/verifier.js", "../../vectors/federation-v0.1"), "verifiers/federation-node"),
                Command("node-federation-v2", ("node", "src/verifier.js", "--version", "federation-v0.1-development-v2", "../../vectors/federation-v0.1-development-v2"), "verifiers/federation-node"),
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
        # GitHub resolves job env before a runner exists; step env/run may use it.
        if any(re.search(r"\$\{\{[^}]*\brunner\s*[.\[]", str(value))
               for value in job.get("env", {}).values()):
            raise ValueError("runner context is unavailable in job environment")
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
    parser.add_argument("profile", choices=("python-core", "python-protocol", "rust", "go", "node", "rust-extended",
                                           "connector-loopback", "soak", "validate"))
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
    if args.profile == "connector-loopback":
        previous = os.environ.get("NBSR_CONNECTOR_GO_TEST")
        with tempfile.TemporaryDirectory(prefix="nbsr-connector-ci-") as directory:
            try:
                os.environ["NBSR_CONNECTOR_GO_TEST"] = str(Path(directory) / ("worker.exe" if os.name == "nt" else "worker"))
                return execute_profile(args.profile, args.timeout)
            finally:
                if previous is None:
                    os.environ.pop("NBSR_CONNECTOR_GO_TEST", None)
                else:
                    os.environ["NBSR_CONNECTOR_GO_TEST"] = previous
    return execute_profile(args.profile, args.timeout)


def execute_profile(profile: str, seconds: int) -> int:
    commands = command_groups(profile)
    results = []
    destination = ROOT / "ci-results"
    destination.mkdir(exist_ok=True)
    for cmd in commands:
        print(f"Running {cmd.name}", flush=True)
        try:
            result = run_command(cmd.name, cmd.argv, ROOT / cmd.cwd, seconds)
        except (OSError, subprocess.SubprocessError):
            result = {"check": cmd.name, "exit_code": 125, "timed_out": False}
        results.append(result)
        (destination / f"{profile}.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
        if result["exit_code"]:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
