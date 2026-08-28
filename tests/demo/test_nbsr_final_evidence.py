import copy
import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
VERIFIER = ROOT / "scripts" / "demo" / "verify-nbsr-demo.py"
SOURCE_SHA = "19f6468f77175adcb7ad410c2016aa889b964dc0"
BODY = "hello from service-a through NBSR"


def load_verifier():
    spec = importlib.util.spec_from_file_location("verify_nbsr_demo_final", VERIFIER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def valid_evidence():
    stages = [
        "RESOLUTION_CANONICALIZED", "MAPPING_ACQUIRED", "FLOW_CORRELATED",
        "AUTHORITY_VERIFIED", "TS_ACTIVE", "SC_AUTHORIZED",
        "STREAM_CREDIT_ADMITTED", "APPLICATION_STREAM_ADMITTED",
        "BACKEND_RESPONSE_RETURNED",
    ]
    negatives = [
        "UNKNOWN_SERVICE_DENIED", "AUTHORITY_DENIED",
        "SERVICE_DIGEST_MISMATCH", "EXPIRED_MAPPING",
        "DIRECT_BACKEND_UNAVAILABLE", "SHARED_IP_ISOLATION_POST_DEMO",
    ]
    return {
        "schema": "nbsr-end-to-end-demo-evidence-v1",
        "overall": "PASS",
        "provenance": {
            "source_branch": "codex/nbsr-v3-wp0-wp1", "source_sha": SOURCE_SHA,
            "production_source_clean": True, "platform": "WINDOWS_LOOPBACK",
            "run_id": "task7-final-case", "toolchains": {
                "go": "go1.25.0", "rustc": "rustc 1.97.1", "cargo": "cargo 1.97.1",
                "powershell": "7.5.2", "python": "3.13.0"},
        },
        "binary_sha256": {name: "a" * 64 for name in ("authority", "client", "backend", "destination")},
        "requested_identity": {
            "presentation_name": "service-a.nbsr.test", "canonical_name": "service-a.nbsr.test",
            "port": 8080, "service_digest": hashlib.sha256(b"service-a.nbsr.test").hexdigest(),
            "synthetic_ip": "127.0.0.2",
        },
        "route_stages": [{"stage": stage, "status": "PASS", "scope": "LIVE_DEMO"} for stage in stages],
        "result": {
            "status": "PASS", "response_body": BODY,
            "response_sha256": hashlib.sha256(BODY.encode()).hexdigest(),
            "backend_invocations": 1,
        },
        "negative_matrix": [
            {"scenario": scenario, "status": "PASS", "backend_invocations": 0,
             "fallback_count": 0, "replay_count": 0, "cleanup": "CLEAN",
             "scope": "REGRESSION"}
            for scenario in negatives
        ],
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


def reject(evidence):
    verifier = load_verifier()
    with pytest.raises(verifier.VerificationError):
        verifier.validate_final_evidence(evidence)


@pytest.mark.parametrize("field", ["provenance", "binary_sha256", "requested_identity", "route_stages", "result", "negative_matrix", "cleanup", "privacy"])
def test_final_evidence_rejects_missing_required_section(valid_evidence, field):
    del valid_evidence[field]
    reject(valid_evidence)


@pytest.mark.parametrize("stage", [
    "RESOLUTION_CANONICALIZED", "MAPPING_ACQUIRED", "FLOW_CORRELATED",
    "AUTHORITY_VERIFIED", "TS_ACTIVE", "SC_AUTHORIZED",
    "STREAM_CREDIT_ADMITTED", "APPLICATION_STREAM_ADMITTED",
    "BACKEND_RESPONSE_RETURNED",
])
def test_final_evidence_rejects_missing_route_stage(valid_evidence, stage):
    valid_evidence["route_stages"] = [item for item in valid_evidence["route_stages"] if item["stage"] != stage]
    reject(valid_evidence)


def test_final_evidence_rejects_missing_binary_hash(valid_evidence):
    del valid_evidence["binary_sha256"]["backend"]
    reject(valid_evidence)


def test_final_evidence_rejects_wrong_source_sha(valid_evidence):
    valid_evidence["provenance"]["source_sha"] = "0" * 40
    reject(valid_evidence)


def test_final_evidence_rejects_missing_negative(valid_evidence):
    valid_evidence["negative_matrix"].pop()
    reject(valid_evidence)


@pytest.mark.parametrize(("field", "value"), [("backend_invocations", 1), ("fallback_count", 1), ("replay_count", 1)])
def test_final_evidence_rejects_denied_scenario_activity(valid_evidence, field, value):
    valid_evidence["negative_matrix"][0][field] = value
    reject(valid_evidence)


def test_final_evidence_rejects_running_cleanup(valid_evidence):
    valid_evidence["cleanup"]["lifecycle"] = "RUNNING"
    reject(valid_evidence)


@pytest.mark.parametrize("field", ["origin_endpoint", "backend_path", "backend_command", "private_key", "signing_key", "route_grant", "proof", "credential", "token", "mapping_id", "local_flow_id"])
def test_final_evidence_rejects_forbidden_fields(valid_evidence, field):
    valid_evidence[field] = "forbidden"
    reject(valid_evidence)


def test_final_evidence_rejects_service_b_falsely_live(valid_evidence):
    valid_evidence["service_b_live_demo"] = "YES"
    reject(valid_evidence)


def test_final_evidence_rejects_regression_falsely_labeled_live(valid_evidence):
    valid_evidence["shared_ip_isolation"]["scope"] = "LIVE_DEMO"
    reject(valid_evidence)


def test_final_evidence_rejects_malformed_response_digest(valid_evidence):
    valid_evidence["result"]["response_sha256"] = "f" * 64
    reject(valid_evidence)


def test_final_evidence_rejects_overall_pass_with_failed_scenario(valid_evidence):
    valid_evidence["negative_matrix"][0]["status"] = "FAIL"
    reject(valid_evidence)


def test_final_evidence_rejects_success_with_zero_backend(valid_evidence):
    valid_evidence["result"]["backend_invocations"] = 0
    reject(valid_evidence)


def test_final_evidence_accepts_complete_allowlisted_bundle(valid_evidence):
    assert load_verifier().validate_final_evidence(copy.deepcopy(valid_evidence)) is None


def test_task6_verifier_allows_only_task6_or_task7_closure_heads():
    verifier = load_verifier()
    assert verifier.task6_verifier_head_allowed("8f76ade9203b706f95c6d4668d46c4fd02d9b2b8")
    assert verifier.task6_verifier_head_allowed(SOURCE_SHA)
    assert not verifier.task6_verifier_head_allowed("0" * 40)
