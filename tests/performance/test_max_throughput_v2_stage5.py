from __future__ import annotations

import importlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence" / "performance" / "v2" / "max-throughput-stage5-5a9477d623dc"


def test_stage5_matrix_matches_affinity_modes_and_priority_shapes() -> None:
    stage5 = importlib.import_module("scripts.run_max_throughput_v2_stage5")
    cells = stage5.stage5_cells()

    assert len(cells) == 8
    assert {cell["path"] for cell in cells} == {"direct", "nbsr"}
    assert {cell["affinity_mode"] for cell in cells} == {"physical", "smt"}
    assert {cell["endpoint_groups"] for cell in cells} == {2, 4}
    assert all(cell["payload_bytes"] == 16384 for cell in cells)
    assert all(cell["streams_per_group"] == 1 for cell in cells)
    assert all(cell["outstanding_per_stream"] == 4 for cell in cells)
    assert all(cell["runtime_workers"] == 1 for cell in cells)


def test_stage5_affinity_plan_preserves_physical_and_enables_smt() -> None:
    stage5 = importlib.import_module("scripts.run_max_throughput_v2_stage5")
    topology = {
        "verified": True,
        "logical_processors": 8,
        "cores": [
            {"logical_mask": 0x3},
            {"logical_mask": 0xC},
            {"logical_mask": 0x30},
            {"logical_mask": 0xC0},
        ],
    }

    assert stage5.affinity_plan(topology, 2, "physical") == {
        "source_mask": 0x55,
        "endpoint_masks": [0x1, 0x4],
        "logical_processors_available": 4,
    }
    assert stage5.affinity_plan(topology, 4, "smt") == {
        "source_mask": 0xFF,
        "endpoint_masks": [0x3, 0xC, 0x30, 0xC0],
        "logical_processors_available": 8,
    }


def test_stage5_reads_host_typeperf_csv_without_utf16_bom(tmp_path: Path) -> None:
    stage5 = importlib.import_module("scripts.run_max_throughput_v2_stage5")
    capture = tmp_path / "host.csv"
    capture.write_text(
        '"timestamp","utility","performance","frequency"\n'
        '"one","10.0","180.0","2101"\n'
        '"two","20.0","190.0","2101"\n',
        encoding="ascii",
    )

    result = stage5.read_host_counters(capture)

    assert result["status"] == "MEASURED"
    assert result["processor_utility_percent_median"] == 15.0
    assert result["processor_performance_percent_median"] == 185.0
    assert result["processor_frequency_mhz_median"] == 2101.0


def test_stage5_analysis_matches_authoritative_manifest() -> None:
    manifest = json.loads((EVIDENCE / "manifest.json").read_text(encoding="utf-8"))
    analysis = json.loads((EVIDENCE / "analysis.json").read_text(encoding="utf-8"))
    cells = {
        (cell["affinity_mode"], cell["path"], cell["endpoint_groups"]): cell
        for cell in manifest["cells"]
    }
    physical = cells[("physical", "nbsr", 2)]
    full_host = cells[("smt", "nbsr", 4)]

    assert analysis["physical_best"]["median_gbps"] == physical["median_gbps"]
    assert analysis["full_host_best"]["median_gbps"] == full_host["median_gbps"]
    assert analysis["highest_repeatable_stage5_nbsr_gbps"] == full_host["median_gbps"]
    assert analysis["full_host_gain_over_physical_best_percent"] == (
        full_host["median_gbps"] / physical["median_gbps"] - 1
    ) * 100
    assert manifest["all_valid"] and manifest["all_cleanup_pass"]
    assert manifest["errors"] == manifest["timeouts"] == 0


def test_stage4_placement_description_uses_actual_source_mask() -> None:
    stage4 = importlib.import_module("scripts.run_max_throughput_v2_stage4")

    assert "0xff" in stage4.placement_description(0xFF, [0x3, 0xC])
    assert "0x3, 0xc" in stage4.placement_description(0xFF, [0x3, 0xC])
