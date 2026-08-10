from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import scripts.run_performance_completion as completion
from scripts.run_performance_completion import RunSpec, completion_plan
from scripts.run_performance_load_cell import expected_steady_sample_count


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


def test_fractional_rate_steady_count_uses_total_minus_warmup_boundary() -> None:
    assert expected_steady_sample_count(1265.625, warmup_seconds=60, steady_seconds=600) == 759_374


def test_memory_execution_uses_durable_runner_only(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, object]] = []
    spec = RunSpec("memory", "go-rust", 200, 60, 1_800, 1, 50)
    monkeypatch.setattr(
        completion,
        "run_durable_memory_child",
        lambda command, **options: calls.append(("durable", (command, options))) or {},
    )
    monkeypatch.setattr(
        completion.subprocess,
        "run",
        lambda *args, **kwargs: calls.append(("short", (args, kwargs))),
    )

    completion.execute_spec(spec, tmp_path, timeout_seconds=3_660)

    assert [name for name, _ in calls] == ["durable"]
    _, (_, options) = calls[0]
    assert options["output"] == tmp_path / "memory" / spec.run_id
    assert options["offered_requests"] == round(200 * 1_860)
    assert options["timeout_seconds"] == 3_660
    assert "--durable-events" in calls[0][1][0]


def test_non_memory_execution_keeps_existing_short_path(monkeypatch, tmp_path: Path) -> None:
    calls: list[str] = []
    spec = RunSpec("formal", "direct-quic", 100, 60, 600, 1, 25)
    monkeypatch.setattr(
        completion,
        "run_durable_memory_child",
        lambda *_args, **_kwargs: calls.append("durable"),
    )
    monkeypatch.setattr(
        completion.subprocess,
        "run",
        lambda *args, **kwargs: calls.append("short") or subprocess.CompletedProcess(args, 0),
    )

    completion.execute_spec(spec, tmp_path, timeout_seconds=3_660)

    assert calls == ["short"]


def test_completion_runner_cli_loads_memory_plan_from_repository_root(tmp_path: Path) -> None:
    capacities = tmp_path / "capacities.json"
    capacities.write_text(
        '{"direct-quic":4750,"rust-rust":1687.5,"go-rust":400}\n', encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable, str(Path("scripts/run_performance_completion.py")),
            "--phase", "memory", "--accepted-capacities", str(capacities),
            "--output", str(tmp_path / "evidence"),
        ],
        cwd=Path(__file__).parents[2], capture_output=True, text=True, check=False,
    )

    assert result.returncode == 0, result.stderr
    assert '"run_id": "go-rust-memory-300-75pct-r1"' in result.stdout
