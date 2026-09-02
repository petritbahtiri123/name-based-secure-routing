from __future__ import annotations

import importlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
CAPTURE = ROOT / "scripts" / "capture_max_throughput_v2_stage3.ps1"
EVIDENCE = ROOT / "evidence" / "performance" / "v2" / "max-throughput-stage3-424dbe067206"


def test_stage3_profile_cells_are_exactly_matched_and_bounded() -> None:
    stage3 = importlib.import_module("scripts.run_max_throughput_v2_stage3_profile")
    cells = stage3.profile_cells()
    assert len(cells) == 6
    assert {cell["path"] for cell in cells} == {"direct", "nbsr"}
    assert {cell["groups"] for cell in cells} == {1, 2, 4}
    assert all(cell["payload_bytes"] == 16384 for cell in cells)
    assert all(cell["streams_per_group"] == 1 for cell in cells)
    assert all(cell["outstanding_per_stream"] == 4 for cell in cells)
    assert all(cell["runtime_workers"] == 1 for cell in cells)


def test_stage3_capture_is_elevated_fail_closed_and_exports_required_views() -> None:
    source = CAPTURE.read_text(encoding="utf-8")
    assert "MANUAL_ELEVATION_REQUIRED" in source
    assert "PROC_THREAD+LOADER+PROFILE+CSWITCH+DISPATCHER" in source
    assert "Profile+CSwitch+ReadyThread" in source
    assert '"-MaxBuffers", "768"' in source
    assert "cpu-profile-detail.txt" in source
    assert "cswitch-process-thread.txt" in source
    assert "readythread.txt" in source
    assert "thread-activity.txt" in source
    assert "process-thread.txt" in source
    assert "profile-overhead.json" in source
    assert "TRACE_INTEGRITY_FAILED" in source


def test_stage3_capture_script_parses_as_powershell() -> None:
    command = (
        "$errors = $null; "
        "[void][System.Management.Automation.Language.Parser]::ParseFile("
        f"'{CAPTURE}', [ref]$null, [ref]$errors); "
        "if ($errors.Count) { $errors | ForEach-Object { Write-Error $_ }; exit 1 }"
    )
    completed = subprocess.run(
        ["pwsh", "-NoProfile", "-Command", command],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_stage3_analysis_matches_preserved_control_and_profiled_measurements() -> None:
    analysis = json.loads((EVIDENCE / "analysis.json").read_text(encoding="utf-8"))
    control = json.loads((EVIDENCE / "raw" / "control-manifest.json").read_text(encoding="utf-8"))
    profiled = json.loads((EVIDENCE / "raw" / "profiled-manifest.json").read_text(encoding="utf-8"))
    overhead = json.loads((EVIDENCE / "raw" / "profile-overhead.json").read_text(encoding="utf-8-sig"))

    for cell in analysis["cells"]:
        key = (cell["path"], cell["groups"])
        control_cell = next(record for record in control["records"] if (record["path"], record["groups"]) == key)
        profiled_cell = next(record for record in profiled["records"] if (record["path"], record["groups"]) == key)
        overhead_cell = next(record for record in overhead if (record["path"], record["groups"]) == key)
        assert cell["control_gbps"] == control_cell["aggregate_application_gbps"]
        assert cell["control_destination_cores"] == control_cell["resources"]["roles"]["destination"]["effective_cores"]
        assert cell["control_p99_ns"] == control_cell["p99_latency_ns"]
        assert cell["profiled_gbps"] == profiled_cell["aggregate_application_gbps"]
        assert cell["profile_overhead_fraction"] == overhead_cell["throughput_overhead_fraction"]

    assert control["all_valid"] and control["all_cleanup_pass"]
    assert profiled["all_valid"] and profiled["all_cleanup_pass"]
