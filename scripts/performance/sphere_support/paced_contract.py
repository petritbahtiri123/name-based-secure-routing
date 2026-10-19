"""Pure bounded benchmark resource and deadline contracts; no remote calls or workload launch."""

import math

MIB = 1024**2
LEVELS = (1, 2, 4, 8, 16, 32)


def duration(seconds):
    if type(seconds) is not int or seconds not in (20, 300):
        raise ValueError("explicit20s smoke or300s measurement only")
    return seconds


class Deadline:
    def __init__(self, t0, seconds):
        self.t0 = t0
        self.seconds = duration(seconds)
        if not isinstance(t0, (int, float)) or not math.isfinite(t0):
            raise ValueError("monotonic origin")

    def remaining(self, stage, now):
        bounds = (
            {"work": 330, "collection": 370, "finalization": 410, "coordinator": 420, "wrapper": 430}
            if self.seconds == 300
            else {"work": 60, "collection": 80, "finalization": 110, "coordinator": 120, "wrapper": 120}
        )
        if not math.isfinite(now) or now < self.t0:
            raise ValueError("clock")
        remaining = self.t0 + bounds[stage] - now
        if remaining <= 0:
            raise TimeoutError(stage + " cutoff")
        return remaining

    def can_measure(self, now):
        if self.remaining("work", now) < 3 + self.seconds:
            raise TimeoutError("full warmup and measurement cannot fit")


def tls_remaining(remaining, *, endpoint=False):
    if type(remaining) not in (int, float) or not math.isfinite(remaining) or remaining < (420 if endpoint else 450):
        raise ValueError("nonrenewable TLS lease insufficient")


class Guard:
    def __init__(self, *, connections, t0, monitor_progress=True):
        if type(connections) is not int or connections not in LEVELS:
            raise ValueError("unauthorized connection count")
        self.monitor_progress = monitor_progress
        self.n = connections
        self.prior = None
        self.high_since = None
        self.net_streak = 0
        self.last_progress = [t0] * connections
        self.completed = [0] * connections

    def progress(self, pair, total, now):
        if type(pair) is not int or not 0 <= pair < self.n or type(total) is not int or total <= self.completed[pair]:
            raise ValueError("invalid/nonadvancing progress")
        if not math.isfinite(now) or now < self.last_progress[pair]:
            raise ValueError("progress clock")
        self.last_progress[pair] = now
        self.completed[pair] = total

    def sample(self, *, now, memory, tasks, available, disk_free, task_bytes, tx, rx, drops, errors, oom, pids_denied, route):
        if not math.isfinite(now):
            raise ValueError("sample clock")
        if any(
            type(x) is not int or x < 0 for x in [memory, tasks, available, disk_free, task_bytes, tx, rx, drops, errors, oom, pids_denied]
        ):
            raise ValueError("invalid resource sample")
        if available < 2 * 1024**3 or disk_free < 2 * 1024**3 or task_bytes > 256 * MIB:
            raise RuntimeError("remote reserve/budget")
        if tasks > 112 or oom or pids_denied or route != "eth1":
            raise RuntimeError("aggregate task/OOM/route guard")
        if memory > 460 * MIB:
            if self.high_since is None:
                self.high_since = now
            if now - self.high_since >= 5:
                raise RuntimeError("memory above460MiB for5s")
        else:
            self.high_since = None
        if self.prior:
            p = self.prior
            dt = now - p["now"]
            if not 0 < dt <= 2:
                raise RuntimeError("supervision gap")
            if min(tx - p["tx"], rx - p["rx"], drops - p["drops"], errors - p["errors"]) < 0:
                raise RuntimeError("interface counters reset")
            if drops > p["drops"] or errors > p["errors"]:
                raise RuntimeError("interface errors/drops")
            high = max(tx - p["tx"], rx - p["rx"]) * 8 / dt > 100_000_000
            self.net_streak = self.net_streak + 1 if high else 0
            if self.net_streak >= 2:
                raise RuntimeError("network100Mbit/s two samples")
        if self.monitor_progress and any(now - p >= 10 for p in self.last_progress):
            raise RuntimeError("no application progress10s")
        self.prior = {"now": now, "tx": tx, "rx": rx, "drops": drops, "errors": errors}
