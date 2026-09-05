from pathlib import Path
import json

from scripts import run_max_throughput_v2_stage4 as stage4
from scripts.run_physical_core_v2 import placement, repeat_requirement
import pytest


def test_shared_physical_pool_excludes_smt_and_unavailable_cores():
    topology = {"verified": True, "cores": [{"logical_mask": 3}, {"logical_mask": 12}]}
    assert placement(topology, 2, 2) == {"source_mask": 5, "endpoint_masks": [5, 5],
                                         "logical_processors_available": 2}
    with pytest.raises(RuntimeError):
        placement(topology, 4, 1)
    with pytest.raises(ValueError):
        placement(topology, 1, 2)
    assert repeat_requirement([1, 1, 1]) == 3
    assert repeat_requirement([1, 2, 1]) == 5


def test_custom_shape_and_single_core_allocation_reach_actual_runner(monkeypatch, tmp_path):
    commands, assigned = [], []
    record = {"schema": "nbsr-p2a-repeat-v2", "errors": 0,
              "transport_sessions_created_delta": 0, "service_channels_created_delta": 0,
              "application_streams_created_delta": 0, "replay_entries_delta": 0}

    class Process:
        pid = 123
        returncode = 0

        def __init__(self, argv, **kwargs):
            commands.append(argv)

        def communicate(self, **kwargs):
            return json.dumps(record, separators=(",", ":")), ""

        def wait(self, **kwargs):
            return 0

        def poll(self):
            return 0

    class Sampler:
        def __init__(self, processes, **kwargs):
            assigned.append(kwargs["assigned_logical_processors"])

        def start(self):
            pass

        def stop(self):
            return []

    monkeypatch.setattr(stage4.subprocess, "Popen", Process)
    monkeypatch.setattr(stage4, "ProcessResourceSampler", Sampler)
    monkeypatch.setattr(stage4, "set_and_verify_exact_affinity", lambda *a: {"verified": True})
    monkeypatch.setattr(stage4, "wait_ready", lambda *a: {"endpoint": "127.0.0.1:1234"})
    monkeypatch.setattr(stage4.p2a, "summarize_resources", lambda *a: {})
    captured = {}

    def aggregate(records, **kwargs):
        captured.update(kwargs)
        return {"measured_ns": 1_000_000_000, "completed_operations": 1}

    monkeypatch.setattr(stage4.stage2, "aggregate_group_records", aggregate)
    monkeypatch.setattr(stage4.stage2, "validate_group_records", lambda *a, **k: True)
    cell = dict(path="direct", payload_bytes=1024, streams_per_group=2,
                outstanding_per_stream=8, endpoint_groups=1, runtime_workers=1)
    stage4.run_repeat(cell, 1, {"direct": Path("direct.exe")}, tmp_path, 1, 2,
                      tmp_path, {}, placement={"source_mask": 1, "endpoint_masks": [1],
                                               "logical_processors_available": 1})
    client = commands[-1]
    assert client[client.index("--payload-bytes") + 1] == "1024"
    assert client[client.index("--p2a-streams") + 1] == "2"
    assert client[client.index("--p2a-outstanding-per-stream") + 1] == "8"
    assert captured == dict(payload_bytes=1024, streams_per_group=2, outstanding_per_stream=8)
    assert assigned == [1]


def test_failed_affinity_cleans_source_and_preserves_partial_output(monkeypatch, tmp_path):
    processes = []

    class Process:
        pid = 123

        def __init__(self, *args, **kwargs):
            self.returncode = None
            processes.append(self)

        def poll(self):
            return self.returncode

        def kill(self):
            self.returncode = -9

        def wait(self, **kwargs):
            return self.returncode

        def communicate(self, **kwargs):
            return "partial stdout", "partial stderr"

    def affinity(*args):
        if len(processes) == 2:
            raise OSError("source affinity failed")
        return {"verified": True}

    monkeypatch.setattr(stage4.subprocess, "Popen", Process)
    monkeypatch.setattr(stage4, "set_and_verify_exact_affinity", affinity)
    monkeypatch.setattr(stage4, "wait_ready", lambda *a: {"endpoint": "127.0.0.1:1234"})
    cell = dict(path="direct", payload_bytes=1024, streams_per_group=1,
                outstanding_per_stream=1, endpoint_groups=1, runtime_workers=1)
    with pytest.raises(OSError, match="source affinity failed"):
        stage4.run_repeat(cell, 1, {"direct": Path("direct.exe")}, tmp_path, 1, 2,
                          tmp_path, {}, placement={"source_mask": 1, "endpoint_masks": [1],
                                                   "logical_processors_available": 1})
    assert all(p.poll() is not None for p in processes)
    assert next(tmp_path.glob("*.stderr.txt")).read_text() == "partial stderr"
