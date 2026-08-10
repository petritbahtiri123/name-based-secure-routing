from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.verify_performance_evidence import verify_evidence
from scripts.performance.memory_closure import (
    analyze_go_runtime,
    analyze_resource_records,
    build_memory_closure,
    classify_completion_paths,
    verify_source_bindings,
    write_source_bindings,
)


def test_completion_classification_requires_eligible_go_runs() -> None:
    conclusions = classify_completion_paths(
        direct_status="PASS",
        rust_status="INCONCLUSIVE",
        go_runs=[
            {"authoritative_run": True, "authoritative_pass_eligible": False},
            {"authoritative_run": True, "authoritative_pass_eligible": False},
        ],
    )

    assert conclusions == {
        "direct-quic": "PASS",
        "rust-rust": "INCONCLUSIVE",
        "go-rust": "INCONCLUSIVE",
        "baseline": "PARTIAL_BASELINE",
    }


def test_source_bindings_cover_files_and_detect_mutation(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "raw.ndjson").write_text('{"sample_id":0}\n', encoding="utf-8")
    (source / "terminal.json").write_text('{"state":"complete"}\n', encoding="utf-8")
    destination = tmp_path / "bindings.json"

    write_source_bindings(tmp_path, destination, [source])
    binding = json.loads(destination.read_text(encoding="utf-8"))
    assert [item["path"] for item in binding["files"]] == [
        "source/raw.ndjson",
        "source/terminal.json",
    ]
    assert verify_source_bindings(tmp_path, destination) == 2

    (source / "raw.ndjson").write_text('{"sample_id":1}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="source binding mismatch"):
        verify_source_bindings(tmp_path, destination)


def test_resource_analysis_reports_three_windows_and_bytes_per_request() -> None:
    records = [
        {
            "role": "destination", "phase": "steady", "timestamp_ns": second * 1_000_000_000,
            "working_set_bytes": 100 + second * 10, "private_bytes": 80 + second * 5,
            "peak_working_set_bytes": 100 + second * 10, "processed_requests": second * 100,
            "queue_depth": second, "active_concurrency": 1,
        }
        for second in range(8)
    ]

    result = analyze_resource_records(records, role="destination")
    assert result["samples"] == 8
    assert result["working_set"]["overall"]["slope_bytes_per_second"] == pytest.approx(10)
    assert result["working_set"]["second_half"]["r_squared"] == pytest.approx(1)
    assert result["working_set"]["final_quarter"]["lower_95"] == pytest.approx(10)
    assert result["private_bytes"]["overall"]["slope_bytes_per_second"] == pytest.approx(5)
    assert result["processed_request_delta"] == 700
    assert result["working_set_bytes_per_request"] == pytest.approx(0.1)
    assert result["backlog"]["start"] == 0
    assert result["backlog"]["end"] == 7


def test_go_runtime_analysis_uses_cumulative_deltas_without_claiming_per_gc_max() -> None:
    records = [
        {
            "processed_requests": 100, "heap_alloc_bytes": 20, "heap_sys_bytes": 40,
            "heap_idle_bytes": 10, "heap_inuse_bytes": 30, "heap_released_bytes": 5,
            "num_gc": 2, "total_alloc_bytes": 1000, "mallocs": 100, "frees": 50,
            "total_gc_pause_ns": 7,
        },
        {
            "processed_requests": 200, "heap_alloc_bytes": 25, "heap_sys_bytes": 45,
            "heap_idle_bytes": 12, "heap_inuse_bytes": 33, "heap_released_bytes": 6,
            "num_gc": 4, "total_alloc_bytes": 1600, "mallocs": 180, "frees": 110,
            "total_gc_pause_ns": 12,
        },
        {
            "processed_requests": 200, "heap_alloc_bytes": 24, "heap_sys_bytes": 45,
            "heap_idle_bytes": 13, "heap_inuse_bytes": 32, "heap_released_bytes": 7,
            "num_gc": 5, "total_alloc_bytes": 1700, "mallocs": 190, "frees": 120,
            "total_gc_pause_ns": 20,
        },
    ]

    result = analyze_go_runtime(records)
    assert result["processed_request_delta"] == 100
    assert result["num_gc_delta"] == 3
    assert result["total_alloc_delta_bytes"] == 700
    assert result["total_gc_pause_delta_ns"] == 13
    assert result["recent_observed_interval_pause_ns"] == 8
    assert result["max_observed_interval_pause_ns"] == 8
    assert result["per_gc_max_pause_ns"] is None


def test_real_retained_evidence_builds_partial_additive_closure(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    output = tmp_path / "memory-closure"

    result = build_memory_closure(repo, output)

    assert result["classification"] == {
        "direct-quic": "INCONCLUSIVE",
        "rust-rust": "INCONCLUSIVE",
        "go-rust": "INCONCLUSIVE",
        "baseline": "PARTIAL_BASELINE",
    }
    assert set(result["runs"]) == {
        "direct-50", "direct-68", "rust-50", "rust-75", "go-50", "go-75",
    }
    assert (output / "manifest.json").is_file()
    assert (output / "checksums.json").is_file()
    assert (output / "source-bindings.json").is_file()
    assert (output / "reports/memory-completion.md").is_file()
    assert not list(output.rglob("*.ndjson"))
    files, raw_records = verify_evidence(output)
    assert files == 5
    assert raw_records == 0

    completed = subprocess.run(
        [sys.executable, "scripts/verify_performance_evidence.py", str(output)],
        cwd=repo, capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "PASS (5 files, 0 raw samples)" in completed.stdout
