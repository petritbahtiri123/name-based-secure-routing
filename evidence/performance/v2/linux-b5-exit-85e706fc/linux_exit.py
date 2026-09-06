"""Nonreaping observation for an exclusively owned Linux child.

The caller must retain the Popen object and explicitly wait after terminal
resource sampling. Do not call Popen.poll or let another thread reap this child
before that sampling. Missing ownership/permissions propagate as failures.
"""

import os


def observe_owned_exit(pid: int) -> int | None:
    if type(pid) is not int or pid <= 0:
        raise ValueError("positive owned child PID required")
    if not hasattr(os, "waitid") or not hasattr(os, "WNOWAIT"):
        raise RuntimeError("nonreaping waitid observation unavailable")
    result = os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    if result is None:
        return None
    if result.si_pid != pid:
        raise RuntimeError("waitid child identity mismatch")
    if result.si_code == os.CLD_EXITED:
        return result.si_status
    if result.si_code in (os.CLD_KILLED, os.CLD_DUMPED):
        return -result.si_status
    raise RuntimeError("waitid returned unexpected non-exit state")
