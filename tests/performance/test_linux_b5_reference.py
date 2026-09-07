from pathlib import Path
import json

import pytest

from scripts.performance import linux_b5_reference as reference


def cell(path="nbsr"):
    return dict(path=path, payload_bytes=16384, streams=1, outstanding=1, cores=1)


def result():
    return dict(
        schema="nbsr-p2a-repeat-v2",
        path="nbsr",
        payload_bytes=16384,
        streams=1,
        outstanding_per_stream=1,
        configured_total_outstanding=1,
        max_outstanding_per_stream_observed=1,
        completed_operations=100,
        measured_ns=1_000_000_000,
        p50_latency_ns=1,
        p95_latency_ns=2,
        p99_latency_ns=3,
        errors=0,
        missing=0,
        duplicates=0,
        corrupt=0,
        wrong_request=0,
        transport_sessions_created_delta=0,
        service_channels_created_delta=0,
        application_streams_created_delta=0,
        replay_entries_delta=0,
    )


def test_commands_match_shape_and_request_both_cleanup_reports(tmp_path):
    server, client, env = reference.commands(cell(), Path("/bin"), Path("/authority"), tmp_path, "127.0.0.1:4", 3, 20)
    assert server[server.index("--p2a-runtime-workers") + 1] == "1"
    assert client[client.index("--p2a-runtime-workers") + 1] == "1"
    assert "--p2a-cleanup-report" in server and "--p2a-cleanup-report" in client
    assert env == {"NBSR_P2A_STREAMS": "1"}
    assert "--b5-rate-numerator" not in client


def test_multicore_is_rejected_not_silently_reinterpreted(tmp_path):
    with pytest.raises(ValueError):
        reference.commands(cell() | {"cores": 4}, Path("/bin"), Path("/auth"), tmp_path, "127.0.0.1:4", 3, 20)


def test_exact_record_has_finite_stability_fields():
    row = reference.finish_record(cell(), 1, result(), cleanup_pass=True)
    assert row["endpoint_groups"] == row["runtime_workers"] == 1
    assert row["operations_per_second"] == 100
    assert row["configured_total_outstanding"] == 1
    assert row["max_observed_total_outstanding"] == 1
    assert row["cleanup_pass"] is True


@pytest.mark.parametrize(
    "change",
    [
        dict(errors=1),
        dict(missing=1),
        dict(corrupt=1),
        dict(duplicates=1),
        dict(wrong_request=1),
        dict(completed_operations=True),
        dict(streams=2),
        dict(payload_bytes=1024),
        dict(configured_total_outstanding=2),
        dict(max_outstanding_per_stream_observed=2),
    ],
)
def test_invalid_binary_records_fail(change):
    with pytest.raises(ValueError):
        reference.finish_record(cell(), 1, result() | change, cleanup_pass=True)


def test_cleanup_failure_cannot_be_valid():
    with pytest.raises(ValueError):
        reference.finish_record(cell(), 1, result(), cleanup_pass=False)


def test_failure_formatter_is_bound_in_retained_sources():
    assert "scripts/performance/b4_linux.py" in reference.SOURCE_PATHS


@pytest.mark.parametrize("server_code", [0, 1])
@pytest.mark.parametrize("source_fault", [None, "final", "report", "telemetry", "exiting", "exiting-first", "exiting-revival"])
def test_orchestration_samples_source_then_ack_then_server_join(tmp_path, server_code, source_fault):
    from scripts.performance.post_close_cleanup import FIELDS

    events = []

    class Process:
        def __init__(self, argv, **kwargs):
            self.role = "server" if "--ready" in argv else "client"
            self.pid = 11 if self.role == "server" else 12
            self.returncode = None
            self.code = server_code if self.role == "server" else 0
            if self.role == "server":
                Path(argv[argv.index("--ready") + 1]).write_text(json.dumps({"endpoint": "127.0.0.1:42"}))
            else:
                final = result()
                if source_fault == "final":
                    final["errors"] = 1
                kwargs["stdout"].write((json.dumps(final) + "\n").encode())
                kwargs["stdout"].flush()
            report = dict(
                schema="nbsr-p2a-post-close-v1",
                pid=self.pid,
                role="destination" if self.role == "server" else "source",
                diagnostics_enabled_before_run=True,
                runtime_state="runtime_alive",
                ownership=dict.fromkeys(FIELDS, 0),
            )
            if self.role == "client" and source_fault == "report":
                report["ownership"]["pending_routes_current_entries"] = 1
            Path(argv[argv.index("--p2a-cleanup-report") + 1]).write_text(json.dumps(report))

        def poll(self):
            return self.returncode

        def wait(self, timeout):
            if self.role == "server" and self.returncode is None:
                assert (tmp_path / "raw/completion.ack").exists()
            events.append(self.role + "-join")
            self.returncode = self.code
            return self.code

        def kill(self):
            self.returncode = -1

    clock = 0
    source_samples = 0

    def sample(pid, cpus):
        nonlocal clock, source_samples
        clock += 1
        state = "Z" if pid == 12 or (tmp_path / "raw/completion.ack").exists() else "S"
        if pid == 12:
            assert not (tmp_path / "raw/completion.ack").exists()
            events.append("client-final-sample")
            source_samples += 1
            if source_fault and source_fault.startswith("exiting"):
                sequence = (["R", "Z"] if source_fault == "exiting-first" else
                            ["S", "R", "S", "Z"] if source_fault == "exiting-revival" else ["S", "R", "Z"])
                state = sequence[source_samples - 1]
                if state == "R":
                    return dict(pid=pid, start_ticks=pid, state="R", flags=4, cpu_ns=clock,
                                timestamp_ns=clock, affinity=cpus, fd_count=None,
                                fd_count_state="UNAVAILABLE_EXITING")
            if source_fault == "telemetry":
                error = PermissionError(13, "FD unavailable", "/proc/12/fd")
                error.add_note("fd_permission_recheck: unchanged identity, state R")
                raise error
        return dict(pid=pid, start_ticks=pid, state=state, cpu_ns=clock, timestamp_ns=clock, affinity=cpus)

    row = reference.run_cell(
        cell(),
        1,
        Path("/bin"),
        tmp_path / "authority",
        tmp_path / "raw",
        [0],
        "/usr/bin/taskset",
        warmup=3,
        duration=20,
        sample_fn=sample,
        popen=Process,
        exec_check=lambda *args: None,
    )
    expected_source_pass = source_fault in (None, "exiting")
    assert row["valid"] is (server_code == 0 and expected_source_pass)
    assert events.index("client-final-sample") < events.index("client-join")
    if not expected_source_pass:
        assert not (tmp_path / "raw/completion.ack").exists()
        assert "error" in row
        assert (tmp_path / "raw/client.stdout").read_bytes()
        assert (tmp_path / "raw/client.cleanup.json").exists()
    else:
        assert events.index("client-join") < events.index("server-join")
    assert (tmp_path / "raw/resources.ndjson").exists()
    assert (tmp_path / "raw/record.json").exists()
    if source_fault == "exiting":
        assert source_samples == 3
        if server_code == 0:
            assert row["final_process_samples"]["client"]["state"] == "Z"
    if source_fault == "telemetry":
        retained = json.loads((tmp_path / "raw/record.json").read_text())
        assert retained["error_type"] == "PermissionError"
        assert "fd_permission_recheck: unchanged identity, state R" in retained["traceback"]
        assert retained["traceback_truncated"] is False


@pytest.mark.parametrize("dispersed", [False, True])
def test_ladder_retains_three_or_five_matched_repeats(dispersed):
    calls, retained = [], []

    def run(value, repeat):
        calls.append((value["path"], value["outstanding"], repeat))
        record = result() | {"path": value["path"]}
        if dispersed and value["path"] == "nbsr" and repeat == 1:
            record["completed_operations"] = 80
        return reference.finish_record(value, repeat, record, cleanup_pass=True)

    rows = reference.run_ladder(16384, 1, [1], run, lambda row: retained.append(dict(row)))
    expected = 10 if dispersed else 6
    assert len(rows) == len(retained) == len(calls) == expected
    assert rows == retained
    assert {row["repeat"] for row in rows} == set(range(1, expected // 2 + 1))


def test_ladder_invalid_attempt_is_retained_and_never_counted():
    retained = []

    def run(value, repeat):
        return dict(path=value["path"], repeat=repeat, valid=False, error="source failed")

    with pytest.raises(RuntimeError, match="invalid"):
        reference.run_ladder(16384, 1, [1], run, retained.append)
    assert len(retained) == 1 and retained[0]["valid"] is False


@pytest.mark.parametrize("depths", [[], [2], [1, 1], [2, 1], [1, True], [1, 3], [1, 2, 4, 8, 16, 32]])
def test_ladder_rejects_ambiguous_or_missing_baseline(depths):
    with pytest.raises(ValueError):
        reference.run_ladder(16384, 1, depths, lambda *args: pytest.fail("launched"), lambda row: None)


@pytest.mark.parametrize("fault", [None, "stale-build", "dirty-final", "binary-drift", "invalid-run"])
def test_campaign_freezes_inputs_and_preserves_failed_attempts(tmp_path, fault):
    from argparse import Namespace
    from tests.performance.test_linux_b5_ceiling import LINUX, SHA
    from scripts.performance.linux_loopback import digest

    binaries = tmp_path / "bin"
    binaries.mkdir()
    names = ("perf_direct_peer", "perf_rust_source", "wp8_interop_server")
    for name in names:
        (binaries / name).write_bytes(name.encode())
    manifest = tmp_path / "build.json"
    manifest.write_text(
        json.dumps(
            dict(
                source_sha="b" * 40 if fault == "stale-build" else SHA,
                build_profile="release",
                build_commands=["cargo build --release"],
                toolchains={"rustc": "test"},
                binary_sha256={name: digest(binaries / name) for name in names},
            )
        )
    )
    args = Namespace(
        binaries=binaries,
        build_manifest=manifest,
        output=tmp_path / "output",
        payload_bytes=16384,
        streams=1,
        depths=[1],
        warmup=3,
        duration=20,
    )
    calls = []

    def run(value, repeat, *unused, **kwargs):
        calls.append(value["path"])
        if fault == "invalid-run":
            return dict(valid=False, path=value["path"], repeat=repeat, error="retained failure")
        if fault == "binary-drift":
            (binaries / names[0]).write_bytes(b"changed")
        return reference.finish_record(value, repeat, result() | {"path": value["path"]}, cleanup_pass=True)

    def state():
        return SHA, " M changed" if len(calls) == 6 and fault == "dirty-final" else ""

    kwargs = dict(
        linux_environment=LINUX | {"taskset": "/usr/bin/taskset"},
        git_state_fn=state,
        run_fn=run,
        authority_fn=lambda p: p.mkdir(),
        executable_fn=lambda p: True,
    )
    if fault:
        with pytest.raises((ValueError, RuntimeError)):
            reference.execute(args, **kwargs)
        if fault == "stale-build":
            assert calls == []
            return
    else:
        reference.execute(args, **kwargs)
    output = args.output
    assert (output / "checksums.sha256").exists()
    rows = json.loads((output / "records.json").read_text())
    env = json.loads((output / "environment.json").read_text())
    assert env["classification"] == ("REFERENCE_CANDIDATE" if fault is None else "FAIL")
    assert len(rows) == (6 if fault in (None, "dirty-final") else 1)
    assert all((output / "binaries" / name).exists() for name in names)
    assert env["source_sha256"]
