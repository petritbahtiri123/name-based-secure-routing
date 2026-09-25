"""Opt-in one-Hz lifecycle memory diagnostics; no performance attribution."""

import json
import time

from scripts.performance.linux_b5_ceiling import require
from scripts.performance.linux_native_cycle_limits import cycle_bounds
from scripts.performance.linux_resources import sample_linux_process

FIELDS = ("rss_bytes", "pss_bytes", "private_resident_bytes", "private_hugetlb_bytes")


def verify_memory(root, *, pid, start_ticks, cpus, cycles, lifetime=None):
    cap = (120 if cycles is None else cycle_bounds(cycles)["controller_seconds"]) + 1
    last = None
    measured = []
    count = 0
    with (root / "memory.ndjson").open("rb") as stream:
        while wire := stream.readline(65537):
            count += 1
            require(count <= cap and len(wire) <= 65536 and wire.endswith(b"\n"), "memory record bound exceeded")
            row = json.loads(wire)
            require(isinstance(row, dict) and set(row) == {"capture_started_ns", "capture_finished_ns", "value"}, "invalid memory record")
            start, end, value = row["capture_started_ns"], row["capture_finished_ns"], row["value"]
            require(
                type(start) is int and type(end) is int and 0 <= start <= end and isinstance(value, dict), "invalid memory capture interval"
            )
            require(
                type(value.get("pid")) is int
                and value["pid"] == pid
                and type(value.get("start_ticks")) is int
                and value["start_ticks"] == start_ticks
                and value.get("affinity") == cpus
                and all(type(cpu) is int for cpu in value["affinity"]),
                "memory process identity/affinity changed",
            )
            require(
                type(value.get("timestamp_ns")) is int
                and start <= value["timestamp_ns"] <= end
                and type(value.get("cpu_ns")) is int
                and value["cpu_ns"] >= 0
                and value.get("memory_basis") == "linux_smaps_rollup",
                "invalid memory provenance",
            )
            require(
                last is None
                or (
                    start >= last["capture_started_ns"] + 1_000_000_000
                    and start >= last["capture_finished_ns"]
                    and value["cpu_ns"] >= last["value"]["cpu_ns"]
                    and last["value"]["state"] != "Z"
                ),
                "memory rate/order regression",
            )
            if lifetime is not None:
                first, terminal = lifetime
                require(
                    start >= first["timestamp_ns"] and first["cpu_ns"] <= value["cpu_ns"] <= terminal["cpu_ns"],
                    "memory outside owned process lifetime/CPU",
                )
                require(value.get("state") == "Z" or end <= terminal["timestamp_ns"], "live memory after terminal sample")
                require(value.get("state") != "Z" or value["cpu_ns"] == terminal["cpu_ns"], "terminal memory CPU mismatch")
            if value.get("state") == "Z":
                require(
                    value.get("memory_state") == "UNAVAILABLE_ZOMBIE" and all(key in value and value[key] is None for key in FIELDS),
                    "invented terminal memory",
                )
            else:
                require(
                    value.get("state") in ("R", "S", "D", "T", "t", "I")
                    and value.get("memory_state") == "MEASURED"
                    and all(type(value.get(key)) is int and value[key] >= 0 for key in FIELDS),
                    "invalid live memory",
                )
                require(
                    value["pss_bytes"] <= value["rss_bytes"] and value["private_resident_bytes"] <= value["rss_bytes"],
                    "private/PSS exceeds resident memory",
                )
                measured.append(value)
            last = row
    require(measured, "no measured live memory")
    return dict(
        status="MEASURED_DIAGNOSTIC_MEMORY",
        measured_samples=len(measured),
        records=count,
        memory_basis="linux_smaps_rollup",
        observer_neutrality="NOT_ESTABLISHED",
        last_live={key: measured[-1][key] for key in FIELDS},
    )


class CycleMemoryObserver:
    result_key = "cycle_memory"

    def __init__(self, root, *, pid, start_ticks, cpus, cycles, sample=sample_linux_process, clock=time.monotonic_ns):
        self.root, self.pid, self.epoch, self.cpus, self.cycles = root, pid, start_ticks, cpus, cycles
        self.sample, self.clock = sample, clock
        self.cap = (120 if cycles is None else cycle_bounds(cycles)["controller_seconds"]) + 1
        self.next_sample = 0
        self.count = 0
        self.stopped = False

    def __enter__(self):
        self.stream = (self.root / "memory.ndjson").open("xb")
        return self

    def __exit__(self, *args):
        self.stream.close()

    def poll(self):
        if self.stopped:
            return
        start = self.clock()
        if start < self.next_sample:
            return
        require(self.count < self.cap, "memory record bound exceeded")
        value = self.sample(self.pid, self.cpus)
        require(value["pid"] == self.pid and value["start_ticks"] == self.epoch, "memory process epoch changed")
        row = dict(capture_started_ns=start, capture_finished_ns=self.clock(), value=value)
        self.stream.write((json.dumps(row, allow_nan=False) + "\n").encode())
        self.stream.flush()
        self.count += 1
        self.next_sample = start + 1_000_000_000
        if value["state"] == "Z":
            self.stopped = True

    def stop(self):
        self.stopped = True

    def finish(self, exit_code):
        require(self.stopped and exit_code == 0, "memory observer requires successful owned exit")
        self.stream.flush()
        with (self.root / "resources.ndjson").open() as stream:
            first = last = json.loads(next(stream))
            for line in stream:
                last = json.loads(line)
        require(last["state"] == "Z", "terminal owned resource sample required")
        return verify_memory(self.root, pid=self.pid, start_ticks=self.epoch, cpus=self.cpus, cycles=self.cycles, lifetime=(first, last))
