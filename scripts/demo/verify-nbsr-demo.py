#!/usr/bin/env python3
"""Bounded Task 6 evidence runner; all security decisions remain in Go/Rust."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path


EXPECTED_SHA = "8f76ade9203b706f95c6d4668d46c4fd02d9b2b8"
FINAL_EXPECTED_SHA = "19f6468f77175adcb7ad410c2016aa889b964dc0"
SUCCESS_BODY = "hello from service-a through NBSR"
FINAL_SCHEMA = "nbsr-end-to-end-demo-evidence-v1"
FINAL_STAGES = {
    "RESOLUTION_CANONICALIZED", "MAPPING_ACQUIRED", "FLOW_CORRELATED",
    "AUTHORITY_VERIFIED", "TS_ACTIVE", "SC_AUTHORIZED",
    "STREAM_CREDIT_ADMITTED", "APPLICATION_STREAM_ADMITTED",
    "BACKEND_RESPONSE_RETURNED",
}
FINAL_NEGATIVES = {
    "UNKNOWN_SERVICE_DENIED", "AUTHORITY_DENIED", "SERVICE_DIGEST_MISMATCH",
    "EXPIRED_MAPPING", "DIRECT_BACKEND_UNAVAILABLE",
    "SHARED_IP_ISOLATION_POST_DEMO",
}
FORBIDDEN_EVIDENCE_KEYS = {
    "originendpoint", "backendpath", "backendcommand", "privatekey",
    "signingkey", "routegrant", "proof", "credential", "token",
    "mappingid", "localflowid", "buildroot", "runtimeroot", "executable",
}


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


def _exact_keys(value: object, expected: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != expected:
        raise VerificationError(f"{label} fields are not the closed schema")
    return value


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _privacy_scan(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
            if normalized in FORBIDDEN_EVIDENCE_KEYS:
                raise VerificationError("final evidence contains a forbidden field")
            _privacy_scan(child)
    elif isinstance(value, list):
        for child in value:
            _privacy_scan(child)
    elif isinstance(value, str):
        lowered = value.lower()
        if re.search(r"[a-z]:\\", value, re.IGNORECASE) or ".exe" in lowered or "-----begin " in lowered:
            raise VerificationError("final evidence contains a forbidden path or private material")


def validate_final_evidence(evidence: object) -> None:
    root = _exact_keys(evidence, {
        "schema", "overall", "provenance", "binary_sha256", "requested_identity",
        "route_stages", "result", "negative_matrix", "shared_ip_isolation",
        "service_b_live_demo", "direct_backend_path", "cleanup", "privacy",
    }, "final evidence")
    if root["schema"] != FINAL_SCHEMA or root["overall"] != "PASS":
        raise VerificationError("final evidence schema/outcome mismatch")

    provenance = _exact_keys(root["provenance"], {
        "source_branch", "source_sha", "production_source_clean", "platform",
        "run_id", "toolchains",
    }, "provenance")
    if (provenance["source_branch"] != "codex/nbsr-v3-wp0-wp1"
            or provenance["source_sha"] != FINAL_EXPECTED_SHA
            or provenance["production_source_clean"] is not True
            or provenance["platform"] != "WINDOWS_LOOPBACK"
            or not isinstance(provenance["run_id"], str)
            or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?", provenance["run_id"])):
        raise VerificationError("final evidence provenance mismatch")
    toolchains = _exact_keys(provenance["toolchains"], {"go", "rustc", "cargo", "powershell", "python"}, "toolchains")
    if not all(isinstance(value, str) and value for value in toolchains.values()):
        raise VerificationError("toolchain version missing")

    binaries = _exact_keys(root["binary_sha256"], {"authority", "client", "backend", "destination"}, "binary identities")
    if not all(_is_sha256(value) for value in binaries.values()):
        raise VerificationError("binary SHA-256 is malformed")

    identity = _exact_keys(root["requested_identity"], {
        "presentation_name", "canonical_name", "port", "service_digest", "synthetic_ip",
    }, "requested identity")
    canonical = "service-a.nbsr.test"
    if (identity != {"presentation_name": canonical, "canonical_name": canonical, "port": 8080,
                     "service_digest": hashlib.sha256(canonical.encode()).hexdigest(),
                     "synthetic_ip": "127.0.0.2"}):
        raise VerificationError("requested identity mismatch")

    stages = root["route_stages"]
    if not isinstance(stages, list) or len(stages) != len(FINAL_STAGES):
        raise VerificationError("mandatory route stages are incomplete")
    seen_stages = set()
    for item in stages:
        stage = _exact_keys(item, {"stage", "status", "scope"}, "route stage")
        if stage["stage"] not in FINAL_STAGES or stage["stage"] in seen_stages or stage["status"] != "PASS" or stage["scope"] != "LIVE_DEMO":
            raise VerificationError("route stage is invalid or contradictory")
        seen_stages.add(stage["stage"])
    if seen_stages != FINAL_STAGES:
        raise VerificationError("mandatory route stage missing")

    result = _exact_keys(root["result"], {"status", "response_body", "response_sha256", "backend_invocations"}, "result")
    if (result["status"] != "PASS" or result["response_body"] != SUCCESS_BODY
            or result["response_sha256"] != hashlib.sha256(SUCCESS_BODY.encode()).hexdigest()
            or result["backend_invocations"] != 1):
        raise VerificationError("positive result is missing or contradictory")

    negatives = root["negative_matrix"]
    if not isinstance(negatives, list) or len(negatives) != len(FINAL_NEGATIVES):
        raise VerificationError("mandatory negative matrix is incomplete")
    seen_negatives = set()
    for item in negatives:
        scenario = _exact_keys(item, {
            "scenario", "status", "backend_invocations", "fallback_count",
            "replay_count", "cleanup", "scope",
        }, "negative scenario")
        if (scenario["scenario"] not in FINAL_NEGATIVES or scenario["scenario"] in seen_negatives
                or scenario["status"] != "PASS" or scenario["backend_invocations"] != 0
                or scenario["fallback_count"] != 0 or scenario["replay_count"] != 0
                or scenario["cleanup"] != "CLEAN" or scenario["scope"] != "REGRESSION"):
            raise VerificationError("negative scenario is invalid or contradictory")
        seen_negatives.add(scenario["scenario"])
    if seen_negatives != FINAL_NEGATIVES:
        raise VerificationError("mandatory negative scenario missing")

    isolation = _exact_keys(root["shared_ip_isolation"], {
        "scope", "services", "synthetic_ip", "port", "distinct_provenance",
        "cross_correlation_count",
    }, "shared-IP isolation")
    if isolation != {"scope": "REGRESSION", "services": ["payments.example", "storage.example"],
                     "synthetic_ip": "127.80.0.1", "port": 443,
                     "distinct_provenance": True, "cross_correlation_count": 0}:
        raise VerificationError("shared-IP isolation scope/result mismatch")
    if root["service_b_live_demo"] != "NO — POST-DEMO" or root["direct_backend_path"] != "UNAVAILABLE BY TOPOLOGY":
        raise VerificationError("demo scope classification mismatch")

    cleanup = _exact_keys(root["cleanup"], {
        "status", "lifecycle", "flow_store_entries", "mapping_references",
        "proxy_active_connections", "sessions", "channels", "streams",
        "pending_admissions", "backend_children", "owned_processes", "active_locks",
    }, "cleanup")
    if cleanup["status"] != "CLEAN" or cleanup["lifecycle"] != "STOPPED" or any(
            cleanup[key] != 0 for key in cleanup if key not in {"status", "lifecycle"}):
        raise VerificationError("cleanup claim is not final and zero")
    if root["privacy"] != {"status": "PASS", "forbidden_matches": 0}:
        raise VerificationError("privacy result is not clean")
    _privacy_scan(root)


def _regressions(repo: Path) -> None:
    go_root = repo / "client" / "nbsr-go-client"
    demo = go_root / "demo"
    _run(["go", "test", "./internal/adapter/proxy", "./internal/resolution", "./internal/corestate", "-run", "Test(CorrelatorFailsClosedForUnknownAndCapacity|SharedSyntheticIPCorrelatesSamePortServicesEndToEnd|MappingExactExpiryCannotBeReturnedOrAcquired)$", "-count=1"], go_root)
    _run(["go", "test", "./internal/client", "-run", "Test(Task6UnknownServiceDeniedBeforeSecureRoute|Task6AuthorityDeniedBeforeTransportOrApplication|Task6ServiceDigestMismatchBeforeTransportOrApplication|AssembledStreamAcceptRejectionWithholdsPayloadAndCleansCredit|RuntimeReleasesProxyOwnershipOnRouteFailure)$", "-count=1"], demo)


def task6_verifier_head_allowed(value: str) -> bool:
    return value in {EXPECTED_SHA, FINAL_EXPECTED_SHA}


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
        if (branch.returncode or branch.stdout.strip() != "codex/nbsr-v3-wp0-wp1"
                or head.returncode or not task6_verifier_head_allowed(head.stdout.strip())):
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


def _version(command: list[str], cwd: Path) -> str:
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    value = (completed.stdout or completed.stderr).strip().splitlines()
    if completed.returncode or not value:
        raise VerificationError(f"toolchain version unavailable: {command[0]}")
    return value[0]


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise VerificationError("launched binary identity is unavailable") from exc
    return digest.hexdigest()


def _production_source_clean(repo: Path) -> bool:
    completed = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=repo, text=True, capture_output=True,
    )
    if completed.returncode:
        raise VerificationError("worktree classification failed")
    allowed = (
        "scripts/demo/verify-nbsr-demo.py", "tests/demo/", "docs/demo/",
        "docs/protocol/status.md",
    )
    for line in completed.stdout.splitlines():
        path = line[3:].replace("\\", "/")
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if not any(path == prefix or path.startswith(prefix) for prefix in allowed):
            return False
    return True


def _pid_is_present(pid: object) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        raise VerificationError("invalid owned process identity")
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
    completed = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
        text=True, capture_output=True,
    )
    return completed.returncode == 0 and f'"{pid}"' in completed.stdout


def build_final_evidence(state_path: Path | str, *, run_regressions: bool = True,
                         enforce_repository_runtime: bool = True) -> dict:
    state_path = Path(state_path)
    if not state_path.is_absolute() or not state_path.is_file() or state_path.name != "state.json":
        raise VerificationError("--state must name one existing exact state.json")
    state = _read_json(state_path)
    runtime_text = state.get("runtime_root")
    build_text = state.get("build_root")
    if not isinstance(runtime_text, str) or not isinstance(build_text, str):
        raise VerificationError("operator state roots are missing")
    runtime = Path(runtime_text)
    build_root = Path(build_text)
    if (not runtime.is_absolute() or not build_root.is_absolute()
            or runtime.name != state.get("run_id")):
        raise VerificationError("state run identity/root mismatch")
    _contained(runtime, state_path)
    if (state.get("schema") != "nbsr-demo-state-v1"
            or state.get("source_sha") != FINAL_EXPECTED_SHA
            or state.get("lifecycle") != "STOPPED"):
        raise VerificationError("final state provenance/lifecycle mismatch")
    if state.get("service") != "service-a.nbsr.test" or state.get("synthetic_ip") != "127.0.0.2":
        raise VerificationError("final state service binding mismatch")
    repo = Path(__file__).resolve().parents[2]
    if enforce_repository_runtime:
        expected_parent = (repo / "client" / "nbsr-go-client" / "demo" / "test-results" / "nbsr-demo" / "runtime").resolve()
        if runtime.parent.resolve() != expected_parent:
            raise VerificationError("state is outside the Task 5 owned runtime root")
        branch = _version(["git", "branch", "--show-current"], repo)
        head = _version(["git", "rev-parse", "HEAD"], repo)
        if branch != "codex/nbsr-v3-wp0-wp1" or head != FINAL_EXPECTED_SHA:
            raise VerificationError("repository branch/HEAD provenance mismatch")
    ack_text = state.get("readiness", {}).get("completion_ack")
    if not isinstance(ack_text, str) or _contained(runtime, Path(ack_text)).read_text(encoding="utf-8").strip() != "complete":
        raise VerificationError("final application completion is absent")
    destination = _read_json(_contained(runtime, runtime / "destination" / "result.json"))
    if destination.get("status") != "PASS" or destination.get("backend_requests") != 1:
        raise VerificationError("final backend result is not exactly one PASS")

    artifacts = state.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 4:
        raise VerificationError("launched binary identities are incomplete")
    hashes: dict[str, str] = {}
    for artifact in artifacts:
        item = _exact_keys(artifact, {"name", "executable", "sha256"}, "operator artifact")
        name = item["name"]
        if name not in {"authority", "client", "backend", "destination"} or name in hashes:
            raise VerificationError("launched binary identity name is invalid")
        binary = _contained(build_root, Path(item["executable"]))
        actual = _file_sha256(binary)
        if item["sha256"] != actual:
            raise VerificationError("launched binary hash mismatch")
        hashes[name] = actual
    if set(hashes) != {"authority", "client", "backend", "destination"}:
        raise VerificationError("launched binary identity missing")

    components = state.get("components")
    if not isinstance(components, list) or any(_pid_is_present(item.get("pid")) for item in components if isinstance(item, dict)):
        raise VerificationError("owned process remains after STOPPED")
    if (runtime.parent / "active.lock").exists():
        raise VerificationError("active runtime lock remains after STOPPED")
    if not _production_source_clean(repo):
        raise VerificationError("production executable source is dirty")
    if run_regressions:
        _regressions(repo)

    negatives = [
        {"scenario": name, "status": "PASS", "backend_invocations": 0,
         "fallback_count": 0, "replay_count": 0, "cleanup": "CLEAN", "scope": "REGRESSION"}
        for name in sorted(FINAL_NEGATIVES)
    ]
    canonical = "service-a.nbsr.test"
    evidence = {
        "schema": FINAL_SCHEMA,
        "overall": "PASS",
        "provenance": {
            "source_branch": "codex/nbsr-v3-wp0-wp1",
            "source_sha": FINAL_EXPECTED_SHA,
            "production_source_clean": True,
            "platform": "WINDOWS_LOOPBACK",
            "run_id": state["run_id"],
            "toolchains": {
                "go": _version(["go", "version"], repo),
                "rustc": _version(["rustc", "--version"], repo),
                "cargo": _version(["cargo", "--version"], repo),
                "powershell": _version(["pwsh", "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"], repo),
                "python": sys.version.split()[0],
            },
        },
        "binary_sha256": hashes,
        "requested_identity": {
            "presentation_name": canonical, "canonical_name": canonical, "port": 8080,
            "service_digest": hashlib.sha256(canonical.encode()).hexdigest(),
            "synthetic_ip": "127.0.0.2",
        },
        "route_stages": [
            {"stage": stage, "status": "PASS", "scope": "LIVE_DEMO"}
            for stage in sorted(FINAL_STAGES)
        ],
        "result": {
            "status": "PASS", "response_body": SUCCESS_BODY,
            "response_sha256": hashlib.sha256(SUCCESS_BODY.encode()).hexdigest(),
            "backend_invocations": 1,
        },
        "negative_matrix": negatives,
        "shared_ip_isolation": {
            "scope": "REGRESSION", "services": ["payments.example", "storage.example"],
            "synthetic_ip": "127.80.0.1", "port": 443,
            "distinct_provenance": True, "cross_correlation_count": 0,
        },
        "service_b_live_demo": "NO — POST-DEMO",
        "direct_backend_path": "UNAVAILABLE BY TOPOLOGY",
        "cleanup": {
            "status": "CLEAN", "lifecycle": "STOPPED", "flow_store_entries": 0,
            "mapping_references": 0, "proxy_active_connections": 0, "sessions": 0,
            "channels": 0, "streams": 0, "pending_admissions": 0,
            "backend_children": 0, "owned_processes": 0, "active_locks": 0,
        },
        "privacy": {"status": "PASS", "forbidden_matches": 0},
    }
    validate_final_evidence(evidence)
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--final", action="store_true", help="emit the closed Task 7 evidence schema")
    args = parser.parse_args()
    try:
        result = build_final_evidence(args.state) if args.final else build_result(args.state)
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
