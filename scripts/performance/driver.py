from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FormalRunRequirements:
    warmup_seconds: int = 60
    steady_state_seconds: int = 600

    def validate_capacity_window(self, *, warmup_seconds: int, steady_state_seconds: int) -> None:
        if warmup_seconds < self.warmup_seconds:
            raise ValueError(f"formal capacity requires a {self.warmup_seconds} second warm-up")
        if steady_state_seconds < self.steady_state_seconds:
            raise ValueError(f"formal capacity requires a {self.steady_state_seconds} second steady-state window")

    def validate_concurrency(self, *, requested: int, active: int) -> None:
        if requested < 1 or active != requested:
            raise ValueError(f"requested concurrency {requested}, active {active}")


@dataclass(frozen=True)
class CapacityObservation:
    path: str
    offered_rate: float
    success_rate: float
    unexpected_rejections: int
    resource_limit_errors: int
    destination_cpu_percent: float
    memory_slope_bytes_per_second: float
    p99_ns: int
    idle_p99_ns: int

    def sustainable(self) -> bool:
        return (
            self.success_rate >= 0.999
            and self.unexpected_rejections == 0
            and self.resource_limit_errors == 0
            and self.destination_cpu_percent <= 85.0
            and self.memory_slope_bytes_per_second <= 0.0
            and self.p99_ns <= 2 * self.idle_p99_ns
        )


def ensure_release_binary(path: Path) -> Path:
    if not path.is_file() or "release" not in {part.lower() for part in path.parts}:
        raise ValueError(f"not a release binary: {path}")
    return path.resolve()


def open_loop_deadlines_ns(*, start_ns: int, rate_per_second: float, count: int) -> list[int]:
    if rate_per_second <= 0 or count < 0:
        raise ValueError("rate must be positive and count non-negative")
    interval = 1_000_000_000 / rate_per_second
    return [start_ns + round(index * interval) for index in range(count)]


def lifecycle_batch_plan(*, samples: int, services_per_session: int = 20) -> tuple[int, ...]:
    if samples < 1:
        raise ValueError("samples must be positive")
    if not 1 <= services_per_session <= 20:
        raise ValueError("services per session must be in 1..20")
    full, remainder = divmod(samples, services_per_session)
    return (services_per_session,) * full + ((remainder,) if remainder else ())


def choose_sustainable_capacity(
    observations: list[CapacityObservation],
) -> dict[str, float]:
    paths = {observation.path for observation in observations}
    result: dict[str, float] = {}
    for path in sorted(paths):
        accepted = [observation.offered_rate for observation in observations if observation.path == path and observation.sustainable()]
        if not accepted:
            raise ValueError(f"no sustainable capacity for {path}")
        result[path] = max(accepted)
    return result
