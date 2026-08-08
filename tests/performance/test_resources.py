from __future__ import annotations

import os

from scripts.performance.resources import sample_windows_process


def test_windows_resource_sample_reports_current_process() -> None:
    sample = sample_windows_process(os.getpid())
    assert sample.pid == os.getpid()
    assert sample.user_cpu_ns >= 0
    assert sample.kernel_cpu_ns >= 0
    assert sample.working_set_bytes > 0
    assert sample.private_bytes > 0
    assert sample.thread_count >= 1
