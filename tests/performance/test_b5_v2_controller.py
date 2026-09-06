import io
import json
from pathlib import Path
import queue

import pytest
from scripts import run_b5_v2 as b5


@pytest.mark.parametrize("paths", [[], ["nbsr", "nbsr"], ["unknown"], "nbsr", None])
def test_path_selection_rejects_empty_duplicate_and_unknown(paths):
    with pytest.raises(ValueError):
        b5.selected_paths(paths)


def test_default_pair_alternates_and_single_path_stays_selected():
    assert b5.selected_paths(["nbsr", "direct"]) == ("direct", "nbsr")
    assert b5.path_order(("direct", "nbsr"), 1) == ("direct", "nbsr")
    assert b5.path_order(("direct", "nbsr"), 2) == ("nbsr", "direct")
    assert b5.path_order(("nbsr",), 2) == ("nbsr",)


@pytest.mark.parametrize("dispersed", [False, True])
@pytest.mark.parametrize("paths", [["nbsr"], ["direct"], ["direct", "nbsr"]])
def test_execute_runs_only_selected_paths_with_same_repeat_gate(monkeypatch, tmp_path, paths, dispersed):
    from types import SimpleNamespace
    binaries = {}
    for role in ("direct", "nbsr", "server"):
        binary = tmp_path / f"{role}.exe"
        binary.write_bytes(role.encode())
        binaries[role] = binary
    monkeypatch.setattr(b5.subprocess, "check_output", lambda argv, **kw: "a" * 40 if argv[1] == "rev-parse" else "")
    monkeypatch.setattr(b5, "assert_clean_source", lambda *_: None)
    monkeypatch.setattr(b5, "windows_processor_topology", lambda: {})
    monkeypatch.setattr(b5, "placement", lambda *_: {})
    monkeypatch.setattr(b5.p2a, "build", lambda *_: binaries.copy())
    monkeypatch.setattr(b5, "load_ceiling", lambda *a, **kw: dict(rate_numerator=123, rate_denominator=2))
    monkeypatch.setattr(b5, "require_reference_placement", lambda *_: None)
    monkeypatch.setattr(b5, "write_loopback_authority", lambda *_: None)
    calls = []
    def run(cell, *args, **kwargs):
        calls.append(cell["path"])
        assert kwargs["duration"] == 7200 and kwargs["rate"] == (123, 2)
        return dict(path=cell["path"], valid=True, gbps=calls.count(cell["path"]) if dispersed else 1)
    monkeypatch.setattr(b5, "run_one", run)
    args = SimpleNamespace(paths=paths, diagnostic=False, reference=tmp_path / "reference", rate=None,
        duration=7200, warmup=2, progress=1, output=tmp_path / "output", target=tmp_path,
        cores=1, groups=1, streams=1, payload=1024, percent=70, depth=1, ownership_sampling=True)
    b5.execute(args)
    expected = []
    for repeat in range(1, 6 if dispersed else 4):
        pair = ("direct", "nbsr") if repeat % 2 else ("nbsr", "direct")
        expected.extend(path for path in pair if path in paths)
    assert calls == expected
    summary = json.loads((args.output / "summary.json").read_text())
    assert summary["selected_paths"] == [path for path in ("direct", "nbsr") if path in paths]
    assert summary["repeats_per_path"] == (5 if dispersed else 3)

@pytest.mark.parametrize("options,expected", [([], ["direct", "nbsr"]), (["--paths", "nbsr"], ["nbsr"])])
def test_paths_cli_default_and_explicit_selection(monkeypatch, options, expected):
    import sys
    received = []
    monkeypatch.setattr(sys, "argv", ["run_b5_v2.py", "--output", "unused", "--duration", "7200", *options])
    monkeypatch.setattr(b5, "execute", lambda args: received.append(args.paths))
    b5.main()
    assert received == [expected]


def test_reader_has_fixed_queue_and_chunk_bounds_and_joins():
    reader = b5.BoundedReader(io.BytesIO(b"a" * 200_000))
    reader.start()
    values = []
    while True:
        value = reader.queue.get(timeout=1)
        if value is None:
            break
        assert isinstance(value, bytes) and len(value) <= 65_536
        values.append(value)
    reader.join()
    assert reader.queue.maxsize == 16
    assert b"".join(values) == b"a" * 200_000


def test_reader_read_error_is_propagated():
    class Broken:
        def read(self, _):
            raise OSError("read failed")
    reader = b5.BoundedReader(Broken())
    reader.start()
    assert isinstance(reader.queue.get(timeout=1), OSError)
    reader.join()


def test_silent_poll_checks_health_and_does_not_extend_deadline():
    class SilentQueue:
        def get(self, timeout):
            assert 0 < timeout <= 0.1
            raise queue.Empty
    class Reader:
        queue = SilentQueue()
    class Source:
        def poll(self):
            return None
    class Stream:
        checks = 0
        def check(self, *, source_active):
            assert source_active
            self.checks += 1
            if self.checks == 3:
                raise ValueError("fixed deadline")
    stream = Stream()
    with pytest.raises(ValueError, match="fixed deadline"):
        b5.consume(Source(), Reader(), stream)
    assert stream.checks == 3


def test_repeat_requirement_never_counts_invalid_or_accepts_high_cv_three():
    assert b5.required_repeats([dict(valid=True, gbps=1)] * 2) == 3
    assert b5.required_repeats([dict(valid=True, gbps=x) for x in (1, 1, 2)]) == 5
    with pytest.raises(ValueError):
        b5.required_repeats([dict(valid=False, gbps=1)] * 3)


def test_every_destination_growth_is_checked_and_mixed_excluded_from_drift():
    guards = b5.LiveGuards(groups=2, max_progress=10, max_resources=100)
    for index in range(4):
        guards.resource(dict(role="destination_1", monotonic_timestamp_ns=100 + index * 1_000_000_000,
                             private_bytes=100 + index * 100))
    guards.origin_ns = 100
    with pytest.raises(RuntimeError, match="destination_1"):
        guards.progress(dict(phase="steady", elapsed_ns=3_000_000_000,
                             goodput_bytes_per_second=100, p99_latency_ns=100), received_ns=3_000_000_100)
    guards = b5.LiveGuards(groups=1, max_progress=10, max_resources=100)
    guards.progress(dict(phase="mixed", elapsed_ns=1, goodput_bytes_per_second=0, p99_latency_ns=None), received_ns=1)
    assert guards.steady == []


def test_receive_clock_origin_is_explicit_and_does_not_rebase():
    guards = b5.LiveGuards(groups=1, max_progress=10, max_resources=10)
    assert guards.qualification()["resource_phase_origin_monotonic_ns"] is None
    value = dict(phase="steady", elapsed_ns=100, goodput_bytes_per_second=100,
                 p99_latency_ns=100)
    guards.progress(value, received_ns=1000)
    assert guards.qualification()["resource_phase_origin_monotonic_ns"] == 900
    guards.progress({**value, "elapsed_ns": 200}, received_ns=9000)
    assert guards.qualification()["resource_phase_origin_monotonic_ns"] == 900


def test_callback_retention_bounds_fail_instead_of_dropping():
    guards = b5.LiveGuards(groups=1, max_progress=1, max_resources=1)
    guards.resource(dict(role="source", monotonic_timestamp_ns=1, private_bytes=1))
    with pytest.raises(RuntimeError, match="resource bound"):
        guards.resource(dict(role="source", monotonic_timestamp_ns=2, private_bytes=1))


def test_source_commands_are_matched_and_no_diagnostic_bypass_in_soak():
    cell = dict(path="direct", endpoint_groups=2, streams_per_group=1,
                outstanding_per_stream=1, payload_bytes=16384)
    binaries = {"direct": "direct.exe", "nbsr": "source.exe"}
    arguments = b5.source_command(cell, binaries, "authority", ["127.0.0.1:1", "127.0.0.1:2"],
                                  warmup=2, duration=30, progress=1, rate=(200, 1), report="cleanup.json")
    assert "--lifecycle" in arguments and "warm" in arguments
    assert arguments[arguments.index("--b5-rate-numerator") + 1] == "200"
    assert arguments[arguments.index("--p2a-runtime-workers") + 1] == "1"
    assert "--p2a-cleanup-report" not in arguments
    cell["path"] = "nbsr"
    arguments = b5.source_command(cell, binaries, "authority", ["127.0.0.1:1"],
                                  warmup=2, duration=30, progress=1, rate=(200, 1), report="cleanup.json")
    assert "--p2a-cleanup-report" in arguments


def test_cli_requires_ceiling_unless_explicit_diagnostic():
    with pytest.raises(ValueError, match="ceiling"):
        b5.validate_mode(diagnostic=False, reference=None, rate=None)
    assert b5.validate_mode(diagnostic=True, reference=None, rate=(200, 1)) == "DIAGNOSTIC"
    with pytest.raises(ValueError):
        b5.validate_mode(diagnostic=True, reference="ref", rate=(200, 1))


@pytest.mark.parametrize("failure", [None, "ownership", "parser"])
def test_run_one_ack_follows_sampling_and_preserves_failed_reader_tail(monkeypatch, tmp_path, failure):
    from scripts.performance.post_close_cleanup import FIELDS
    stopped = []
    processes = []

    class Process:
        def __init__(self, argv, **kwargs):
            self.source = argv[0] == "source.exe"
            self.pid = 100 + len(processes)
            self.returncode = 0 if self.source else None
            self.stdout = io.BytesIO(b"retained failure bytes\n")
            self.argv = argv
            processes.append(self)
            report = Path(argv[argv.index("--p2a-cleanup-report") + 1])
            counters = dict.fromkeys(FIELDS, 0)
            if failure == "ownership":
                counters[FIELDS[-1]] = 1
            report.write_text(json.dumps(dict(schema="nbsr-p2a-post-close-v1", pid=self.pid,
                role="source" if self.source else "destination", diagnostics_enabled_before_run=True,
                runtime_state="runtime_alive", ownership=counters)))

        def poll(self):
            return self.returncode

        def wait(self, timeout):
            if not self.source and self.returncode is None:
                assert stopped, "ACK cannot precede sampler stop"
                ack = Path(self.argv[self.argv.index("--completion-ack") + 1])
                assert ack.is_file()
            self.returncode = 0
            return 0

        def kill(self):
            self.returncode = -1

    class Sampler:
        def __init__(self, processes, **kwargs):
            assert kwargs["max_records"] == 388  # ceil((2+2+92)/.5+2)*2

        def start(self):
            pass

        def stop(self):
            stopped.append(True)
            return []

        def check_health(self, **kwargs):
            pass

    def consume(source, reader, stream):
        stream._on_progress(dict(phase="steady", elapsed_ns=100,
                                 goodput_bytes_per_second=100, p99_latency_ns=100),
                            received_ns=1000)
        if failure == "parser":
            cause = ProcessLookupError("synthetic lookup failure")
            cause.add_note("resource sampler role=destination_0 pid=100")
            raise ValueError("injected parser failure") from cause
        return dict(completed=1, offered=1, measurement_duration_ns=2_000_000_000, drain_duration_ns=0)

    monkeypatch.setattr(b5.subprocess, "Popen", Process)
    monkeypatch.setattr(b5, "ProcessResourceSampler", Sampler)
    monkeypatch.setattr(b5, "consume", consume)
    monkeypatch.setattr(b5, "wait_ready", lambda *_: {"endpoint": "127.0.0.1:1234"})
    monkeypatch.setattr(b5, "set_and_verify_exact_affinity", lambda *_: {"verified": True})
    result = b5.run_one(dict(path="nbsr", endpoint_groups=1, streams_per_group=1,
                            outstanding_per_stream=1, payload_bytes=1024),
                        dict(direct="direct.exe", nbsr="source.exe", server="server.exe"),
                        tmp_path, dict(endpoint_masks=[1], source_mask=1, logical_processors_available=1),
                        tmp_path / "run", warmup=2, duration=2, progress=1, rate=(200, 1), diagnostic=True)
    assert result["valid"] is (failure is None)
    assert result["qualification"]["resource_phase_origin_monotonic_ns"] == 900
    retained = json.loads((tmp_path / "run" / "result.json").read_text())
    assert retained["qualification"]["resource_phase_origin_monotonic_ns"] == 900
    assert all(process.poll() is not None for process in processes)
    if failure == "parser":
        assert (tmp_path / "run" / "source.stdout.ndjson").read_bytes() == b"retained failure bytes\n"
        assert not (tmp_path / "run" / "completion.ack").exists()
        assert "synthetic lookup failure" in retained["failure_traceback"]
        assert "role=destination_0 pid=100" in retained["failure_traceback"]
        assert retained["failure_traceback_truncated"] is False


@pytest.mark.parametrize("change", [None, "mask", "efficiency", "logical_count"])
def test_reference_pool_and_stable_topology_must_match(change):
    from copy import deepcopy
    topology = dict(verified=True, scope="physical-core-selected-logical-processors", physical_cores=1,
                    logical_processors=2, cores=[dict(core_index=0, smt=True, efficiency_class=0, logical_mask=3)])
    plan = dict(source_mask=1, endpoint_masks=[1], logical_processors_available=1)
    load = dict(reference_placement=deepcopy(plan),
                reference_topology_identity={k: deepcopy(v) for k, v in topology.items() if k != "verified"})
    if change == "mask":
        plan["source_mask"] = 2
        plan["endpoint_masks"] = [2]
    elif change == "efficiency":
        topology["cores"][0]["efficiency_class"] = 1
    elif change == "logical_count":
        topology["logical_processors"] = 4
    if change:
        with pytest.raises(ValueError):
            b5.require_reference_placement(load, plan, topology)
    else:
        b5.require_reference_placement(load, plan, topology)


@pytest.mark.parametrize("head,status", [("b" * 40, ""), ("a" * 40, " M source.rs")])
def test_final_source_identity_check_rejects_repository_drift(monkeypatch, head, status):
    def output(argv, **kwargs):
        return head if argv[1] == "rev-parse" else status
    monkeypatch.setattr(b5.subprocess, "check_output", output)
    with pytest.raises(RuntimeError, match="source changed"):
        b5.assert_clean_source("a" * 40)
