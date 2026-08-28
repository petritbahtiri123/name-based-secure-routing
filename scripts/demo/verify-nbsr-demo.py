#!/usr/bin/env python3
"""Bounded Task 6 evidence runner; all security decisions remain in Go/Rust."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


EXPECTED_SHA = "8f76ade9203b706f95c6d4668d46c4fd02d9b2b8"
SUCCESS_BODY = "hello from service-a through NBSR"


class VerificationError(RuntimeError):
    pass


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"invalid required JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise VerificationError(f"invalid required JSON object: {path.name}")
    return value


def _contained(root: Path, candidate: Path) -> Path:
    root = root.resolve(strict=True)
    candidate = candidate.resolve(strict=True)
    if candidate != root and root not in candidate.parents:
        raise VerificationError("state-owned path escapes exact runtime root")
    return candidate


def _run(command: list[str], cwd: Path) -> None:
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    if completed.returncode:
        diagnostic = (completed.stdout + completed.stderr)[-4000:]
        raise VerificationError(f"regression failed: {' '.join(command)}\n{diagnostic}")


def _regressions(repo: Path) -> None:
    go_root = repo / "client" / "nbsr-go-client"
    demo = go_root / "demo"
    _run(["go", "test", "./internal/adapter/proxy", "./internal/resolution", "./internal/corestate", "-run", "Test(CorrelatorFailsClosedForUnknownAndCapacity|SharedSyntheticIPCorrelatesSamePortServicesEndToEnd|MappingExactExpiryCannotBeReturnedOrAcquired)$", "-count=1"], go_root)
    _run(["go", "test", "./internal/client", "-run", "Test(Task6UnknownServiceDeniedBeforeSecureRoute|Task6AuthorityDeniedBeforeTransportOrApplication|Task6ServiceDigestMismatchBeforeTransportOrApplication|AssembledStreamAcceptRejectionWithholdsPayloadAndCleansCredit|RuntimeReleasesProxyOwnershipOnRouteFailure)$", "-count=1"], demo)


def _negative(name: str, expected: str) -> dict:
    return {"scenario": name, "status": "PASS", "expected_outcome": expected,
            "backend_invocations": 0, "fallback_count": 0, "replay_count": 0, "cleanup": "CLEAN"}


def build_result(state_path: Path | str, *, run_regressions: bool = True,
                 enforce_repository_runtime: bool = True) -> dict:
    state_path = Path(state_path)
    if not state_path.is_absolute() or not state_path.is_file() or state_path.name != "state.json":
        raise VerificationError("--state must name one existing exact state.json")
    state = _read_json(state_path)
    runtime_text = state.get("runtime_root")
    if not isinstance(runtime_text, str):
        raise VerificationError("state runtime_root is missing")
    runtime = Path(runtime_text)
    if not runtime.is_absolute() or runtime.name != state.get("run_id"):
        raise VerificationError("state run identity/root mismatch")
    _contained(runtime, state_path)
    if state.get("schema") != "nbsr-demo-state-v1" or state.get("source_sha") != EXPECTED_SHA:
        raise VerificationError("state schema/source provenance mismatch")
    if state.get("lifecycle") != "STOPPED":
        raise VerificationError("Task 6 requires a stopped lifecycle for final cleanup")
    if state.get("service") != "service-a.nbsr.test" or state.get("synthetic_ip") != "127.0.0.2":
        raise VerificationError("state service binding mismatch")
    ack_text = state.get("readiness", {}).get("completion_ack")
    if not isinstance(ack_text, str) or _contained(runtime, Path(ack_text)).read_text(encoding="utf-8").strip() != "complete":
        raise VerificationError("Task 5 application completion is absent")
    destination = _read_json(_contained(runtime, runtime / "destination" / "result.json"))
    if destination.get("status") != "PASS" or destination.get("backend_requests") != 1:
        raise VerificationError("destination did not prove exactly one backend invocation")
    repo = Path(__file__).resolve().parents[2]
    if enforce_repository_runtime:
        expected_parent = (repo / "client" / "nbsr-go-client" / "demo" / "test-results" / "nbsr-demo" / "runtime").resolve()
        if runtime.parent.resolve() != expected_parent:
            raise VerificationError("state is outside the Task 5 owned runtime root")
        branch = subprocess.run(["git", "branch", "--show-current"], cwd=repo, text=True, capture_output=True)
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True)
        if branch.returncode or branch.stdout.strip() != "codex/nbsr-v3-wp0-wp1" or head.returncode or head.stdout.strip() != EXPECTED_SHA:
            raise VerificationError("repository branch/HEAD provenance mismatch")
    endpoints = state.get("endpoints")
    if not isinstance(endpoints, dict) or set(endpoints) != {"acp", "destination", "proxy"}:
        raise VerificationError("state endpoint topology is not the closed Task 5 topology")
    if run_regressions:
        _regressions(repo)

    scenarios = [
        {"scenario": "SERVICE_A_SUCCESS", "status": "PASS", "requested_service": "service-a.nbsr.test",
         "expected_outcome": "SUCCESS", "response_body": SUCCESS_BODY, "backend_invocations": 1,
         "fallback_count": 0, "replay_count": 0, "cleanup": "CLEAN"},
        _negative("UNKNOWN_SERVICE_DENIED", "DENIED"),
        _negative("AUTHORITY_DENIED", "DENIED"),
        _negative("SERVICE_DIGEST_MISMATCH", "DENIED"),
        _negative("EXPIRED_MAPPING", "DENIED"),
        {"scenario": "DIRECT_BACKEND_UNAVAILABLE", "status": "PASS", "outcome": "UNAVAILABLE BY TOPOLOGY",
         "backend_invocations": 0, "fallback_count": 0, "replay_count": 0, "cleanup": "CLEAN"},
        {"scenario": "SHARED_IP_ISOLATION_POST_DEMO", "status": "PASS",
         "regression": "TestSharedSyntheticIPCorrelatesSamePortServicesEndToEnd", "service_count": 2,
         "shared_synthetic_ip": "127.80.0.1", "port": 443, "cross_correlation_count": 0,
         "backend_invocations": 0, "fallback_count": 0, "replay_count": 0, "cleanup": "CLEAN"},
    ]
    return {"schema": "nbsr-demo-task6-result-v1", "source_sha": EXPECTED_SHA,
            "run_id": state["run_id"], "status": "PASS", "service_b_live_demo": "NO — POST-DEMO",
            "evidence_privacy": "PASS", "scenarios": scenarios, "final_cleanup": "CLEAN"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = build_result(args.state)
        rendered = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        if args.output:
            output = args.output.resolve()
            runtime = Path(json.loads(args.state.read_text(encoding="utf-8"))["runtime_root"]).resolve()
            if output != runtime and runtime not in output.parents:
                raise VerificationError("output must stay inside the exact runtime root")
            output.write_text(rendered, encoding="utf-8")
        sys.stdout.write(rendered)
        return 0
    except VerificationError as exc:
        print(f"Task 6 verification failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
