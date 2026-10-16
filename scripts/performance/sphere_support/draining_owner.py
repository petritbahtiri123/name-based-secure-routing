"""Bounded Windows Job drain; no extension of the caller's original deadline."""
import math,time
from scripts.performance.windows_native_management import WindowsOwner

class DrainingOwner(WindowsOwner):
    GRACE_SECONDS = 2.0

    def __init__(self, argv, *, backend, cancel, deadline, clock=time.monotonic):
        super().__init__(argv, backend=backend, cancel=cancel)
        if not isinstance(deadline,(int,float)) or not math.isfinite(deadline):
            raise ValueError('finite original deadline required')
        self.deadline,self.clock = deadline,clock
        self.drain_until = self.previous = None
        self.drain_failure = None
        self.drain_events = []

    def record(self, **row):
        if len(self.drain_events)<2048:self.drain_events.append(row)

    def fail(self, reason):
        self.drain_failure = self.drain_failure or reason
        self.record(event='failed',reason=reason)
        # Only the exact retained Job (or unassigned suspended process) can be killed.
        # Preserve the primary failure and any termination failure separately.
        try:
            self.record(event='owned_termination_requested',already_requested=self.killed)
            self.signal('KILL')
            self.record(event='owned_termination_returned')
        except Exception as exc:self.record(event='termination_failed',type=type(exc).__name__)

    def observe(self):
        try:
            code,live = super().observe()
            now = self.clock()
            if not math.isfinite(now) or (self.previous is not None and now<self.previous):
                raise RuntimeError('drain clock uncertainty')
            self.previous = now
            # After a latched failure, retain normal observations so cleanup can
            # independently prove empty and reap. The caller retains failure status.
            if self.drain_failure is not None:return code,live
            if self.drain_until is not None and now>=self.drain_until:
                raise TimeoutError('descendant drain deadline')
            if code==0 and live and self.assigned and not self.cancelled and not self.killed:
                if self.drain_until is None:
                    self.drain_until=min(now+self.GRACE_SECONDS,self.deadline)
                if now>=self.drain_until:raise TimeoutError('original deadline exhausted')
                pids=self.backend.member_pids(self.job)
                self.record(event='draining',monotonic=now,leader_exit=code,
                            job_member_pids=pids,deadline=self.drain_until)
                # Keep the composite owned operation pending. Raw leader exit is
                # retained above; the supervisor continues its original guards.
                return None,True
            if self.drain_until is not None and not live:
                self.record(event='empty_observed',monotonic=now,leader_exit=code)
            return code,live
        except Exception as exc:
            self.fail(type(exc).__name__)
            raise
