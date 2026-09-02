from __future__ import annotations

import importlib


def test_stage2_matrix_is_matched_and_uses_only_approved_groups() -> None:
    stage2 = importlib.import_module("scripts.run_max_throughput_v2_stage2")
    cells = stage2.stage2_cells()

    assert {cell["groups"] for cell in cells} == {1, 2, 4}
    assert {cell["runtime_workers"] for cell in cells} == {1}
    assert all(1 <= cell["streams_per_group"] <= 64 for cell in cells)
    shapes = {}
    for cell in cells:
        key = (
            cell["payload_bytes"], cell["groups"], cell["streams_per_group"],
            cell["outstanding_per_stream"],
        )
        shapes.setdefault(key, set()).add(cell["path"])
    assert all(paths == {"direct", "nbsr"} for paths in shapes.values())


def test_group_records_are_aggregated_without_double_counting_wall_time() -> None:
    stage2 = importlib.import_module("scripts.run_max_throughput_v2_stage2")
    groups = [
        {"completed_operations": 100, "measured_ns": 1_000_000_000, "p50_latency_ns": 10,
         "p95_latency_ns": 20, "p99_latency_ns": 30, "max_outstanding_per_stream_observed": 4},
        {"completed_operations": 110, "measured_ns": 1_010_000_000, "p50_latency_ns": 11,
         "p95_latency_ns": 21, "p99_latency_ns": 31, "max_outstanding_per_stream_observed": 4},
    ]

    aggregate = stage2.aggregate_group_records(
        groups, payload_bytes=1024, streams_per_group=8, outstanding_per_stream=4
    )

    assert aggregate["completed_operations"] == 210
    assert aggregate["measured_ns"] == 1_010_000_000
    assert aggregate["groups"] == 2
    assert aggregate["configured_total_outstanding"] == 64
    assert aggregate["max_observed_total_outstanding"] == 64
    assert len(aggregate["per_group"]) == 2


def test_stage2_classification_keeps_repeatable_peak_separate_from_strict_stable() -> None:
    stage2 = importlib.import_module("scripts.run_max_throughput_v2_stage2")
    cells = [
        {"groups": 1, "median_gbps": 2.0, "throughput_cv": 0.01, "repeat_count": 3,
         "median_p99_latency_ns": 100, "errors": 0, "timeouts": 0, "cleanup_pass": True,
         "achieved_offered_ratio": 1.0},
        {"groups": 2, "median_gbps": 3.5, "throughput_cv": 0.02, "repeat_count": 3,
         "median_p99_latency_ns": 120, "errors": 0, "timeouts": 0, "cleanup_pass": True,
         "achieved_offered_ratio": 1.0},
        {"groups": 4, "median_gbps": 3.6, "throughput_cv": 0.02, "repeat_count": 3,
         "median_p99_latency_ns": 230, "errors": 0, "timeouts": 0, "cleanup_pass": True,
         "achieved_offered_ratio": 1.0},
    ]

    result = stage2.classify_group_scaling(cells)

    assert result["highest_repeatable"]["groups"] == 4
    assert result["highest_strict_stable"]["groups"] == 2
    assert [cell["region"] for cell in result["cells"]] == ["STABLE", "STABLE", "SATURATED"]


def test_process_cleanup_requires_every_owned_resource_and_registry_to_be_zero() -> None:
    stage2 = importlib.import_module("scripts.run_max_throughput_v2_stage2")
    clean = {key: 0 for key in stage2.CLEANUP_FIELDS}
    assert stage2.cleanup_from_diagnostic(clean)
    dirty = dict(clean)
    dirty["application_streams_current_live"] = 1
    assert not stage2.cleanup_from_diagnostic(dirty)


def test_multi_group_validity_uses_per_group_correctness_and_process_cleanup() -> None:
    stage2 = importlib.import_module("scripts.run_max_throughput_v2_stage2")
    records = [
        {
            "completed_operations": 10,
            "errors": 0,
            "missing": 0,
            "duplicates": 0,
            "corrupt": 0,
            "wrong_request": 0,
            # Global lifecycle deltas overlap while independent groups run.
            "application_streams_created_delta": 1,
        },
        {
            "completed_operations": 11,
            "errors": 0,
            "missing": 0,
            "duplicates": 0,
            "corrupt": 0,
            "wrong_request": 0,
            "application_streams_created_delta": -1,
        },
    ]

    assert stage2.validate_group_records(records, process_cleanup_pass=True)
    assert not stage2.validate_group_records(records, process_cleanup_pass=False)
    records[1]["corrupt"] = 1
    assert not stage2.validate_group_records(records, process_cleanup_pass=True)
