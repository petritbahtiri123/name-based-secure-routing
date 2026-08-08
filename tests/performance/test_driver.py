from __future__ import annotations

from pathlib import Path

import pytest

from scripts.performance.driver import (
    CapacityObservation,
    FormalRunRequirements,
    choose_sustainable_capacity,
    ensure_release_binary,
    open_loop_deadlines_ns,
)


def observation(path: str, rate: float, **changes: object) -> CapacityObservation:
    values: dict[str, object] = {
        "path": path,
        "offered_rate": rate,
        "success_rate": 0.999,
        "unexpected_rejections": 0,
        "resource_limit_errors": 0,
        "destination_cpu_percent": 80.0,
        "memory_slope_bytes_per_second": 0.0,
        "p99_ns": 1_500,
        "idle_p99_ns": 1_000,
    }
    values.update(changes)
    return CapacityObservation(**values)  # type: ignore[arg-type]


def test_debug_binary_cannot_be_measured(tmp_path: Path) -> None:
    binary = tmp_path / "debug" / "peer.exe"
    binary.parent.mkdir()
    binary.write_bytes(b"MZ")
    with pytest.raises(ValueError, match="release binary"):
        ensure_release_binary(binary)


def test_open_loop_deadlines_use_absolute_schedule() -> None:
    assert open_loop_deadlines_ns(start_ns=1_000_000_000, rate_per_second=4, count=4) == [
        1_000_000_000,
        1_250_000_000,
        1_500_000_000,
        1_750_000_000,
    ]


def test_capacity_is_chosen_independently_for_each_path() -> None:
    observations = [
        observation("direct-quic", 1000),
        observation("direct-quic", 1200, destination_cpu_percent=90),
        observation("rust-rust", 700),
        observation("rust-rust", 900, success_rate=0.998),
        observation("go-rust", 500),
        observation("go-rust", 600, p99_ns=2_001),
    ]
    assert choose_sustainable_capacity(observations) == {
        "direct-quic": 1000,
        "rust-rust": 700,
        "go-rust": 500,
    }


def test_any_protocol_or_resource_error_disqualifies_capacity() -> None:
    with pytest.raises(ValueError, match="no sustainable capacity"):
        choose_sustainable_capacity([observation("go-rust", 100, unexpected_rejections=1)])


def test_formal_capacity_window_cannot_be_silently_shortened() -> None:
    requirements = FormalRunRequirements()
    requirements.validate_capacity_window(warmup_seconds=60, steady_state_seconds=600)
    with pytest.raises(ValueError, match="60 second warm-up"):
        requirements.validate_capacity_window(warmup_seconds=59, steady_state_seconds=600)
    with pytest.raises(ValueError, match="600 second steady-state"):
        requirements.validate_capacity_window(warmup_seconds=60, steady_state_seconds=599)


def test_requested_concurrency_is_not_silently_clamped() -> None:
    requirements = FormalRunRequirements()
    requirements.validate_concurrency(requested=64, active=64)
    with pytest.raises(ValueError, match="requested concurrency 64, active 32"):
        requirements.validate_concurrency(requested=64, active=32)
