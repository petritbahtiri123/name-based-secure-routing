"""Declared sequential diagnostic workload bounds; transport timers are unchanged."""

from scripts.performance.linux_b5_ceiling import require

CYCLE_COUNTS = (1, 2, 4, 8, 10, 16, 25, 50, 100)


def cycle_bounds(cycles):
    require(type(cycles) is int and cycles in CYCLE_COUNTS, 'invalid cycle count')
    return dict(controller_seconds=120 if cycles <= 16 else 120 + cycles * 4)
