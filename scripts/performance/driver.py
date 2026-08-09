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


@dataclass(frozen=True)
class CapacityConfirmation:
    run_id: str
    observation: CapacityObservation

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("capacity confirmation run ID cannot be empty")


@dataclass(frozen=True)
class OpenLoopIssue:
    scheduled_ns: int
    started_ns: int
    completed_ns: int
    success: bool
    error_type: str | None

    def __post_init__(self) -> None:
        if self.started_ns < self.scheduled_ns or self.completed_ns < self.started_ns:
            raise ValueError("open-loop timestamps are not monotonic")
        if self.success == (self.error_type is not None):
            raise ValueError("open-loop success and error type disagree")


@dataclass(frozen=True)
class OpenLoopSummary:
    offered_rate: float
    achieved_rate: float
    offered_requests: int
    successful_requests: int
    failed_requests: int
    late_requests: int
    max_start_lateness_ns: int


def summarize_open_loop_issues(
    issues: list[OpenLoopIssue],
    *,
    offered_rate: float,
    window_seconds: float,
    expected_requests: int | None = None,
) -> OpenLoopSummary:
    if offered_rate <= 0 or window_seconds <= 0:
        raise ValueError("offered rate and window must be positive")
    expected = round(offered_rate * window_seconds) if expected_requests is None else expected_requests
    if len(issues) != expected:
        raise ValueError(f"offered request count {expected}, observed {len(issues)}")
    successful = sum(issue.success for issue in issues)
    lateness = [issue.started_ns - issue.scheduled_ns for issue in issues]
    return OpenLoopSummary(
        offered_rate=offered_rate,
        achieved_rate=successful / window_seconds,
        offered_requests=expected,
        successful_requests=successful,
        failed_requests=expected - successful,
        late_requests=sum(value > 0 for value in lateness),
        max_start_lateness_ns=max(lateness, default=0),
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
    if not 1 <= services_per_session <= 32:
        raise ValueError("services per session must be in 1..32")
    full, remainder = divmod(samples, services_per_session)
    return (services_per_session,) * full + ((remainder,) if remainder else ())


def concurrency_distribution(*, requested: int, services: int, max_per_service: int = 64) -> tuple[int, ...]:
    if services < 1 or services > 20:
        raise ValueError("services must be in 1..20")
    if requested < services:
        raise ValueError("requested concurrency must cover every service")
    configured_limit = services * max_per_service
    if requested > configured_limit:
        raise ValueError(f"requested concurrency {requested} exceeds configured limit {configured_limit}")
    quotient, remainder = divmod(requested, services)
    return tuple(quotient + (1 if index < remainder else 0) for index in range(services))


def progressive_counts(*, maximum: int) -> tuple[int, ...]:
    if maximum < 1:
        raise ValueError("maximum must be positive")
    values: list[int] = []
    current = 1
    while current < maximum:
        values.append(current)
        current *= 2
    if not values or values[-1] != maximum:
        values.append(maximum)
    return tuple(values)


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


def accept_confirmed_capacity(
    confirmations: list[CapacityConfirmation], *, required_runs: int = 3,
) -> dict[str, float]:
    if required_runs < 3:
        raise ValueError("capacity acceptance requires at least 3 confirmations")
    run_ids = [confirmation.run_id for confirmation in confirmations]
    if len(run_ids) != len(set(run_ids)):
        raise ValueError("capacity confirmation run IDs must be unique")
    groups: dict[tuple[str, float], list[CapacityConfirmation]] = {}
    for confirmation in confirmations:
        observation = confirmation.observation
        groups.setdefault((observation.path, observation.offered_rate), []).append(confirmation)
    paths = {path for path, _ in groups}
    accepted: dict[str, float] = {}
    errors: dict[str, str] = {}
    for path in sorted(paths):
        for (_, rate), group in sorted(
            ((key, value) for key, value in groups.items() if key[0] == path),
            key=lambda item: item[0][1],
            reverse=True,
        ):
            if len(group) < required_runs:
                errors[path] = f"capacity {path} at {rate:g} requires at least {required_runs} independent confirmations"
                continue
            failed = next((item for item in group if not item.observation.sustainable()), None)
            if failed is not None:
                errors[path] = f"confirmation {failed.run_id} failed frozen criteria"
                continue
            accepted[path] = rate
            break
        if path not in accepted:
            raise ValueError(errors[path])
    return accepted


def formal_load_rate(path: str, percent: int, accepted_capacities: dict[str, float]) -> float:
    if percent not in {25, 50, 75, 90}:
        raise ValueError("formal load percent must be one of 25, 50, 75, 90")
    try:
        capacity = accepted_capacities[path]
    except KeyError as error:
        raise ValueError(f"accepted capacity missing for {path}") from error
    return capacity * percent / 100


def validate_formal_load_result(*, percent: int, observation: CapacityObservation) -> None:
    if percent not in {25, 50, 75, 90}:
        raise ValueError("formal load percent must be one of 25, 50, 75, 90")
    if not observation.sustainable():
        if percent == 90:
            raise ValueError(f"capacity re-evaluation required for {observation.path}")
        raise ValueError(f"formal {percent}% load failed frozen criteria for {observation.path}")
