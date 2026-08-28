import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
VERIFIER = ROOT / "scripts" / "demo" / "verify-nbsr-demo.py"


def load_verifier():
    spec = importlib.util.spec_from_file_location("verify_nbsr_demo", VERIFIER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def completed_state(tmp_path):
    runtime = tmp_path / "runtime" / "task6-case"
    (runtime / "destination").mkdir(parents=True)
    (runtime / "readiness").mkdir()
    result = runtime / "destination" / "result.json"
    result.write_text(json.dumps({"backend_requests": 1, "status": "PASS"}), encoding="utf-8")
    ack = runtime / "readiness" / "completion.ack"
    ack.write_text("complete", encoding="utf-8")
    state = runtime / "state.json"
    state.write_text(json.dumps({
        "schema": "nbsr-demo-state-v1", "run_id": "task6-case", "lifecycle": "STOPPED",
        "source_sha": "8f76ade9203b706f95c6d4668d46c4fd02d9b2b8",
        "runtime_root": str(runtime), "service": "service-a.nbsr.test",
        "synthetic_ip": "127.0.0.2", "endpoints": {
            "acp": "https://127.0.0.1:18443", "destination": "127.0.0.1:18444", "proxy": "127.0.0.1:18080"},
        "readiness": {"completion_ack": str(ack)},
    }), encoding="utf-8")
    return state


def matrix(completed_state):
    return load_verifier().build_result(completed_state, run_regressions=False, enforce_repository_runtime=False)


def scenario(result, name):
    return next(item for item in result["scenarios"] if item["scenario"] == name)


def test_service_a_success(completed_state):
    item = scenario(matrix(completed_state), "SERVICE_A_SUCCESS")
    assert (item["status"], item["response_body"], item["backend_invocations"], item["cleanup"]) == (
        "PASS", "hello from service-a through NBSR", 1, "CLEAN")


@pytest.mark.parametrize("name", ["UNKNOWN_SERVICE_DENIED", "AUTHORITY_DENIED", "SERVICE_DIGEST_MISMATCH", "EXPIRED_MAPPING"])
def test_denied_zero_backend(completed_state, name):
    item = scenario(matrix(completed_state), name)
    assert item["status"] == "PASS"
    assert item["backend_invocations"] == item["fallback_count"] == item["replay_count"] == 0


def test_unknown_service_denied_zero_backend(completed_state):
    assert scenario(matrix(completed_state), "UNKNOWN_SERVICE_DENIED")["backend_invocations"] == 0


def test_authority_denied_zero_backend(completed_state):
    assert scenario(matrix(completed_state), "AUTHORITY_DENIED")["backend_invocations"] == 0


def test_service_digest_mismatch_zero_backend(completed_state):
    assert scenario(matrix(completed_state), "SERVICE_DIGEST_MISMATCH")["backend_invocations"] == 0


def test_expired_mapping_zero_backend(completed_state):
    assert scenario(matrix(completed_state), "EXPIRED_MAPPING")["backend_invocations"] == 0


def test_direct_backend_path_unavailable(completed_state):
    item = scenario(matrix(completed_state), "DIRECT_BACKEND_UNAVAILABLE")
    assert item["outcome"] == "UNAVAILABLE BY TOPOLOGY"
    assert "origin" not in json.dumps(item).lower()


def test_all_negative_scenarios_cleanup(completed_state):
    negatives = matrix(completed_state)["scenarios"][1:]
    assert all(item["cleanup"] == "CLEAN" for item in negatives)


def test_no_negative_scenario_replays_or_falls_back(completed_state):
    negatives = matrix(completed_state)["scenarios"][1:]
    assert all(item["fallback_count"] == item["replay_count"] == 0 for item in negatives)


def test_service_b_post_demo_requires_tranche6_isolation(completed_state):
    result = matrix(completed_state)
    assert result["service_b_live_demo"] == "NO — POST-DEMO"
    item = scenario(result, "SHARED_IP_ISOLATION_POST_DEMO")
    assert item["regression"] == "TestSharedSyntheticIPCorrelatesSamePortServicesEndToEnd"
    assert (item["service_count"], item["shared_synthetic_ip"], item["port"], item["cross_correlation_count"]) == (2, "127.80.0.1", 443, 0)


def test_state_must_be_exact_and_contained(tmp_path):
    verifier = load_verifier()
    with pytest.raises(verifier.VerificationError):
        verifier.build_result(tmp_path / "missing.json", run_regressions=False, enforce_repository_runtime=False)


def test_running_state_cannot_claim_final_cleanup(completed_state):
    verifier = load_verifier()
    state = json.loads(completed_state.read_text(encoding="utf-8"))
    state["lifecycle"] = "RUNNING"
    completed_state.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(verifier.VerificationError):
        verifier.build_result(completed_state, run_regressions=False, enforce_repository_runtime=False)


def test_cli_has_no_regression_bypass(completed_state):
    completed = subprocess.run([sys.executable, str(VERIFIER), "--state", str(completed_state), "--skip-regressions"], cwd=ROOT, text=True, capture_output=True)
    assert completed.returncode != 0


def test_result_is_bounded(completed_state):
    result = matrix(completed_state)
    rendered = json.dumps(result, ensure_ascii=False)
    assert result["schema"] == "nbsr-demo-task6-result-v1"
    forbidden = (
        "routegrant", "private_key", "backend_command", "backend_path",
        "origin_endpoint", "credential", "proof", ".exe", "build_root",
    )
    rendered = rendered.lower()
    assert all(value not in rendered for value in forbidden)


def test_task6_evidence_privacy_passes_without_copying_operator_paths(completed_state):
    result = matrix(completed_state)
    assert result["evidence_privacy"] == "PASS"
