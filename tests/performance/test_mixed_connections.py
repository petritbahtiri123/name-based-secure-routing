from __future__ import annotations

import inspect
from pathlib import Path

from scripts.performance.mixed_connections import admission_server_specs, analyze_records, load_levels, remember_completion
from scripts.run_b4b_mixed_connections import lifecycle_client_command, run_cell, terminal_evidence_complete


def test_exact_markers_do_not_validate_a_failed_evidence_writer() -> None:
    assert terminal_evidence_complete({0, 1}, {0}, {1}, source_succeeded=True)
    assert not terminal_evidence_complete({0, 1}, {0}, {1}, source_succeeded=False)
    assert not terminal_evidence_complete({0, 1}, {0}, {0, 1}, source_succeeded=True)
    assert not terminal_evidence_complete({0, 1}, {0}, set(), source_succeeded=True)


def test_admission_destinations_start_after_established_warmup() -> None:
    source = inspect.getsource(run_cell)
    warmup_complete = source.index("while time.monotonic() < warmup_deadline:")
    admission_destination_start = source.index('processes["admission-destination"] = lifecycle_server')

    assert admission_destination_start > warmup_complete


def record(
    clients: int,
    repeat: int,
    *,
    goodput: float,
    p99: int,
    successful: int,
    failed: int = 0,
    timeouts: int = 0,
    cleanup: bool = True,
) -> dict:
    per_client = 8 if clients else 0
    scheduled = clients * per_client
    return {
        "repeat": repeat,
        "clients": clients,
        "connections_per_client": per_client,
        "planned_clients": [0, 2, 4],
        "scheduled_admissions": scheduled,
        "successful_admissions": successful,
        "failed_admissions": failed,
        "errors": failed,
        "timeouts": timeouts,
        "established_goodput_bytes_per_second": goodput,
        "established_p95_latency_ns": p99 // 2,
        "established_p99_latency_ns": p99,
        "admission_p50_latency_ns": 1_000 if clients else None,
        "admission_p95_latency_ns": 2_000 if clients else None,
        "admission_p99_latency_ns": 3_000 if clients else None,
        "admission_elapsed_seconds": 1.0,
        "peak_pending_clients": clients,
        "resources": {"cpu_seconds": 1.0, "peak_working_set_bytes": 2_000, "peak_private_bytes": 1_000},
        "cleanup": {"all_zero": cleanup, "processes_exited": cleanup},
    }


def test_load_levels_increase_clients_without_changing_connection_work() -> None:
    assert load_levels(validation=True) == [(0, 0), (1, 2), (2, 2)]
    levels = load_levels(validation=False)
    assert [clients for clients, _ in levels] == [0, 1, 2, 4, 8, 16, 32, 64]
    assert {connections for clients, connections in levels if clients} == {4}


def test_historical_fanout_specs_remain_available_for_comparison() -> None:
    assert admission_server_specs(3, 8) == [(0, 0), (1, 8), (2, 16)]


def test_task4b_uses_one_bounded_driver_for_independent_logical_clients() -> None:
    command = lifecycle_client_command(
        Path("perf_rust_source"),
        "127.0.0.1:4433",
        Path("authority"),
        Path("lifecycle"),
        connections=1,
        offset=0,
        logical_clients=512,
    )

    assert command[command.index("--connections") + 1] == "1"
    assert command[command.index("--lifecycle-clients") + 1] == "512"


def test_task4b_orchestration_has_bounded_admission_processes() -> None:
    source = inspect.getsource(run_cell)

    assert 'processes["admission-destination"]' in source
    assert 'processes["admission-source"]' in source
    assert 'processes[f"admission-destination-{index}"]' not in source
    assert "stdout=admission_stdout_file" in source
    assert "stderr=admission_stderr_file" in source
    assert "lifecycle destination cleanup exceeded 15 seconds" in source


def test_task4d_each_client_owns_an_independent_task_on_one_driver_runtime() -> None:
    source = (Path("crates/nbsr-transport/src/bin/perf_rust_source.rs")).read_text(encoding="utf-8")

    assert "lifecycle_clients.spawn(async move" in source
    assert "build_benchmark_runtime(1)" in source
    assert "wait_for_lifecycle_client_terminals" not in source
    assert "fs::read_dir(root)" not in source
    assert "CompletionCoordinator::with_evidence" in source
    assert "thread::Builder::new()" in (Path("crates/nbsr-transport/src/bin/benchmark_support/lifecycle_completion.rs")).read_text(
        encoding="utf-8"
    )
    assert "tokio::time::timeout(deadline" in (Path("crates/nbsr-transport/src/bin/benchmark_support/lifecycle_completion.rs")).read_text(
        encoding="utf-8"
    )
    assert "if let Err(error) = connection.close().await" in source
    assert "client_task_failed" in source


def test_task4d_destination_uses_in_memory_completion_not_filesystem_polling() -> None:
    source = (Path("crates/nbsr-transport/src/bin/wp8_interop_server.rs")).read_text(encoding="utf-8")

    assert "wait_for_lifecycle_client_terminals" not in source
    assert "fs::read_dir(root)" not in source
    assert "CompletionCoordinator::without_evidence" in source
    assert "application.wait_for_send_ack().await.unwrap();" not in source
    assert "lifecycle destination handshake failed: {error:?}" in source
    assert "poll_fn(|context|" in source
    assert "completion.record(ordinal, terminal).await.unwrap();" in source


def test_first_admission_completion_timestamp_is_immutable() -> None:
    assert remember_completion(None, pending=1, now=10.0) is None
    assert remember_completion(None, pending=0, now=11.0) == 11.0
    assert remember_completion(11.0, pending=0, now=12.0) == 11.0


def test_task4b_records_completion_when_driver_exits_between_polls() -> None:
    source = inspect.getsource(run_cell)

    assert "pending=0, now=established_finished" in source
    assert (
        'glob("connection-*.ack")' not in source[source.index("while established_client.poll()") : source.index("established_finished =")]
    )
    assert "connection-*.driver-complete" not in source


def test_analysis_classifies_stable_degraded_and_saturated_regions() -> None:
    records = []
    for repeat in range(1, 4):
        records.extend(
            [
                record(0, repeat, goodput=100.0, p99=100, successful=0),
                record(2, repeat, goodput=96.0, p99=120, successful=16),
                record(4, repeat, goodput=82.0, p99=240, successful=32),
            ]
        )
    analysis = analyze_records(records)
    assert analysis["evidence"] == "PASS"
    assert analysis["system"] == "DEGRADED"
    assert [cell["status"] for cell in analysis["cells"]] == ["BASELINE", "STABLE", "DEGRADED"]


def test_analysis_preserves_first_saturation_and_bad_valid_results() -> None:
    records = []
    for repeat in range(1, 4):
        records.extend(
            [
                record(0, repeat, goodput=100.0, p99=100, successful=0),
                record(2, repeat, goodput=95.0, p99=120, successful=16),
                record(4, repeat, goodput=60.0, p99=400, successful=20, failed=12, timeouts=2),
            ]
        )
    analysis = analyze_records(records)
    assert analysis["evidence"] == "PASS"
    assert analysis["system"] == "SATURATED"
    assert analysis["first_saturation"]["clients"] == 4
    assert analysis["cells"][-1]["failed_admissions"] == 36


def test_non_monotonic_low_load_outlier_does_not_define_terminal_saturation() -> None:
    records = []
    for repeat in range(1, 4):
        records.extend(
            [
                record(0, repeat, goodput=100.0, p99=100, successful=0),
                record(2, repeat, goodput=60.0, p99=180, successful=16),
                record(4, repeat, goodput=95.0, p99=120, successful=32),
            ]
        )

    analysis = analyze_records(records)

    assert analysis["system"] == "STABLE"
    assert analysis["first_saturation"] is None


def test_analysis_fails_closed_on_missing_cells_repeats_or_cleanup() -> None:
    records = [record(0, repeat, goodput=100.0, p99=100, successful=0) for repeat in range(1, 4)]
    records.extend(record(2, repeat, goodput=95.0, p99=120, successful=16) for repeat in range(1, 4))
    records[-1]["cleanup"]["all_zero"] = False
    analysis = analyze_records(records)
    assert analysis["evidence"] == "INCONCLUSIVE"
    assert analysis["system"] == "UNSTABLE"
    assert analysis["invalid_records"]


def test_single_repeat_validation_is_inconclusive_but_not_unstable() -> None:
    records = [
        record(0, 1, goodput=100.0, p99=100, successful=0),
        record(2, 1, goodput=95.0, p99=120, successful=16),
        record(4, 1, goodput=92.0, p99=130, successful=32),
    ]
    analysis = analyze_records(records)
    assert analysis["evidence"] == "INCONCLUSIVE"
    assert analysis["system"] == "STABLE"


def test_handshake_saturation_is_partial_when_process_cleanup_is_proven() -> None:
    records = []
    for repeat in range(1, 4):
        records.extend(
            [
                record(0, repeat, goodput=100.0, p99=100, successful=0),
                record(2, repeat, goodput=95.0, p99=120, successful=16),
            ]
        )
        saturated = record(4, repeat, goodput=70.0, p99=350, successful=20, failed=12, cleanup=False)
        saturated["cleanup"]["processes_exited"] = True
        saturated["saturation_failure"] = "HandshakeTimeout"
        records.append(saturated)
    analysis = analyze_records(records)
    assert analysis["evidence"] == "PARTIAL"
    assert analysis["system"] == "SATURATED"
    assert analysis["first_saturation"]["clients"] == 4
