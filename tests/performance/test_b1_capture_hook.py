from contextlib import contextmanager
import json
from pathlib import Path

import pytest

from scripts import run_b1_wire_overhead as b1


@pytest.mark.parametrize("fail", [False, True])
def test_observer_covers_workload_and_closes_on_failure(monkeypatch, tmp_path, fail):
    events = []

    class Peer:
        returncode = 0

        def poll(self):
            return 0

        def wait(self, timeout):
            events.append("server_wait")

    class Counter:
        relay_endpoint = ("127.0.0.1", 1111)
        control_endpoint = ("127.0.0.1", 2222)

        def start(self):
            pass

        def authorize_client_process(self, pid):
            pass

        def close(self):
            events.append("counter_close")

        def result(self):
            return {"capture_method": "fixture", "measured_unit": "fixture", "client_ownership": "fixture",
                    "phases": {"setup": {}, "established": {}}, "rejected_datagrams": 0,
                    "server_endpoint": "127.0.0.1:5678", "relay_endpoint": "127.0.0.1:1111"}

    class Observer:
        @contextmanager
        def capture(self, endpoint, directory):
            assert endpoint == "127.0.0.1:5678"
            events.append("capture_start")
            try:
                yield
            finally:
                events.append("capture_stop")

    def measured(*args, **kwargs):
        assert events == ["capture_start"]
        events.append("client")
        if fail:
            raise RuntimeError("fixture client failure")
        return json.dumps({"completed_operations": 10, "measured_ns": 1_000_000_000}), []

    monkeypatch.setattr(b1.subprocess, "Popen", lambda *a, **k: Peer())
    monkeypatch.setattr(b1, "wait_ready", lambda *a: {"endpoint": "127.0.0.1:5678"})
    monkeypatch.setattr(b1, "UdpFlowCounter", lambda *a: Counter())
    monkeypatch.setattr(b1, "measured_client", measured)
    monkeypatch.setattr(b1, "summarize_resources", lambda *a: {})
    kwargs = dict(path="nbsr", cell={"payload_bytes": 1024, "streams": 1, "operations_per_stream": 10},
                  repeat=1, binaries={"server": Path("server"), "nbsr": Path("source")}, authority=tmp_path,
                  warmup_seconds=0, raw_dir=tmp_path, observer=Observer())
    if fail:
        with pytest.raises(RuntimeError, match="fixture client failure"):
            b1._run_repeat(**kwargs)
    else:
        assert b1._run_repeat(**kwargs)["application_bytes"] == 20480
    assert events[-1] == "capture_stop"
