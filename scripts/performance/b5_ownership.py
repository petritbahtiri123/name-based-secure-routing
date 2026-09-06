"""Bounded optional ownership observation; sampled growth is not a leak proof."""

from collections import deque
import json
import os
import statistics

from scripts.performance.b5_stream import _reject_constant, _unique_object
from scripts.performance.post_close_cleanup import FIELDS

CAPACITIES = tuple(f"{name}_retained_capacity" for name in (
    "pending_routes", "channel_registry", "stream_registry", "replay_state", "audit_queue"))
PERIOD = 1_000_000_000


def integer(value):
    return type(value) is int and 0 <= value < 2**64


class OwnershipHistory:
    """At most 60 projected snapshots/role plus fixed counters.

    A three-third monotone median increase after twelve samples aborts as an
    early growth diagnostic. One setup step followed by a plateau does not.
    Cumulative events and high-water marks cannot establish live-resource growth.
    """

    def __init__(self, *, groups, max_samples):
        if groups not in (1, 2, 4) or type(max_samples) is not int or max_samples < 1:
            raise ValueError("invalid ownership bounds")
        self.max_samples = max_samples
        self.roles = {"source", *(f"destination_{i}" for i in range(groups))}
        self.history = {role: deque(maxlen=60) for role in self.roles}
        self.counts = dict.fromkeys(self.roles, 0)
        self.first, self.last, self.max_gap = {}, {}, dict.fromkeys(self.roles, 0)
        self.failed = False

    def retained(self, role):
        return len(self.history[role])

    def accept(self, role, value, received_ns):
        try:
            if self.failed or role not in self.roles:
                raise ValueError("invalid ownership role/state")
            expected = "source" if role == "source" else "destination"
            phases = ("b5_initial", "b5_sample") if role == "source" else ("initial", "sample")
            if (type(value) is not dict or value.get("schema") != "nbsr-rust-ownership-v1"
                    or value.get("event") != "diagnostic" or value.get("role") != expected
                    or value.get("phase") not in phases or not integer(value.get("timestamp_ns"))
                    or not integer(received_ns) or any(not integer(value.get(k)) for k in FIELDS)
                    or any(k in value and not integer(value[k]) for k in CAPACITIES)):
                raise ValueError("invalid ownership snapshot")
            stamp = value["timestamp_ns"]
            if self.counts[role] >= self.max_samples:
                raise ValueError("ownership sample bound exceeded")
            if role in self.last:
                if stamp <= self.last[role]:
                    raise ValueError("ownership clock did not advance")
                self.max_gap[role] = max(self.max_gap[role], stamp - self.last[role])
            else:
                self.first[role] = stamp
            self.last[role] = stamp
            self.counts[role] += 1
            self.history[role].append({key: value[key] for key in (*FIELDS, *CAPACITIES) if key in value})
            rows = list(self.history[role])
            if len(rows) >= 12:
                third = len(rows) // 3
                for key in (*FIELDS, *CAPACITIES):
                    if not all(key in row for row in rows):
                        continue
                    medians = [statistics.median(row[key] for row in part) for part in (
                        rows[:third], rows[third:2 * third], rows[-third:])]
                    if medians[0] < medians[1] < medians[2]:
                        raise ValueError(f"sampled ownership growth: {role}/{key}; not a leak proof")
        except Exception:
            self.failed = True
            raise

    def finish(self, *, duration_ns):
        if self.failed:
            raise ValueError("ownership evidence failed")
        missing = [role for role in self.roles if self.counts[role] < 12]
        if missing:
            raise ValueError(f"missing qualified ownership roles: {sorted(missing)}")
        for role in self.roles:
            if (self.max_gap[role] > 3 * PERIOD
                    or self.last[role] - self.first[role] < duration_ns - 2 * PERIOD):
                raise ValueError(f"insufficient ownership time coverage: {role}")
        return {"classification": "SAMPLED_NO_SUSTAINED_GROWTH", "sample_counts": dict(self.counts),
                "max_snapshot_gap_ns": dict(self.max_gap), "retained_window_per_role": 60,
                "scope": "Process-local sample intervals; cross-process clock alignment and final zero cleanup are separate.",
                "retained_capacity_scope": "Optional fields observed when emitted; not allocator or leak attribution."}


class OwnershipTail:
    """Bounded incremental reader of an original, retained diagnostic file."""

    def __init__(self, path, accept, *, max_line_bytes=262_144):
        self.path, self.accept = path, accept
        self.bound = max_line_bytes
        self.file = None
        self.pending = bytearray()
        self.failed = False

    def poll(self):
        try:
            if self.failed:
                raise ValueError("ownership tail failed")
            if self.file is None:
                try:
                    self.file = self.path.open("rb")
                except FileNotFoundError:
                    return 0
            current, opened = self.path.stat(), os.fstat(self.file.fileno())
            if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
                raise ValueError("ownership file replaced")
            if current.st_size < self.file.tell():
                raise ValueError("ownership file truncated")
            count = 0
            for _ in range(16):
                data = self.file.read(65_536)
                if not data:
                    break
                for index, part in enumerate(data.split(b"\n")):
                    if index:
                        value = json.loads(self.pending.decode("utf-8"), object_pairs_hook=_unique_object,
                                           parse_constant=_reject_constant)
                        self.pending.clear()
                        self.accept(value)
                        count += 1
                    if len(self.pending) + len(part) > self.bound:
                        raise ValueError("ownership line bound exceeded")
                    self.pending.extend(part)
            return count
        except Exception:
            self.failed = True
            raise

    def finish(self):
        self.poll()
        if self.file is None or self.file.tell() != self.path.stat().st_size:
            raise ValueError("missing or unread ownership file")
        if self.pending:
            raise ValueError("partial ownership line at EOF")

    def close(self):
        if self.file is not None:
            self.file.close()
