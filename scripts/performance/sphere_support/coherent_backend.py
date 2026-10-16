"""Refresh Job accounting after an irrevocably signalled leader observation.

Retains the original suspended assignment, kill-on-close Job, exact handles,
deadlines and fail-closed ownership. Does not give surviving children a grace
period or infer their absence from leader exit.
"""
import ctypes as C
import time
from scripts.performance.windows_job_backend import Win32Backend, Accounting

class CoherentBackend(Win32Backend):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.exit_observations = []

    def observe(self, job, process, assigned):
        code, active = super().observe(job, process, assigned)
        if assigned and code is not None:
            accounting = Accounting()
            row = dict(monotonic=time.monotonic(), exit_code=code,
                       sampled_before_exit_check=active, refreshed_after_exit_check=None)
            # Capture only exit observations; bounded diagnostics never affect ownership.
            if len(self.exit_observations) < 2048:
                self.exit_observations.append(row)
            self._check(self.kernel.QueryInformationJobObject(
                job, 1, C.byref(accounting), C.sizeof(accounting), None))
            active = accounting.ActiveProcesses
            row['refreshed_after_exit_check'] = active
        return code, active
