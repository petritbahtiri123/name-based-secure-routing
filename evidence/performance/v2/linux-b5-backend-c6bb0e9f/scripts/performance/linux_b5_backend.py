"""Single-core Linux lifecycle adapter for the shared B5 controller.

This does not qualify its smaps observer or provide an external server claim.
"""

from pathlib import Path
import time

from scripts.performance.linux_b5_reference import wait_exec
from scripts.performance.linux_exit import observe_owned_exit
from scripts.performance.linux_resources import LinuxResourceSampler, sample_linux_process


class LinuxB5Backend:
    resource_basis = "linux_private_resident"
    scope = "Linux loopback shared physical-core pool; observer qualification pending"

    def __init__(self, environment):
        cpus = environment.get("selected_cpus")
        if (environment.get("platform") != "linux" or type(cpus) is not list or len(cpus) != 1
                or type(cpus[0]) is not int or cpus[0] < 0 or not environment.get("taskset")):
            raise ValueError("one explicitly selected Linux CPU required")
        self.cpus = list(cpus)
        self.taskset = environment["taskset"]
        self.mask = 1 << cpus[0]

    def validate(self, cell, plan):
        if (cell["endpoint_groups"] != 1 or plan["source_mask"] != self.mask
                or plan["endpoint_masks"] != [self.mask] or plan["logical_processors_available"] != 1):
            raise ValueError("Linux B5 adapter requires one shared selected core/group")

    def command(self, argv):
        return [self.taskset, "-c", str(self.cpus[0]), *argv]

    def verify_affinity(self, process, mask, binary):
        if mask != self.mask:
            raise RuntimeError("Linux affinity plan mismatch")
        wait_exec(process, Path(binary))
        row = sample_linux_process(process.pid, self.cpus)
        if row["state"] == "Z":
            raise RuntimeError("peer exited before live affinity verification")
        return dict(verified=True, requested_mask=mask, observed_mask=mask,
                    linux_affinity=row["affinity"], start_ticks=row["start_ticks"])

    def sampler(self, processes, *, interval, bound, sink):
        return LinuxResourceSampler(processes, self.cpus, interval_seconds=interval,
            max_records=bound, record_sink=sink, terminal_roles=("source",))

    @staticmethod
    def observe_source(source):
        return observe_owned_exit(source.pid)

    @staticmethod
    def complete_source(source, sampler, deadline_ns):
        while True:
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
        while observe_owned_exit(server.pid) is None:
            if time.monotonic_ns() >= deadline_ns:
                raise RuntimeError("destination terminal sampling deadline")
            time.sleep(.01)
        prior = [r for r in sampler.records_snapshot() if r["role"] == role]
        final = sample_linux_process(server.pid, self.cpus)
        if (not prior or final["state"] != "Z" or final["pid"] != prior[-1]["pid"]
                or final["start_ticks"] != prior[-1]["start_ticks"]
                or final["cpu_ns"] < prior[-1]["cpu_ns"]
                or final["timestamp_ns"] <= prior[-1]["timestamp_ns"]):
            raise RuntimeError("destination terminal identity/counter continuity failed")
        sink({**final, "role": role})
        if server.wait(timeout=0) != 0:
            raise RuntimeError("destination exit failed")
