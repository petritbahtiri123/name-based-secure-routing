"""B3 active-resource scaling and lifecycle-cycle analysis."""

from __future__ import annotations

import statistics
from typing import Any


def _slope(points: list[tuple[float, float]]) -> float | None:
    if len(points) < 2:
        return None
    mean_x = statistics.fmean(x for x, _ in points)
    mean_y = statistics.fmean(y for _, y in points)
    denominator = sum((x - mean_x) ** 2 for x, _ in points)
    if denominator == 0:
        return None
    return sum((x - mean_x) * (y - mean_y) for x, y in points) / denominator


def _median_phase(cell: dict[str, Any], phase: str, field: str, role: str = "destination") -> float | None:
    values = [float(item[field]) for item in cell["samples"] if item["phase"] == phase and item["role"] == role]
    return float(statistics.median(values)) if values else None


def analyze_path(path: str, cells: list[dict[str, Any]]) -> dict[str, Any]:
    scaling: dict[str, Any] = {}
    for kind in ("connections", "sessions", "channels", "streams"):
        selected = sorted((cell for cell in cells if cell["kind"] == kind), key=lambda cell: cell["active_count"])
        points = []
        for cell in selected:
            active = _median_phase(cell, "active", "private_bytes")
            idle = _median_phase(cell, "idle", "private_bytes")
            if active is not None and idle is not None:
                points.append((float(cell["active_count"]), active - idle))
        if points:
            scaling[kind] = {
                "counts": [int(x) for x, _ in points],
                "incremental_private_bytes": [y for _, y in points],
                "private_bytes_per_resource": _slope(points),
            }
    cycle_cells = [cell for cell in cells if cell["kind"] == "cycles"]
    cooldown_points: list[tuple[float, float]] = []
    for cell in cycle_cells:
        cycles = sorted({int(item["cycle"]) for item in cell["samples"] if item["phase"] == "cooldown"})
        for cycle in cycles:
            values = [float(item["private_bytes"]) for item in cell["samples"] if item["role"] == "destination" and item["phase"] == "cooldown" and int(item["cycle"]) == cycle]
            if values:
                cooldown_points.append((float(cycle), float(statistics.median(values))))
    cleanup_zero = all(bool(cell.get("cleanup", {}).get("all_zero")) for cell in cells)
    cycle_slope = _slope(cooldown_points)
    lifecycle = "CLEAN"
    if not cleanup_zero or (cycle_slope is not None and cycle_slope > 64 * 1024):
        lifecycle = "RESOURCE-GROWTH"
    same_process_cycles = any(
        cell.get("cycle_mode", "same-process") == "same-process"
        and len({int(item["cycle"]) for item in cell["samples"] if item["phase"] == "cooldown"}) >= 5
        for cell in cycle_cells
    )
    return {
        "path": path,
        "evidence": "PASS" if cells and cooldown_points and same_process_cycles else ("PARTIAL" if cells and cooldown_points else "INCONCLUSIVE"),
        "lifecycle": lifecycle,
        "scaling": scaling,
        "cycles": {"count": len(cooldown_points), "mode": "same-process" if same_process_cycles else "process-isolated", "cooldown_private_slope_bytes_per_cycle": cycle_slope},
        "cleanup_all_zero": cleanup_zero,
    }
