"""Opt-in live lifecycle regression; not a throughput measurement."""
import json
import os
from pathlib import Path
import subprocess
import time

import pytest

from scripts import run_b5_v2 as b5
from scripts.performance.authority import write_loopback_authority
from scripts.performance.post_close_cleanup import validate_report


@pytest.mark.parametrize("path", ["direct", "nbsr"])
def test_destination_remains_sampleable_until_controller_ack(tmp_path, path):
    binary_root = os.environ.get("NBSR_B5_LIVE_BINARIES")
    if binary_root is None:
        pytest.skip("set NBSR_B5_LIVE_BINARIES to reviewed release binaries")
    suffix = ".exe" if os.name == "nt" else ""
    binaries = {role: Path(binary_root) / (name + suffix) for role, name in
                (("direct", "perf_direct_peer"), ("nbsr", "perf_rust_source"),
                 ("server", "wp8_interop_server"))}
    assert all(value.is_file() for value in binaries.values())
    authority = tmp_path / "authority"
    write_loopback_authority(authority)
    cell = dict(path=path, endpoint_groups=1, streams_per_group=1,
                outstanding_per_stream=1, payload_bytes=1024)
    ready, ack = tmp_path / "ready.json", tmp_path / "completion.ack"
    destination_report = tmp_path / "destination.cleanup.json"
    argv, env = b5.stage4._server_command(cell, binaries, authority, ready,
                                         tmp_path / "destination.result.json", ack)
    if path == "nbsr":
        argv += ["--p2a-cleanup-report", str(destination_report),
                 "--p2a-post-cleanup-ack", str(ack)]
    source = None
    with (tmp_path / "destination.stderr").open("wb") as error_log:
        destination = subprocess.Popen(argv, cwd=b5.ROOT, env=env,
                                       stdout=subprocess.DEVNULL, stderr=error_log)
        try:
            endpoint = b5.wait_ready(ready, destination)["endpoint"]
            source_report = tmp_path / "source.cleanup.json"
            source_argv = b5.source_command(cell, binaries, authority, [endpoint],
                warmup=1, duration=2, progress=1, rate=(200, 1), report=source_report)
            source = subprocess.Popen(source_argv, cwd=b5.ROOT,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = source.communicate(timeout=95)
            (tmp_path / "source.stdout").write_bytes(stdout)
            (tmp_path / "source.stderr").write_bytes(stderr)
            assert source.returncode == 0, stderr.decode(errors="replace")
            if path == "nbsr":
                assert validate_report(json.loads(source_report.read_text()), "source", source.pid)
                until = time.monotonic() + 5
                while not destination_report.exists() and time.monotonic() < until:
                    time.sleep(0.01)
                assert validate_report(json.loads(destination_report.read_text()), "destination", destination.pid)
            # Deliberately delay only the external controller after source exit.
            # No extra workload, network timeout, or performance claim.
            time.sleep(0.6)
            assert destination.poll() is None, "destination exited before controller sampling ACK"
            if os.name == "nt":
                from scripts.performance.resources import sample_windows_process
                sample = sample_windows_process(destination.pid)
                assert sample.pid == destination.pid and sample.thread_count > 0
            ack.write_text("sampling complete\n", encoding="ascii")
            assert destination.wait(timeout=5) == 0
        finally:
            for process in (source, destination):
                if process is not None:
                    if process.poll() is None:
                        process.kill()
                    process.wait(timeout=5)
