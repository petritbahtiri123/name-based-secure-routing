from __future__ import annotations

from scripts.run_performance_completion import completion_plan


def test_discovery_plan_uses_independent_bounded_regions() -> None:
    specs = completion_plan("discover", accepted_capacities={})
    by_path = {path: [spec.rate for spec in specs if spec.path == path] for path in ("direct-quic", "rust-rust", "go-rust")}
    assert by_path == {
        "direct-quic": [3_000, 4_000, 4_500, 5_000],
        "rust-rust": [1_000, 1_500, 1_750, 2_000],
        "go-rust": [200, 300, 400],
    }
    assert all(spec.warmup_seconds == 60 and spec.steady_seconds == 600 for spec in specs)


def test_confirmation_plan_requires_three_independent_runs_per_path() -> None:
    accepted = {"direct-quic": 4_000, "rust-rust": 1_500, "go-rust": 300}
    specs = completion_plan("confirm", accepted_capacities=accepted)
    assert len(specs) == 9
    for path, rate in accepted.items():
        path_specs = [spec for spec in specs if spec.path == path]
        assert [spec.run_ordinal for spec in path_specs] == [1, 2, 3]
        assert {spec.rate for spec in path_specs} == {rate}


def test_formal_plan_uses_each_paths_accepted_capacity() -> None:
    accepted = {"direct-quic": 4_000, "rust-rust": 1_500, "go-rust": 300}
    specs = completion_plan("formal", accepted_capacities=accepted)
    assert [(spec.path, spec.percent, spec.rate) for spec in specs] == [
        (path, percent, accepted[path] * percent / 100)
        for path in ("direct-quic", "rust-rust", "go-rust")
        for percent in (25, 50, 75, 90)
    ]


def test_memory_plan_has_six_identically_timed_non_saturated_runs() -> None:
    accepted = {"direct-quic": 4_000, "rust-rust": 1_500, "go-rust": 300}
    specs = completion_plan("memory", accepted_capacities=accepted)
    assert len(specs) == 6
    assert {(spec.path, spec.percent) for spec in specs} == {
        (path, percent) for path in accepted for percent in (50, 75)
    }
    assert all(spec.warmup_seconds == 60 for spec in specs)
    assert all(spec.steady_seconds == 1_800 for spec in specs)
    assert all(spec.sampling_cadence_seconds == 1 for spec in specs)
    assert all(spec.percent != 90 for spec in specs)
