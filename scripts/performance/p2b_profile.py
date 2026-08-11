"""Frozen P2B load, sharding, and observer-effect rules."""

from __future__ import annotations

import statistics

LOADS = {
    "direct": {50: 2375.0, 90: 4275.0},
    "nbsr": {50: 843.75, 90: 1518.75},
}
MAX_SESSION_OPERATIONS = 8000


def shard_plan(rate: float, duration_seconds: int) -> list[int]:
    remaining = round(rate * duration_seconds)
    shards = []
    while remaining:
        count = min(MAX_SESSION_OPERATIONS, remaining)
        shards.append(count)
        remaining -= count
    return shards


def profile_manifest(path: str, load_percent: int, repeat: int, duration_seconds: int,
                     instrumentation_enabled: bool) -> dict:
    return {
        "schema": "nbsr-p2b-profile-manifest-v1",
        "path": path,
        "load_percent": load_percent,
        "offered_rate": LOADS[path][load_percent],
        "repeat": repeat,
        "profile_seconds": duration_seconds,
        "payload_bytes": 1024,
        "operation": "new-application-stream-lifecycle",
        "connection_model": "persistent-per-shard",
        "service_channel_model": "existing-authorized-per-shard",
        "application_stream_model": "new-per-operation",
        "max_operations_per_session": MAX_SESSION_OPERATIONS,
        "one_outstanding_operation": True,
        "instrumentation_enabled": instrumentation_enabled,
    }


def observer_effect(*, disabled_throughput: list[float], enabled_throughput: list[float],
                    disabled_p99: list[float], enabled_p99: list[float],
                    disabled_errors: int, enabled_errors: int) -> dict:
    throughput_loss = 1 - statistics.median(enabled_throughput) / statistics.median(disabled_throughput)
    p99_growth = statistics.median(enabled_p99) / statistics.median(disabled_p99) - 1
    tolerance = 1e-12
    passed = (throughput_loss <= 0.03 + tolerance and p99_growth <= 0.05 + tolerance
              and enabled_errors <= disabled_errors)
    return {"throughput_degradation": throughput_loss, "p99_degradation": p99_growth,
            "additional_errors": enabled_errors - disabled_errors, "passed": passed}
