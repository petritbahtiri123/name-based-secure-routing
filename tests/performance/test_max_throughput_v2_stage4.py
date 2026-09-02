from __future__ import annotations

import importlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence" / "performance" / "v2" / "max-throughput-stage4-87466238276a"


def test_stage4_matrix_is_matched_and_bounded() -> None:
    stage4 = importlib.import_module("scripts.run_max_throughput_v2_stage4")
    cells = stage4.stage4_cells()

    assert len(cells) == 6
    assert {cell["path"] for cell in cells} == {"direct", "nbsr"}
    assert {cell["endpoint_groups"] for cell in cells} == {1, 2, 4}
    assert all(cell["payload_bytes"] == 16384 for cell in cells)
    assert all(cell["streams_per_group"] == 1 for cell in cells)
    assert all(cell["outstanding_per_stream"] == 4 for cell in cells)
    assert all(cell["runtime_workers"] == 1 for cell in cells)


def test_stage4_endpoint_masks_use_distinct_verified_physical_cores() -> None:
    stage4 = importlib.import_module("scripts.run_max_throughput_v2_stage4")
    topology = {
        "verified": True,
        "cores": [
            {"logical_mask": 0x3},
            {"logical_mask": 0xC},
            {"logical_mask": 0x30},
            {"logical_mask": 0xC0},
        ],
    }

    assert stage4.endpoint_masks(topology, 4) == [0x1, 0x4, 0x10, 0x40]


def test_stage4_analysis_matches_preserved_authoritative_manifest() -> None:
    manifest = json.loads((EVIDENCE / "manifest.json").read_text(encoding="utf-8"))
    analysis = json.loads((EVIDENCE / "analysis.json").read_text(encoding="utf-8"))
    cells = {(cell["path"], cell["endpoint_groups"]): cell for cell in manifest["cells"]}

    nbsr_one = cells[("nbsr", 1)]["median_gbps"]
    nbsr_two = cells[("nbsr", 2)]["median_gbps"]
    nbsr_four = cells[("nbsr", 4)]["median_gbps"]
    assert analysis["highest_measured_median_nbsr_gbps"] == nbsr_two
    assert analysis["scaling"]["nbsr_1_to_2_percent"] == (nbsr_two / nbsr_one - 1) * 100
    assert analysis["scaling"]["nbsr_2_to_4_percent"] == (nbsr_four / nbsr_two - 1) * 100
    assert manifest["all_valid"] is True
    assert manifest["all_cleanup_pass"] is True
    assert manifest["errors"] == 0
    assert manifest["timeouts"] == 0
