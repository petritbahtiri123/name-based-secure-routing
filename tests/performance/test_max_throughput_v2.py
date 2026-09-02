from __future__ import annotations

import importlib


def test_stage1_matrix_is_matched_bounded_and_single_worker() -> None:
    sweep = importlib.import_module("scripts.run_max_throughput_v2")
    cells = sweep.stage1_cells()

    assert {cell["payload_bytes"] for cell in cells} == {1024, 16384}
    assert {cell["streams"] for cell in cells} == {1, 2, 4, 8, 16, 32, 64}
    assert {cell["outstanding_per_stream"] for cell in cells} == {1, 2, 4, 8, 16}
    assert {cell["runtime_workers"] for cell in cells} == {1}
    assert max(cell["streams"] for cell in cells) == 64

    shapes = {}
    for cell in cells:
        key = (cell["payload_bytes"], cell["streams"], cell["outstanding_per_stream"])
        shapes.setdefault(key, set()).add(cell["path"])
    assert all(paths == {"direct", "nbsr"} for paths in shapes.values())


def test_repeat_target_extends_only_when_cv_exceeds_five_percent() -> None:
    sweep = importlib.import_module("scripts.run_max_throughput_v2")

    assert sweep.repeat_target([2.00, 2.01, 1.99]) == 3
    assert sweep.repeat_target([2.00, 2.20, 1.80]) == 5
    assert sweep.repeat_target([2.00, 2.20, 1.80, 2.10, 1.90]) == 5


def test_midpoint_refinement_returns_unmeasured_geometric_midpoint() -> None:
    sweep = importlib.import_module("scripts.run_max_throughput_v2")

    assert sweep.midpoint_refinement(8, 32, measured={8, 32}) == 16
    assert sweep.midpoint_refinement(8, 16, measured={8, 16}) is None


def _cell(*, load: int, gbps: float, p99: float, achieved: float = 1.0,
          cv: float = 0.01, errors: int = 0, timeouts: int = 0,
          cleanup: bool = True, backlog_drained: bool = True) -> dict:
    return {
        "load": load,
        "median_gbps": gbps,
        "median_p99_latency_ns": p99,
        "achieved_offered_ratio": achieved,
        "throughput_cv": cv,
        "errors": errors,
        "timeouts": timeouts,
        "cleanup_pass": cleanup,
        "backlog_drained": backlog_drained,
        "repeat_count": 3,
    }


def test_classification_and_stable_ceiling_follow_common_saturation_rules() -> None:
    sweep = importlib.import_module("scripts.run_max_throughput_v2")
    cells = [
        _cell(load=1, gbps=1.00, p99=100),
        _cell(load=2, gbps=1.80, p99=120),
        _cell(load=4, gbps=1.65, p99=140),
        _cell(load=8, gbps=1.20, p99=220, achieved=0.88),
    ]

    result = sweep.classify_regions(cells)

    assert [cell["region"] for cell in result["cells"]] == [
        "STABLE", "STABLE", "DEGRADED", "SATURATED"
    ]
    assert result["stable_ceiling"]["load"] == 2
    assert result["first_degraded"]["load"] == 4
    assert result["first_saturated"]["load"] == 8


def test_errors_or_cleanup_failure_can_never_be_stable() -> None:
    sweep = importlib.import_module("scripts.run_max_throughput_v2")
    cells = [
        _cell(load=1, gbps=1.0, p99=100),
        _cell(load=2, gbps=1.1, p99=105, errors=1),
        _cell(load=4, gbps=1.2, p99=110, cleanup=False),
    ]

    result = sweep.classify_regions(cells)

    assert result["cells"][1]["region"] == "SATURATED"
    assert result["cells"][2]["region"] == "SATURATED"
    assert result["stable_ceiling"]["load"] == 1
