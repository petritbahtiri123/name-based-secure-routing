from __future__ import annotations

import importlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence" / "performance" / "v2" / "b4b-772996e9cced"
TASK4B_EVIDENCE = ROOT / "evidence" / "performance" / "v2" / "b4b-task4b-final2-b0498aceb519"


def record(*, clients: int, goodput: float, p99: int, success_ratio: float = 1.0,
           errors: int = 0, timeouts: int = 0, cleanup: bool = True) -> dict:
    scheduled = clients
    return {
        "clients": clients,
        "scheduled_admissions": scheduled,
        "successful_admissions": round(scheduled * success_ratio),
        "failed_admissions": scheduled - round(scheduled * success_ratio),
        "errors": errors,
        "timeouts": timeouts,
        "established_goodput_bytes_per_second": goodput,
        "established_p99_latency_ns": p99,
        "admission_elapsed_seconds": 1.0,
        "cleanup": {"all_zero": cleanup, "processes_exited": True},
    }


def test_task4_progression_is_exact_and_bounded() -> None:
    b4b = importlib.import_module("scripts.run_b4b_v2")

    assert b4b.CLIENT_LEVELS == (8, 16, 32, 64, 128, 256, 512)
    assert b4b.CONNECTIONS_PER_CLIENT == 1


def test_repeat_count_extends_to_five_when_either_rate_or_goodput_cv_exceeds_five_percent() -> None:
    b4b = importlib.import_module("scripts.run_b4b_v2")
    stable = [
        {"established_goodput_bytes_per_second": 100.0, "admission_rate": 50.0},
        {"established_goodput_bytes_per_second": 101.0, "admission_rate": 51.0},
        {"established_goodput_bytes_per_second": 99.0, "admission_rate": 49.0},
    ]
    variable = [
        {"established_goodput_bytes_per_second": 100.0, "admission_rate": 40.0},
        {"established_goodput_bytes_per_second": 101.0, "admission_rate": 50.0},
        {"established_goodput_bytes_per_second": 99.0, "admission_rate": 60.0},
    ]

    assert b4b.required_repeats(stable) == 3
    assert b4b.required_repeats(variable) == 5


def test_v2_classification_uses_funding_grade_stable_degraded_and_saturated_rules() -> None:
    b4b = importlib.import_module("scripts.run_b4b_v2")
    baseline = record(clients=0, goodput=100.0, p99=100)

    assert b4b.classify_cell(record(clients=8, goodput=95.0, p99=125), baseline) == "STABLE"
    assert b4b.classify_cell(record(clients=16, goodput=85.0, p99=140), baseline) == "DEGRADED"
    assert b4b.classify_cell(record(clients=32, goodput=74.0, p99=150), baseline) == "SATURATED"
    assert b4b.classify_cell(
        record(clients=32, goodput=95.0, p99=120, success_ratio=0.89), baseline
    ) == "SATURATED"


def test_saturation_stop_requires_three_complete_valid_repeats() -> None:
    b4b = importlib.import_module("scripts.run_b4b_v2")
    saturated = record(clients=128, goodput=70.0, p99=250)
    saturated["status"] = "SATURATED"
    saturated["valid"] = True

    assert not b4b.should_stop_after_saturation([saturated, saturated])
    assert b4b.should_stop_after_saturation([saturated, saturated, saturated])
    assert not b4b.should_stop_after_saturation(
        [saturated, saturated, {**saturated, "valid": False}]
    )


def test_authoritative_analysis_preserves_regions_cleanup_and_attribution() -> None:
    analysis = json.loads((EVIDENCE / "analysis.json").read_text(encoding="utf-8"))
    cells = {cell["clients"]: cell for cell in analysis["cells"]}

    assert analysis["evidence"] == "PASS"
    assert analysis["system"] == "SATURATED"
    assert cells[8]["status"] == "STABLE"
    assert all(cells[clients]["status"] == "DEGRADED" for clients in (16, 32, 64, 128))
    assert cells[256]["status"] == "SATURATED"
    assert all(cell["cleanup_pass"] and cell["process_cleanup_pass"] for cell in cells.values())
    assert analysis["limiting_boundary"]["classification"].startswith("HARNESS_LIMITED")
    assert analysis["limiting_boundary"]["host_processor_time_percent_median"] < 90


def test_evidence_classification_fails_closed_on_cleanup_failure() -> None:
    b4b = importlib.import_module("scripts.run_b4b_v2")
    cells = [
        {"status": "STABLE", "cleanup_pass": True, "process_cleanup_pass": True},
        {"status": "DEGRADED", "cleanup_pass": True, "process_cleanup_pass": True},
        {"status": "SATURATED", "cleanup_pass": False, "process_cleanup_pass": True},
    ]

    assert b4b.classify_evidence(cells, invalid=[]) == "FAIL"


def test_task4b_evidence_preserves_saturation_and_cleanup_failure() -> None:
    analysis = json.loads((TASK4B_EVIDENCE / "analysis.json").read_text(encoding="utf-8"))
    cells = {cell["clients"]: cell for cell in analysis["cells"]}

    assert analysis["evidence"] == "FAIL"
    assert analysis["system"] == "SATURATED"
    assert all(cells[clients]["status"] == "STABLE" for clients in (8, 16, 32, 64))
    assert all(cells[clients]["status"] == "SATURATED" for clients in (128, 256, 512))
    assert all(cells[clients]["median_peak_processes"] == 4 for clients in (8, 64, 128, 256, 512))
    assert all(cells[clients]["process_cleanup_pass"] for clients in cells)
    assert not all(cells[clients]["cleanup_pass"] for clients in (128, 256, 512))
