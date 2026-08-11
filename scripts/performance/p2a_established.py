"""P2A established-data-plane matrix and validity rules."""

from __future__ import annotations

import statistics
from typing import Any


def build_matrix() -> list[dict[str, int | str]]:
    return [
        {"path": path, "streams": streams, "payload_bytes": payload}
        for payload in (1, 1024, 16384)
        for streams in (1, 8, 64)
        for path in ("direct", "nbsr")
    ]


def coefficient_of_variation(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = statistics.fmean(values)
    return statistics.stdev(values) / mean if mean else float("inf")


def validate_repeat(record: dict[str, Any]) -> bool:
    if int(record.get("completed_operations", 0)) < 1:
        return False
    zero_fields = (
        "errors",
        "missing",
        "duplicates",
        "corrupt",
        "wrong_request",
        "transport_sessions_created_delta",
        "service_channels_created_delta",
        "application_streams_created_delta",
        "replay_entries_delta",
    )
    return all(int(record.get(field, -1)) == 0 for field in zero_fields)
