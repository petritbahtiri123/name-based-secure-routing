"""The external contract must distinguish executable coverage from missing ports."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "config/benchmarks/funding-grade-v2-server-matrix.json"


def test_external_matrix_has_closed_workloads_and_required_evidence():
    value = json.loads(MATRIX.read_text(encoding="utf-8"))
    assert value["schema"] == "nbsr-server-validation-definition-v1"
    assert value["execution_status"] == "NOT_RUN"
    assert value["definition_status"] == "PARTIAL_REQUIRED_PORTING"
    assert value["physical_cores"] == [1, 2, 4, 8, 16, 32]
    assert value["paths"] == ["direct", "nbsr"]
    assert set(value["placements"]) == {"loopback_shared_core_pool", "two_host_disjoint_core_pools"}
    for field in ("hardware", "topology", "affinity", "nic", "profiler", "repeat_policy", "stop_gates", "evidence"):
        assert value[field]
    assert value["repeat_policy"]["minimum_valid"] == 3
    assert value["repeat_policy"]["high_cv_valid"] == 5
    assert value["repeat_policy"]["invalid_replacement"] is False
    assert value["repeat_policy"]["discard_unfavorable_valid"] is False
    assert value["workloads"]["forwarding"]["payload_bytes"] == [1024, 16384]
    assert value["workloads"]["soak"]["authoritative_seconds"] == [3600, 7200]
    assert value["workloads"]["memory"]["cardinalities"][-1] >= 1024


def test_missing_backends_cannot_be_reported_as_executed_or_complete():
    value = json.loads(MATRIX.read_text(encoding="utf-8"))
    for coverage in value["coverage"].values():
        assert coverage["status"] in {"AUTHORED_UNEXECUTED", "PARTIAL", "NOT_IMPLEMENTED"}
        if coverage["status"] == "NOT_IMPLEMENTED":
            assert coverage["command"] is None
            assert coverage["missing"]
        for source in coverage.get("sources", []):
            assert (ROOT / source).is_file(), source
    assert value["coverage"]["linux_sustained_b5"]["status"] == "NOT_IMPLEMENTED"
    assert value["acceptance"]["definition_pass_requires_all_commands_executable"] is True
    assert value["acceptance"]["server_claim_requires_external_raw_results"] is True
    assert value["evidence"]["preserve_failed_and_partial"] is True
