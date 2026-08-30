from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
GO_ROOT = ROOT / "client" / "nbsr-go-client"
DEMO_ROOT = GO_ROOT / "demo"
MANIFEST_ARG = "crates/nbsr-transport/Cargo.toml"


@dataclass(frozen=True)
class Scenario:
    id: str
    attack: str
    expected: str
    observed_on_pass: str
    reason_code: str
    cleanup_on_pass: str
    command: tuple[str, ...]
    cwd: str = "root"
    pass_classification: str = "PASS"


def cargo_test(target: str, test: str) -> tuple[str, ...]:
    return (
        "cargo",
        "test",
        "--locked",
        "--release",
        "--manifest-path",
        MANIFEST_ARG,
        "--test",
        target,
        test,
        "--",
        "--exact",
    )


SCENARIOS = (
    Scenario(
        "replayed_grant_ticket",
        "Replay an already admitted route request/grant nonce.",
        "Reject as replay and retain zero active channel state.",
        "The first request was admitted; the replay returned AdmissionReject::Replay and active_channels returned to zero.",
        "AdmissionReject::Replay",
        "CLEAN",
        cargo_test("admission", "invalid_or_replayed_requests_leave_no_channel_state"),
    ),
    Scenario(
        "tampered_grant_ticket",
        "Flip one byte in a signed RouteGrant artifact.",
        "Reject signature validation before route admission.",
        "Tampered COSE_Sign1 RouteGrant validation returned CoreV02Reject::GrantInvalid.",
        "CoreV02Reject::GrantInvalid",
        "CLEAN",
        cargo_test("core_v02_vectors", "route_grant_sign1_is_validated_only_in_the_supplied_trust_context"),
    ),
    Scenario(
        "wrong_service_name",
        "Substitute the authorized service identity/name.",
        "Reject the binding and retain no cached or pending authority.",
        "Service-identity substitution returned authority.ErrBindingMismatch and Usage retained zero cache/pending entries.",
        "authority.ErrBindingMismatch",
        "CLEAN",
        ("go", "test", "./internal/client", "-run", "^TestAcquireRouteFailsClosedForAuthorityMutations$/^service_identity$", "-count=1"),
        "demo",
    ),
    Scenario(
        "wrong_port_transport",
        "Present RouteGrant vectors bound to the wrong port or transport.",
        "Reject each vector with the declared fail-closed protocol error.",
        "The closed Core v0.1 vector suite rejected wrong-port and wrong-transport RouteGrants with their declared errors.",
        "NBSR_E_GRANT_INVALID/NBSR_E_ROUTE_DENIED",
        "CLEAN",
        ("python", "-m", "pytest", "tests/protocol/test_vectors.py::test_every_vector_produces_its_declared_result", "-q"),
    ),
    Scenario(
        "wrong_pop_key",
        "Substitute the transport-session proof-of-possession key reference.",
        "Reject before dialing any transport.",
        "Proof-key substitution returned session.ErrProofBinding before wire dial.",
        "session.ErrProofBinding",
        "CLEAN",
        ("go", "test", "./internal/client", "-run", "^TestWireConnectorRejectsProofBWithoutDialing$", "-count=1"),
        "demo",
    ),
    Scenario(
        "expired_grant",
        "Present an expired RouteGrant.",
        "Reject as expired and retain no cached or pending authority.",
        "Expired authority returned authority.ErrExpired and retained zero cache/pending entries.",
        "authority.ErrExpired",
        "CLEAN",
        ("go", "test", "./internal/client", "-run", "^TestAcquireRouteFailsClosedForAuthorityMutations$/^expired$", "-count=1"),
        "demo",
    ),
    Scenario(
        "revoked_credential_grant",
        "Consume a grant after its digest appears in the verified revocation checkpoint.",
        "Reject as revoked without authorizing new work.",
        "Final authority validation returned authority.ErrRevoked for the checkpoint-revoked grant.",
        "authority.ErrRevoked",
        "CLEAN",
        (
            "go",
            "test",
            "./internal/authority",
            "-run",
            "^TestFinalCheckRejectsExpiryRevocationAndGeneration$/^checkpoint_revocation$",
            "-count=1",
        ),
        "go",
    ),
    Scenario(
        "stale_generation_sequence",
        "Present authority from a stale generation.",
        "Reject before transport/application creation and retain no authority state.",
        "Stale generation returned authority.ErrStaleGeneration with no transport, stream, payload, cache, or pending entry.",
        "authority.ErrStaleGeneration",
        "CLEAN",
        ("go", "test", "./internal/client", "-run", "^TestTask6AuthorityDeniedBeforeTransportOrApplication$", "-count=1"),
        "demo",
    ),
    Scenario(
        "downgrade_attempt",
        "Send a legacy v1 STREAM_OPEN on a negotiated credited-stream session.",
        "Reject the legacy path without consuming credit/replay/live capacity; allow only a valid credited retry.",
        "The negotiated v1 credited mode rejected legacy STREAM_OPEN without state mutation and accepted only the credited retry.",
        "ApplicationStreamRejected::ProfileUnsupported",
        "CLEAN",
        cargo_test("stream_credit_integration", "live_v1_rejects_legacy_stream_open_then_credited_retry_succeeds"),
    ),
    Scenario(
        "unauthorized_source",
        "Authenticate with a client certificate issued by an unknown CA.",
        "Reject the handshake before allocating an authenticated connection.",
        "The destination rejected the unknown-CA client certificate; no authenticated source connection was exposed.",
        "TLS_UNTRUSTED_CLIENT_CERTIFICATE",
        "CLEAN",
        cargo_test("handshake", "client_certificate_from_unknown_ca_is_rejected"),
    ),
    Scenario(
        "direct_origin_scan",
        "Attempt to bypass name routing and reach the private origin directly.",
        "The private origin must be unreachable from the client network.",
        "Adjacent current-SHA tests prove unknown routes and backend/transport failures have no fallback, but no network-isolated current-SHA origin scan was executed.",
        "NOT_CURRENT_SHA_NETWORK_ISOLATION",
        "NOT_APPLICABLE",
        (
            "go",
            "test",
            "./internal/client",
            "-run",
            "Test(Task6UnknownServiceDeniedBeforeSecureRoute|StandaloneBackendFailureHasNoFallback|StandaloneTransportFailureHasNoFallback)$",
            "-count=1",
        ),
        "demo",
        "INCONCLUSIVE",
    ),
    Scenario(
        "malformed_control_wire",
        "Send malformed early stream-credit/control bytes.",
        "Reject before admission without consuming credit, replay history, live capacity, or audit state.",
        "Malformed early bytes were rejected before admission; the same credit remained usable and ownership returned cleanly.",
        "ApplicationStreamRejected::MalformedPreface",
        "CLEAN",
        cargo_test("stream_credit_integration", "malformed_early_bytes_reject_before_admission_and_do_not_consume_state"),
    ),
    Scenario(
        "forged_identity_source_binding",
        "Present a validly signed certificate whose source identity does not match policy.",
        "Reject the handshake before exposing an authenticated connection.",
        "The destination rejected the mismatched source identity before authenticated connection allocation.",
        "TLS_SOURCE_IDENTITY_MISMATCH",
        "CLEAN",
        cargo_test("handshake", "source_identity_mismatch_is_rejected"),
    ),
    Scenario(
        "edge_session_failure_recovery",
        "Fail a replacement/current transport during rotation and recovery.",
        "Never restore a draining generation, never replay payload, bound retries, and clean pending ownership.",
        "Failure tests kept the old generation non-current, performed no payload replay, bounded recovery attempts, and returned pending ownership to zero.",
        "session.ErrTransport/session.ErrRecoveryExhausted",
        "CLEAN",
        (
            "go",
            "test",
            "./internal/session",
            "-run",
            "Test(FailedCurrentBDoesNotPromoteDrainingAOrCreateC|RotationDoesNotReplayApplicationPayload|RecoveryAttemptsAndCancellationAreBounded)$",
            "-count=1",
        ),
        "go",
    ),
)


RESULT_KEYS = {
    "scenario",
    "attack",
    "expected",
    "actual",
    "reason_code",
    "protected_service_reachable",
    "cleanup",
    "status",
    "command",
    "exit_code",
    "duration_seconds",
    "stdout_log",
    "stderr_log",
}
SOURCE_FILES = (
    "scripts/security/adversarial_campaign.py",
    "tests/security/test_adversarial_campaign.py",
)


def source_hashes() -> dict[str, str]:
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCE_FILES}


def validate_result(result: dict[str, Any]) -> None:
    if set(result) != RESULT_KEYS:
        raise ValueError("result schema is not closed")
    if result["status"] not in {"PASS", "FAIL", "INCONCLUSIVE"}:
        raise ValueError("invalid status")
    if result["status"] == "PASS":
        if result["exit_code"] != 0:
            raise ValueError("PASS requires a successful command")
        if result["protected_service_reachable"] is not False:
            raise ValueError("protected service became reachable")
        if result["cleanup"] != "CLEAN":
            raise ValueError("PASS requires clean cleanup")


def analyze_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    for result in results:
        validate_result(result)
    counts = {status: sum(result["status"] == status for result in results) for status in ("PASS", "FAIL", "INCONCLUSIVE")}
    overall = "FAIL" if counts["FAIL"] else "PARTIAL" if counts["INCONCLUSIVE"] else "PASS"
    return {"schema": "nbsr-security-adversarial-analysis-v1", "overall": overall, "counts": counts, "scenarios": results}


def scenario_cwd(scenario: Scenario) -> Path:
    return {"root": ROOT, "go": GO_ROOT, "demo": DEMO_ROOT}[scenario.cwd]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def run_scenario(scenario: Scenario, raw: Path, env: dict[str, str]) -> dict[str, Any]:
    started = time.monotonic()
    completed = subprocess.run(scenario.command, cwd=scenario_cwd(scenario), env=env, text=True, capture_output=True)
    duration = time.monotonic() - started
    stdout = raw / f"{scenario.id}.stdout.log"
    stderr = raw / f"{scenario.id}.stderr.log"
    stdout.write_text(completed.stdout, encoding="utf-8", newline="\n")
    stderr.write_text(completed.stderr, encoding="utf-8", newline="\n")
    if completed.returncode:
        status = "FAIL"
        actual = "The required fail-closed regression command failed; security behavior is not accepted."
        reachable: bool | None = None
        cleanup = "UNKNOWN"
    else:
        status = scenario.pass_classification
        actual = scenario.observed_on_pass
        reachable = False if status == "PASS" else None
        cleanup = scenario.cleanup_on_pass
    result = {
        "scenario": scenario.id,
        "attack": scenario.attack,
        "expected": scenario.expected,
        "actual": actual,
        "reason_code": scenario.reason_code,
        "protected_service_reachable": reachable,
        "cleanup": cleanup,
        "status": status,
        "command": list(scenario.command),
        "exit_code": completed.returncode,
        "duration_seconds": duration,
        "stdout_log": stdout.relative_to(raw.parent).as_posix(),
        "stderr_log": stderr.relative_to(raw.parent).as_posix(),
    }
    validate_result(result)
    return result


def checksums(root: Path) -> None:
    paths = sorted(path for path in root.rglob("*") if path.is_file() and path.name != "checksums.sha256")
    (root / "checksums.sha256").write_text(
        "".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root).as_posix()}\n" for path in paths),
        encoding="utf-8",
        newline="\n",
    )


def render_summary(analysis: dict[str, Any], metadata: dict[str, Any]) -> str:
    lines = [
        "# NBSR Security Adversarial Campaign",
        "",
        f"Overall: **{analysis['overall']}**",
        "",
        "| Scenario | Expected | Observed reason/code | Service reachable | Cleanup | Status |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for result in analysis["scenarios"]:
        reachable = "UNKNOWN" if result["protected_service_reachable"] is None else "YES" if result["protected_service_reachable"] else "NO"
        lines.append(
            f"| {result['scenario']} | {result['expected']} | {result['reason_code']} | {reachable} | {result['cleanup']} | {result['status']} |"
        )
    lines.extend(
        [
            "",
            "All PASS rows are current-SHA executable regressions whose underlying assertions verify the stated rejection and cleanup/state boundary.",
            "",
            "The direct-origin scan is INCONCLUSIVE because this campaign did not create a current-SHA network-isolated private-origin topology. Adjacent no-route/no-fallback regressions passed, but they are not equivalent to a network reachability scan.",
            "",
            "Reproduce: `python scripts/security/adversarial_campaign.py --output <new-empty-output-directory>`. Exact per-scenario commands and working-directory labels are stored in `environment.json`; raw stdout/stderr are stored under `raw/`.",
            "",
            f"Git SHA: `{metadata['git_sha']}`",
            f"Branch: `{metadata['branch']}`",
            f"Platform: {metadata['platform']}",
            "",
        ]
    )
    return "\n".join(lines)


def version(command: list[str]) -> str:
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=True)
    return (result.stdout or result.stderr).strip().splitlines()[0]


def windows_host() -> dict[str, Any]:
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        "$cpu=Get-CimInstance Win32_Processor|Select-Object -First 1; "
        "$cs=Get-CimInstance Win32_ComputerSystem; "
        "[ordered]@{cpu=$cpu.Name;physical_cores=$cpu.NumberOfCores;"
        "logical_processors=$cpu.NumberOfLogicalProcessors;memory_bytes=[uint64]$cs.TotalPhysicalMemory}"
        "|ConvertTo-Json -Compress",
    ]
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=True)
    return json.loads(completed.stdout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    raw = output / "raw"
    raw.mkdir()
    git_sha = version(["git", "rev-parse", "HEAD"])
    branch = version(["git", "branch", "--show-current"])
    host = windows_host()
    metadata = {
        "schema": "nbsr-security-adversarial-environment-v1",
        "git_sha": git_sha,
        "branch": branch,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "platform": f"{platform.system()}-{platform.release()}-{platform.version()}",
        "cpu": host["cpu"],
        "physical_cores": host["physical_cores"],
        "logical_processors": host["logical_processors"],
        "memory_bytes": host["memory_bytes"],
        "python": sys.version.split()[0],
        "go": version(["go", "version"]),
        "rustc": version(["rustc", "--version"]),
        "cargo": version(["cargo", "--version"]),
        "source_sha256": source_hashes(),
        "scenario_manifest": [asdict(scenario) for scenario in SCENARIOS],
        "command": list(sys.argv),
    }
    write_json(output / "environment.json", metadata)
    env = {**os.environ, "CARGO_TARGET_DIR": os.environ.get("CARGO_TARGET_DIR", r"C:\NBSR-build\security-campaign\cargo-target")}
    results = []
    for scenario in SCENARIOS:
        print(f"running {scenario.id}", flush=True)
        result = run_scenario(scenario, raw, env)
        results.append(result)
        write_json(raw / f"{scenario.id}.json", result)
    analysis = analyze_results(results)
    write_json(output / "analysis.json", analysis)
    (output / "summary.md").write_text(render_summary(analysis, metadata), encoding="utf-8", newline="\n")
    checksums(output)
    print(json.dumps({"overall": analysis["overall"], "counts": analysis["counts"]}))
    return 1 if analysis["overall"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
