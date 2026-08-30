from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.security.adversarial_campaign import SCENARIOS, analyze_results, source_hashes, validate_result


REQUIRED = {
    "replayed_grant_ticket",
    "tampered_grant_ticket",
    "wrong_service_name",
    "wrong_port_transport",
    "wrong_pop_key",
    "expired_grant",
    "revoked_credential_grant",
    "stale_generation_sequence",
    "downgrade_attempt",
    "unauthorized_source",
    "direct_origin_scan",
    "malformed_control_wire",
    "forged_identity_source_binding",
    "edge_session_failure_recovery",
}


def passing_result(scenario_id: str) -> dict:
    scenario = next(item for item in SCENARIOS if item.id == scenario_id)
    status = scenario.pass_classification
    return {
        "scenario": scenario.id,
        "attack": scenario.attack,
        "expected": scenario.expected,
        "actual": scenario.observed_on_pass,
        "reason_code": scenario.reason_code,
        "protected_service_reachable": False if status == "PASS" else None,
        "cleanup": scenario.cleanup_on_pass,
        "status": status,
        "command": list(scenario.command),
        "exit_code": 0,
        "duration_seconds": 0.1,
        "stdout_log": f"raw/{scenario.id}.stdout.log",
        "stderr_log": f"raw/{scenario.id}.stderr.log",
    }


def test_manifest_is_closed_complete_and_uses_direct_process_commands() -> None:
    assert {scenario.id for scenario in SCENARIOS} == REQUIRED
    assert len(SCENARIOS) == len(REQUIRED)
    for scenario in SCENARIOS:
        assert scenario.command
        assert scenario.command[0] in {"cargo", "go", "python"}
        assert all(token not in {"&&", ";", "|"} for token in scenario.command)
        assert all(not Path(token).is_absolute() for token in scenario.command)
        assert scenario.reason_code


def test_negative_pass_requires_unreachable_service_and_clean_state() -> None:
    result = passing_result("replayed_grant_ticket")
    validate_result(result)
    result["protected_service_reachable"] = True
    with pytest.raises(ValueError, match="reachable"):
        validate_result(result)
    result["protected_service_reachable"] = False
    result["cleanup"] = "LEAKED"
    with pytest.raises(ValueError, match="cleanup"):
        validate_result(result)


def test_failed_command_is_fail_not_security_pass() -> None:
    results = [passing_result(scenario.id) for scenario in SCENARIOS]
    failed = next(item for item in results if item["scenario"] == "tampered_grant_ticket")
    failed["exit_code"] = 1
    failed["status"] = "FAIL"
    analysis = analyze_results(results)
    assert analysis["overall"] == "FAIL"
    assert analysis["counts"] == {"PASS": 12, "FAIL": 1, "INCONCLUSIVE": 1}


def test_inconclusive_direct_scan_prevents_complete_classification() -> None:
    results = [passing_result(scenario.id) for scenario in SCENARIOS]
    direct = next(item for item in results if item["scenario"] == "direct_origin_scan")
    direct.update(
        status="INCONCLUSIVE",
        actual="No current-SHA network-isolated origin scan was executed.",
        reason_code="NOT_CURRENT_SHA_NETWORK_ISOLATION",
        cleanup="NOT_APPLICABLE",
        exit_code=None,
    )
    analysis = analyze_results(results)
    assert analysis["overall"] == "PARTIAL"
    assert analysis["counts"] == {"PASS": 13, "FAIL": 0, "INCONCLUSIVE": 1}


def test_result_schema_rejects_missing_or_extra_fields() -> None:
    result = passing_result("malformed_control_wire")
    del result["reason_code"]
    with pytest.raises(ValueError, match="schema"):
        validate_result(result)
    result = passing_result("malformed_control_wire")
    result["invented"] = True
    with pytest.raises(ValueError, match="schema"):
        validate_result(result)


def test_machine_result_round_trips_without_absolute_paths(tmp_path: Path) -> None:
    result = passing_result("wrong_pop_key")
    path = tmp_path / "result.json"
    path.write_text(json.dumps(result, sort_keys=True), encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    validate_result(loaded)
    assert "C:\\" not in path.read_text(encoding="utf-8")


def test_source_metadata_is_relative_and_hash_bound() -> None:
    hashes = source_hashes()
    assert set(hashes) == {
        "scripts/security/adversarial_campaign.py",
        "tests/security/test_adversarial_campaign.py",
    }
    assert all(len(value) == 64 for value in hashes.values())
