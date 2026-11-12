"""Offline evidence consistency checks; receipts are not signed attestations."""
import hashlib
import json
import re
from pathlib import Path, PurePosixPath

EXPECTED_TESTS = {
    "unknown_service": "TestTask6UnknownServiceDeniedBeforeSecureRoute",
    "stale_authority": "TestTask6AuthorityDeniedBeforeTransportOrApplication",
    "digest_mismatch": "TestTask6ServiceDigestMismatchBeforeTransportOrApplication",
    "expired_mapping": "TestMappingExactExpiryCannotBeReturnedOrAcquired",
    "shared_ip_isolation": "TestSharedSyntheticIPCorrelatesSamePortServicesEndToEnd",
}
BODY = "hello from service-a through NBSR"
MAX_BYTES = 4 * 1024 * 1024
TOP = {"schema_version", "scenario", "evidence_kind", "provenance", "result", "cleanup", "artifacts"}
RESULT = {"exit_code", "reason", "cancelled", "timeout", "expected_tests", "regression_kind"}
PROVENANCE = {"source_hashes", "binary_hashes", "source_commit", "platform", "toolchain"}
EXECUTION = {"mode", "host_platform", "execution_platform", "image_id", "container_id"}
NATIVE_CONTAINERS = {"Darwin-arm64": "Linux-aarch64", "Darwin-x86_64": "Linux-x86_64"}
ATTEMPT = {"schema", "run_id", "source_commit", "expected_source_hashes", "host_platform",
           "image_id", "container_id", "exit_code", "reason", "cleanup"}


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _json(raw):
    def invalid(_):
        raise ValueError("nonfinite JSON number")
    return json.loads(raw, object_pairs_hook=_pairs, parse_constant=invalid)


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _safe_path(path):
    # Also reject Windows reparse points (junctions), including parent directories.
    for part in (path, *path.parents):
        if part.exists() or part.is_symlink():
            info = part.lstat()
            _require(not part.is_symlink() and not (getattr(info, "st_file_attributes", 0) & 0x400),
                     "symlink or reparse point in evidence path")


def _read(path):
    _safe_path(path)
    _require(path.is_file(), "missing evidence file")
    _require(path.stat().st_size <= MAX_BYTES, "evidence exceeds size limit")
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    _require(len(raw) <= MAX_BYTES, "evidence exceeds size limit")
    return raw


def _digest(value):
    return hashlib.sha256(value).hexdigest()


def _text(value):
    return isinstance(value, str) and 0 < len(value) <= 300 and not any(
        marker in value for marker in ("\\", ":/", "-----BEGIN", "\n", "\r")
    ) and not value.startswith("/")


def _schema(receipt):
    _require(isinstance(receipt, dict), "invalid receipt fields")
    version = receipt.get("schema_version")
    _require(type(version) is int and version in (1, 2), "unsupported schema")
    _require(set(receipt) == (TOP if version == 1 else TOP | {"execution"}), "invalid receipt fields")
    scenario = receipt["scenario"]
    _require(isinstance(scenario, str) and scenario in {"allowed_service_a", *EXPECTED_TESTS}, "unknown scenario")
    live = scenario == "allowed_service_a"
    _require(receipt["evidence_kind"] == ("LIVE_ATTEMPT" if live else "REGRESSION"), "incorrect evidence kind")
    _require(receipt["cleanup"] in ("CLEAN", "FAILED", "UNCONFIRMED"), "invalid cleanup")
    provenance = receipt["provenance"]
    _require(isinstance(provenance, dict) and set(provenance) == PROVENANCE, "invalid provenance fields")
    _require(isinstance(provenance["source_commit"], str) and re.fullmatch(r"[0-9a-f]{40}", provenance["source_commit"]), "invalid commit")
    _require(_text(provenance["platform"]), "invalid platform")
    if version == 2:
        execution = receipt["execution"]
        _require(isinstance(execution, dict) and set(execution) == EXECUTION, "invalid execution fields")
        _require(execution["mode"] == "mac_host_linux_container", "invalid execution mode")
        host = execution["host_platform"]
        _require(isinstance(host, str) and host in NATIVE_CONTAINERS, "invalid host platform")
        _require(execution["execution_platform"] == NATIVE_CONTAINERS[host], "non-native container architecture")
        _require(provenance["platform"] == execution["execution_platform"], "execution provenance mismatch")
        for field, pattern in (("image_id", r"sha256:[0-9a-f]{64}"), ("container_id", r"[0-9a-f]{64}")):
            _require(isinstance(execution[field], str) and re.fullmatch(pattern, execution[field]),
                     "invalid container identity")
    for field in ("source_hashes", "binary_hashes", "toolchain"):
        values = provenance[field]
        _require(isinstance(values, dict) and bool(values), "missing provenance inventory")
        for name, value in values.items():
            _require(_text(name), "invalid provenance name")
            if field == "source_hashes":
                parts = PurePosixPath(name).parts
                _require(not any(p in ("..", ".") for p in parts) and ":" not in name and
                         not name.lower().endswith((".pem", ".key")), "invalid source path")
            else:
                _require(re.fullmatch(r"[A-Za-z0-9_.-]+", name), "invalid provenance role")
            _require(_text(value) if field == "toolchain" else
                     isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value), "invalid provenance value")
    result = receipt["result"]
    _require(isinstance(result, dict) and set(result) == RESULT, "invalid result fields")
    _require(result["exit_code"] is None or type(result["exit_code"]) is int, "invalid exit code")
    _require(type(result["cancelled"]) is bool and type(result["timeout"]) is bool, "invalid result flags")
    _require(_text(result["reason"]), "invalid reason")
    _require(result["expected_tests"] == ([] if live else [EXPECTED_TESTS[scenario]]), "incorrect expected tests")
    _require(result["regression_kind"] == (None if live else "fixture_regression"), "incorrect regression classification")
    artifacts = receipt["artifacts"]
    _require(isinstance(artifacts, dict), "invalid artifact inventory")
    permitted = {"application.json", "destination.json"} if live else {"test-output.txt"}
    _require(set(artifacts).issubset(permitted), "unexpected artifact name")
    for digest in artifacts.values():
        _require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest), "invalid artifact hash")
    return live, permitted


def _test_output(raw, expected):
    text = raw.decode("utf-8")
    lines = text.splitlines()
    _require(bool(lines), "empty regression output")
    runs, passes = set(), set()
    suite_pass = False
    for line in lines:
        line = line.strip()
        if line.startswith("{"):
            event = _json(line)
            _require(isinstance(event, dict), "invalid test event")
            action, name = event.get("Action"), event.get("Test")
            _require(action not in ("skip", "fail"), "regression failed or skipped")
            if action == "run" and name:
                runs.add(name)
            if action == "pass":
                if name:
                    _require(name in runs, "test pass without run")
                    passes.add(name)
                else:
                    suite_pass = True
        else:
            _require(not re.match(r"(?:--- (?:SKIP|FAIL):|FAIL(?:\s|$)|panic:)", line), "regression failed or skipped")
            match = re.fullmatch(r"=== RUN\s+(\S+)", line)
            if match:
                runs.add(match[1])
            match = re.fullmatch(r"--- PASS: (\S+) \([0-9.]+s\)", line)
            if match:
                _require(match[1] in runs, "test pass without run")
                passes.add(match[1])
            suite_pass |= line == "PASS"
    _require(expected in runs and runs == passes and suite_pass, "missing executed passing expected test")


def write_receipt(run_dir: Path, scenario: str, provenance: dict, result: dict,
                  cleanup: str, artifacts: dict[str, str], execution: dict | None = None) -> dict:
    """Write new evidence; v2 callers must supply outer-host cleanup observations."""
    run_dir = Path(run_dir)
    _safe_path(run_dir)
    encoded = {name: value.encode("utf-8") for name, value in artifacts.items()}
    receipt = dict(schema_version=1 if execution is None else 2, scenario=scenario,
                   evidence_kind="LIVE_ATTEMPT" if scenario == "allowed_service_a" else "REGRESSION",
                   provenance=provenance, result=result, cleanup=cleanup,
                   artifacts={name: _digest(raw) for name, raw in encoded.items()})
    if execution is not None:
        receipt["execution"] = execution
    _schema(receipt)
    serialized = json.dumps(receipt, allow_nan=False, sort_keys=True, indent=2).encode("utf-8")
    _require(len(serialized) <= MAX_BYTES and all(len(raw) <= MAX_BYTES for raw in encoded.values()), "evidence exceeds size limit")
    run_dir.mkdir(parents=True, exist_ok=True)
    for name in (*encoded, "receipt.json"):
        path = run_dir / name
        _safe_path(path)
        _require(not path.exists(), "evidence already exists")
    for name, raw in {**encoded, "receipt.json": serialized}.items():
        with (run_dir / name).open("xb") as stream:
            stream.write(raw)
    return receipt


def _attempt_schema(attempt):
    _require(isinstance(attempt, dict) and set(attempt) == ATTEMPT, "invalid attempt fields")
    _require(attempt["schema"] == "nbsr-demo-attempt-v1", "unsupported attempt schema")
    for field, pattern in (("run_id", r"demo-[0-9a-f]{32}"), ("source_commit", r"[0-9a-f]{40}"),
                           ("image_id", r"sha256:[0-9a-f]{64}")):
        _require(isinstance(attempt[field], str) and re.fullmatch(pattern, attempt[field]), "invalid attempt identity")
    container = attempt["container_id"]
    _require(container is None or isinstance(container, str) and re.fullmatch(r"[0-9a-f]{64}", container),
             "invalid attempt container")
    _require(isinstance(attempt["host_platform"], str) and attempt["host_platform"] in NATIVE_CONTAINERS,
             "invalid attempt host")
    _require(attempt["exit_code"] is None or type(attempt["exit_code"]) is int, "invalid attempt exit code")
    _require(_text(attempt["reason"]), "invalid attempt reason")
    _require(attempt["cleanup"] in ("CLEAN", "UNCONFIRMED", "FAILED"), "invalid attempt cleanup")
    sources = attempt["expected_source_hashes"]
    _require(isinstance(sources, dict) and bool(sources), "missing expected source inventory")
    for name, digest in sources.items():
        _require(_text(name) and ":" not in name and
                 not any(part in ("", ".", "..") for part in name.split("/")) and
                 not name.lower().endswith((".pem", ".key")), "invalid expected source path")
        _require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest), "invalid expected source hash")


def write_attempt(run_dir: Path, attempt: dict) -> dict:
    """Retain an outer attempt; expected source hashes do not claim execution."""
    _attempt_schema(attempt)
    raw = json.dumps(attempt, allow_nan=False, sort_keys=True, indent=2).encode("utf-8")
    _require(len(raw) <= MAX_BYTES, "evidence exceeds size limit")
    run_dir = Path(run_dir)
    _safe_path(run_dir / "attempt.json")
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / "attempt.json").open("xb") as stream:
        stream.write(raw)
    return attempt


def _verify_attempt(run_dir):
    attempt = _json(_read(run_dir / "attempt.json"))
    _attempt_schema(attempt)
    failed = attempt["exit_code"] not in (None, 0) or attempt["cleanup"] == "FAILED"
    errors = ["scenario evidence unavailable; expected source inventory does not prove execution"]
    if attempt["cleanup"] != "CLEAN":
        errors.append("cleanup is not confirmed clean")
    return dict(valid=True, outcome="FAIL" if failed else "INCOMPLETE", scenario_outcome="INCOMPLETE",
                cleanup=attempt["cleanup"], errors=errors, receipt=attempt)


def verify(run_dir: Path) -> dict:
    """Recompute hashes and fixed scenario assertions without executing tools."""
    receipt = None
    errors = []
    cleanup = "UNCONFIRMED"
    scenario_outcome = "INCOMPLETE"
    try:
        run_dir = Path(run_dir)
        _safe_path(run_dir / "receipt.json")
        if not (run_dir / "receipt.json").exists():
            return _verify_attempt(run_dir)
        receipt = _json(_read(run_dir / "receipt.json"))
        live, required = _schema(receipt)
        cleanup = receipt["cleanup"]
        raw = {}
        for name, digest in receipt["artifacts"].items():
            raw[name] = _read(run_dir / name)
            _require(_digest(raw[name]) == digest, "artifact hash mismatch")
        result = receipt["result"]
        if result["exit_code"] not in (None, 0) or result["cancelled"] or result["timeout"] or result["reason"] != "completed":
            scenario_outcome = "FAIL"
        elif result["exit_code"] is None:
            errors.append("scenario did not execute")
        else:
            _require(set(raw) == required, "missing required raw evidence")
            if live:
                application = _json(raw["application.json"])
                destination = _json(raw["destination.json"])
                _require(isinstance(application, dict) and application.get("body") == BODY, "application body mismatch")
                _require(isinstance(destination, dict) and destination.get("status") == "PASS" and
                         type(destination.get("backend_requests")) is int and destination["backend_requests"] == 1,
                         "destination assertion failed")
            else:
                _test_output(raw["test-output.txt"], EXPECTED_TESTS[receipt["scenario"]])
            scenario_outcome = "PASS"
    except (ValueError, OSError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
        # Do not export OS exceptions, which can contain private absolute paths.
        errors.append(str(exc) if type(exc) is ValueError else "unreadable or malformed evidence")
    outcome = scenario_outcome
    if cleanup == "FAILED":
        outcome = "FAIL"
    elif errors or cleanup != "CLEAN":
        outcome = "INCOMPLETE" if scenario_outcome != "FAIL" else "FAIL"
    if cleanup != "CLEAN":
        errors.append("cleanup is not confirmed clean")
    return dict(valid=not errors, outcome=outcome, scenario_outcome=scenario_outcome,
                cleanup=cleanup, errors=errors, receipt=receipt)
