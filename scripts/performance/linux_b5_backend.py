"""Explicit per-peer Linux affinity for the shared B5 controller.

This does not qualify its smaps observer or provide an external server claim.
"""

from pathlib import Path
import time

from scripts.performance.linux_b5_reference import wait_exec
from scripts.performance.linux_exit import observe_owned_exit
from scripts.performance.linux_resources import LinuxResourceSampler, sample_linux_process
from scripts.performance.process_cancellation import not_cancelled


class LinuxB5Backend:
    resource_basis = "linux_private_resident"
    scope = "Linux loopback selected guest CPUs; observer qualification pending"

    def __init__(self, environment, *, placement="shared", check_cancelled=not_cancelled):
        cpus = environment.get("selected_cpus")
        if (placement not in ("shared", "split") or environment.get("platform") != "linux"
                or type(cpus) is not list or len(cpus) != (2 if placement == "split" else 1)
                or any(type(cpu) is not int or cpu < 0 for cpu in cpus)
                or len(set(cpus)) != len(cpus) or not environment.get("taskset")):
            raise ValueError("explicit distinct Linux CPUs required for placement")
        self.cpus = list(cpus)
        self.taskset = environment["taskset"]
        self.mask = 1 << cpus[0]
        self.destination_mask = 1 << cpus[-1]
        self.role_cpus = {"source": [cpus[0]], "destination_0": [cpus[-1]]}
        self.check_cancelled = check_cancelled

    def validate(self, cell, plan):
        if (cell["endpoint_groups"] != 1 or plan["source_mask"] != self.mask
                or plan["endpoint_masks"] != [self.destination_mask]
                or plan["logical_processors_available"] != len(self.cpus)):
            raise ValueError("Linux B5 adapter requires exact per-peer placement/group")

    def command(self, argv, *, mask=None):
        mask = self.mask if mask is None else mask
        if mask not in (self.mask, self.destination_mask):
            raise ValueError("Linux command affinity plan mismatch")
        return [self.taskset, "-c", str(mask.bit_length() - 1), *argv]

    def verify_affinity(self, process, mask, binary):
        self.check_cancelled()  # Shared controller has registered this child before calling us.
        if mask not in (self.mask, self.destination_mask):
            raise RuntimeError("Linux affinity plan mismatch")
        wait_exec(process, Path(binary))
        row = sample_linux_process(process.pid, [mask.bit_length() - 1])
        if row["state"] == "Z":
            raise RuntimeError("peer exited before live affinity verification")
        return dict(verified=True, requested_mask=mask, observed_mask=mask,
                    linux_affinity=row["affinity"], start_ticks=row["start_ticks"])

    def sampler(self, processes, *, interval, bound, sink):
        self.check_cancelled()
        return LinuxResourceSampler(processes, self.cpus, interval_seconds=interval,
            max_records=bound, record_sink=sink, terminal_roles=("source",), role_cpus=self.role_cpus)

    def observe_source(self, source):
        self.check_cancelled()
        return observe_owned_exit(source.pid)

    def complete_source(self, source, sampler, deadline_ns):
        while True:
            self.check_cancelled()
            sampler.check_health(require_running=True)
            if any(r["role"] == "source" and r["pid"] == source.pid and r["state"] == "Z"
                   for r in sampler.records_snapshot()):
                break
            if time.monotonic_ns() >= deadline_ns:
                raise RuntimeError("source terminal sampling deadline")
            time.sleep(.01)
        sampler.stop()
        if source.wait(timeout=0) != 0:
            raise RuntimeError("source exit failed")

    def complete_destination(self, server, role, sampler, sink, deadline_ns):
        self.check_cancelled()
        while observe_owned_exit(server.pid) is None:
            self.check_cancelled()
            if time.monotonic_ns() >= deadline_ns:
                raise RuntimeError("destination terminal sampling deadline")
            time.sleep(.01)
        prior = [r for r in sampler.records_snapshot() if r["role"] == role]
        final = sample_linux_process(server.pid, self.role_cpus[role])
        if (not prior or final["state"] != "Z" or final["pid"] != prior[-1]["pid"]
                or final["start_ticks"] != prior[-1]["start_ticks"]
                or final["cpu_ns"] < prior[-1]["cpu_ns"]
                or final["timestamp_ns"] <= prior[-1]["timestamp_ns"]):
            raise RuntimeError("destination terminal identity/counter continuity failed")
        sink({**final, "role": role})
        if server.wait(timeout=0) != 0:
            raise RuntimeError("destination exit failed")
