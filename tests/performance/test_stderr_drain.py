import importlib
import subprocess
import sys
import time

import pytest


PAYLOAD = bytes(range(256)) * 8192


def child():
    return subprocess.Popen(
        [sys.executable, "-c", "import sys; print('ready',flush=True); sys.stderr.buffer.write(bytes(range(256))*8192); sys.stderr.buffer.flush()"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def test_unread_pipe_blocks_but_continuous_drain_preserves_every_byte(tmp_path):
    process = child()
    try:
        assert process.stdout.readline().strip() == b"ready"
        with pytest.raises(subprocess.TimeoutExpired):
            process.wait(timeout=0.2)
        module = importlib.import_module("scripts.performance.stderr_drain")
        output = tmp_path / "stderr.raw"
        drain = module.StderrDrain(process.stderr, output)
        assert process.wait(timeout=5) == 0
        result = drain.finish(5)
        assert result["valid"] and result["bytes"] == len(PAYLOAD)
        assert output.read_bytes() == PAYLOAD
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)


def test_write_failure_invalidates_but_still_drains_child(tmp_path):
    module = importlib.import_module("scripts.performance.stderr_drain")
    process = child()
    try:
        drain = module.StderrDrain(process.stderr, tmp_path)  # directory cannot be a log
        assert process.wait(timeout=5) == 0
        with pytest.raises(RuntimeError, match="stderr"):
            drain.finish(5)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)


def test_shutdown_is_bounded_and_can_finish_after_child_termination(tmp_path):
    module = importlib.import_module("scripts.performance.stderr_drain")
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], stderr=subprocess.PIPE)
    drain = module.StderrDrain(process.stderr, tmp_path / "stderr.raw")
    try:
        start = time.monotonic()
        with pytest.raises(TimeoutError):
            drain.finish(0.05)
        assert time.monotonic() - start < 1
    finally:
        process.kill()
        process.wait(timeout=5)
    assert drain.finish(5)["valid"]


def test_capture_failure_invalidates_otherwise_complete_record():
    from scripts.run_b4b_v2 import valid_record
    record = dict(successful_admissions=1, failed_admissions=0,
                  established_goodput_bytes_per_second=1, established_p99_latency_ns=1,
                  admission_elapsed_seconds=1, resources={}, cleanup={"processes_exited": True},
                  stderr_capture={"valid": False})
    assert not valid_record(record)


def test_read_failure_invalidates_capture(tmp_path):
    from scripts.performance.stderr_drain import StderrDrain
    class BrokenPipe:
        def read(self, size):
            raise OSError("injected pipe read failure")
        def close(self):
            pass
    drain = StderrDrain(BrokenPipe(), tmp_path / "stderr.raw")
    with pytest.raises(RuntimeError, match="pipe read failure"):
        drain.finish(5)
