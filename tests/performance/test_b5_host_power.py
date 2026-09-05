import ctypes
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import run_b5_sustained_capacity as b5
from scripts.performance import windows_power


def test_power_schema_is_raw_os_reported_and_never_secret_text(monkeypatch):
    def system(pointer):
        value = ctypes.cast(pointer, ctypes.POINTER(windows_power.SystemPower)).contents
        value.ACLineStatus = 1
        value.BatteryLifePercent = 50
        return 1

    def cpu(level, input_buffer, length, output, size):
        assert level == 11 and input_buffer is None and length == 0
        value = ctypes.cast(output, ctypes.POINTER(windows_power.ProcessorPower)).contents
        value.CurrentMhz = value.MaxMhz = value.MhzLimit = 2101
        return 0

    monkeypatch.setattr(windows_power, "_apis", lambda: (system, cpu, 1))
    row = windows_power.sample_host_power()
    assert row["status"] == "AVAILABLE"
    assert row["processor_information"]["fields"][0]["CurrentMhz"] == 2101
    assert "OS-reported" in row["interpretation"]
    assert row["monotonic_timestamp_ns"] > 0
    assert row["system_power_status"]["call_cost_ns"] >= 0
    assert set(row) == {"schema", "status", "monotonic_timestamp_ns", "system_power_status", "processor_information", "interpretation"}

    def unavailable():
        raise OSError("secret-password 192.0.2.1 private-key")

    monkeypatch.setattr(windows_power, "_apis", unavailable)
    row = windows_power.sample_host_power()
    assert row["status"] == "UNAVAILABLE"
    assert "secret" not in json.dumps(row) and "192.0.2.1" not in json.dumps(row)
    assert row["system_power_status"]["fields"] is None


def test_failed_api_status_is_not_implicit_success(monkeypatch):
    monkeypatch.setattr(windows_power, "_apis", lambda: (lambda p: 0, lambda *a: -1073741790, 1))
    row = windows_power.sample_host_power()
    assert row["status"] == "UNAVAILABLE"
    assert row["processor_information"]["return_code"] == "0xc0000022"
    assert row["processor_information"]["fields"] is None


@pytest.mark.parametrize("enabled", [False, True])
def test_power_is_optional_progress_only_and_preserved_on_abort(monkeypatch, tmp_path, enabled):
    peer = SimpleNamespace(pid=1, poll=lambda: 0)
    monkeypatch.setattr(b5.subprocess, "Popen", lambda *a, **k: peer)
    monkeypatch.setattr(b5, "wait_ready", lambda *a: {"endpoint": "127.0.0.1:12345"})
    calls = []
    def power():
        calls.append(True)
        return {"status": "UNAVAILABLE", "fields": None}
    monkeypatch.setattr(b5, "sample_host_power", power)
    def measured(*a, output_line_sink, **k):
        output_line_sink(json.dumps({"event": "diagnostic"}))
        output_line_sink(json.dumps({"event": "p2a_progress", "elapsed_ns": 1, "errors": 1}))
    monkeypatch.setattr(b5, "measured_client", measured)
    with pytest.raises(RuntimeError, match="soak live abort"):
        b5._run_one(dict(name="power", duration_seconds=10, payload_bytes=1024, streams=1),
                    binaries={"server": Path("server"), "nbsr": Path("source")}, authority=tmp_path,
                    output=tmp_path, warmup_seconds=1, cooldown_seconds=1, sample_seconds=1,
                    **({"host_power": True} if enabled else {}))
    path = tmp_path / "raw/power/power.ndjson"
    assert len(calls) == int(enabled)
    if enabled:
        assert json.loads(path.read_text())["status"] == "UNAVAILABLE"
    else:
        assert not path.exists()
