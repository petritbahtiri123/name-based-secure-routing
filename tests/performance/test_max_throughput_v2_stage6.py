from __future__ import annotations

import importlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence" / "performance" / "v2" / "max-throughput-stage6-31f927f8681c"


def test_stage6_matrix_is_nbsr_only_and_below_saturated_region() -> None:
    stage6 = importlib.import_module("scripts.run_max_throughput_v2_stage6")

    cells = stage6.stage6_cells()

    assert len(cells) == 4
    assert {cell["path"] for cell in cells} == {"nbsr"}
    assert {cell["affinity_mode"] for cell in cells} == {"physical", "smt"}
    assert {cell["endpoint_groups"] for cell in cells} == {1, 2}
    assert all(cell["payload_bytes"] == 16384 for cell in cells)
    assert all(cell["streams_per_group"] == 1 for cell in cells)
    assert all(cell["outstanding_per_stream"] == 4 for cell in cells)
    assert all(cell["runtime_workers"] == 1 for cell in cells)


def test_stage6_strict_stable_uses_funding_grade_rules() -> None:
    stage6 = importlib.import_module("scripts.run_max_throughput_v2_stage6")
    baseline = {
        "median_p99_latency_ns": 1_000_000,
    }
    candidate = {
        "valid": True,
        "cleanup_pass": True,
        "errors": 0,
        "timeouts": 0,
        "throughput_cv": 0.05,
        "median_p99_latency_ns": 1_250_000,
        "achieved_offered_ratio": 1.0,
        "backlog_drained": True,
    }

    assert stage6.is_strict_stable(candidate, baseline)
    assert not stage6.is_strict_stable({**candidate, "throughput_cv": 0.05001}, baseline)
    assert not stage6.is_strict_stable(
        {**candidate, "median_p99_latency_ns": 1_250_001}, baseline
    )
    assert not stage6.is_strict_stable(
        {**candidate, "achieved_offered_ratio": 0.949}, baseline
    )


def test_stage6_repeat_extension_stops_at_ten() -> None:
    stage6 = importlib.import_module("scripts.run_max_throughput_v2_stage6")

    assert stage6.required_repeats([3.0, 3.0, 3.0, 3.0, 3.0]) == 5
    assert stage6.required_repeats([2.0, 3.0, 2.0, 3.0, 2.0]) == 10
    assert stage6.required_repeats([2.0] * 10) == 10


def test_stage6_analysis_matches_authoritative_manifest() -> None:
    manifest = json.loads((EVIDENCE / "manifest.json").read_text(encoding="utf-8"))
    analysis = json.loads((EVIDENCE / "analysis.json").read_text(encoding="utf-8"))
    strict = [cell for cell in manifest["cells"] if cell["strict_stable"]]

    assert manifest["all_valid"] and manifest["all_cleanup_pass"]
    assert manifest["errors"] == manifest["timeouts"] == 0
    assert sum(cell["repeat_count"] for cell in manifest["cells"]) == 20
    assert analysis["highest_single_stage6_nbsr_gbps"] == manifest[
        "highest_single_nbsr_gbps"
    ]
    assert analysis["highest_repeatable_stage6_nbsr_gbps"] == manifest[
        "highest_repeatable_nbsr_gbps"
    ]
    assert analysis["highest_strict_stable_stage6_nbsr_gbps"] == max(
        cell["median_gbps"] for cell in strict
    )
