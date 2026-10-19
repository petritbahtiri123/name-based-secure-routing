"""Explicit diagnostic workload budgets; never reference or soak qualification."""
from scripts.performance.linux_b5_ceiling import require


def bounds(seconds=None):
    if type(seconds) is int and seconds in (20, 300):
        return dict(duration=seconds, controller_seconds=seconds + 30 if seconds == 300 else 60,
                    progress=1024, resources=850 if seconds == 300 else 250)
    require(seconds is None or type(seconds) is int and seconds in (60, 3600, 7200),
            'diagnostic duration must be explicit 60, 3600 or 7200 seconds')
    if seconds is None:
        return dict(duration=20, controller_seconds=120, progress=1024, resources=250)
    return dict(duration=seconds, controller_seconds=seconds + 120,
                progress=1024 + seconds // 5, resources=250 + seconds * 2)
