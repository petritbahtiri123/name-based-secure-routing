"""Preserved task-local drain/observation primitives; inert until explicitly called."""

import ctypes as C
from ctypes import wintypes as W
import math
import time
from scripts.performance.reader_windows_backend import Win32Backend, Accounting
from scripts.performance.reader_windows_owner import WindowsOwner


class CoherentBackend(Win32Backend):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.exit_observations = []

    def observe(self, job, process, assigned):
        code, active = super().observe(job, process, assigned)

        if assigned and code is not None:
            accounting = Accounting()

            row = dict(monotonic=time.monotonic(), exit_code=code, sampled_before_exit_check=active, refreshed_after_exit_check=None)

            # Capture only exit observations; bounded diagnostics never affect ownership.

            if len(self.exit_observations) < 2048:
                self.exit_observations.append(row)

            self._check(self.kernel.QueryInformationJobObject(job, 1, C.byref(accounting), C.sizeof(accounting), None))

            active = accounting.ActiveProcesses

            row["refreshed_after_exit_check"] = active

        return code, active


class ProcessIds(C.Structure):
    _fields_ = [("NumberOfAssignedProcesses", W.DWORD), ("NumberOfProcessIdsInList", W.DWORD), ("ProcessIdList", C.c_size_t * 256)]


class DiagnosticBackend(CoherentBackend):
    def member_pids(self, job):
        info = ProcessIds()

        self._check(self.kernel.QueryInformationJobObject(job, 3, C.byref(info), C.sizeof(info), None))

        if info.NumberOfProcessIdsInList > 256 or info.NumberOfAssignedProcesses > 256:
            raise RuntimeError("Job PID snapshot exceeds bound")

        pids = list(info.ProcessIdList[: info.NumberOfProcessIdsInList])

        if any(p <= 0 for p in pids) or len(set(pids)) != len(pids):
            raise RuntimeError("invalid Job PID snapshot")

        return pids


class DrainingOwner(WindowsOwner):
    GRACE_SECONDS = 2.0

    def __init__(self, argv, *, backend, cancel, deadline, clock=time.monotonic):
        super().__init__(argv, backend=backend, cancel=cancel)

        if not isinstance(deadline, (int, float)) or not math.isfinite(deadline):
            raise ValueError("finite original deadline required")

        self.deadline, self.clock = deadline, clock

        self.drain_until = self.previous = None

        self.drain_failure = None

        self.drain_events = []

        self.timely_terminal = None

    def record(self, **row):
        if len(self.drain_events) < 2048:
            self.drain_events.append(row)

    def fail(self, reason):
        self.drain_failure = self.drain_failure or reason

        self.record(event="failed", reason=reason)

        # Only the exact retained Job (or unassigned suspended process) can be killed.

        # Preserve the primary failure and any termination failure separately.

        try:
            self.record(event="owned_termination_requested", already_requested=self.killed)

            self.signal("KILL")

            self.record(event="owned_termination_returned")

        except Exception as exc:
            self.record(event="termination_failed", type=type(exc).__name__)

    def observe(self):
        try:
            code, live = super().observe()

            now = self.clock()

            if not math.isfinite(now) or (self.previous is not None and now < self.previous):
                raise RuntimeError("drain clock uncertainty")

            self.previous = now

            # After a latched failure, retain normal observations so cleanup can

            # independently prove empty and reap. The caller retains failure status.

            if self.drain_failure is not None:
                return code, live

            if now >= self.deadline:
                raise TimeoutError("original owner deadline")

            if self.timely_terminal is not None:
                job, observed_at, drain_deadline = self.timely_terminal

                if self.job is not job or not self.assigned or self.cancelled or self.killed or code != 0 or live:
                    raise RuntimeError("timely Job terminal evidence changed")

                # Fresh Job observation still empty; prior timed proof remains immutable.

                # Caller must finish resource/cancel/deadline checks before accepting/reaping.

                return code, live

            if self.drain_until is not None and now >= self.drain_until:
                raise TimeoutError("descendant drain deadline")

            if code == 0 and live and self.assigned and not self.cancelled and not self.killed:
                if self.drain_until is None:
                    self.drain_until = min(now + self.GRACE_SECONDS, self.deadline)

                if now >= self.drain_until:
                    raise TimeoutError("original deadline exhausted")

                pids = self.backend.member_pids(self.job)

                self.record(event="draining", monotonic=now, leader_exit=code, job_member_pids=pids, deadline=self.drain_until)

                # Keep the composite owned operation pending. Raw leader exit is

                # retained above; the supervisor continues its original guards.

                return None, True

            if self.drain_until is not None and not live:
                self.record(event="empty_observed", monotonic=now, leader_exit=code)

                if code == 0 and self.assigned and not self.cancelled and not self.killed:
                    self.timely_terminal = (self.job, now, self.drain_until)

            return code, live

        except Exception as exc:
            self.fail(type(exc).__name__)

            raise
