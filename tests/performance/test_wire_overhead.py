from __future__ import annotations

import json
import os
import socket
import threading
import time

import pytest

from scripts.performance.wire_overhead import UdpFlowCounter, analyze_pairs, send_phase
from scripts.run_b1_wire_overhead import _render_summary, failure_record, workload_cells


def _quic_datagram(payload: bytes) -> bytes:
    return b"\xc0" + b"\x00" * (1199 - len(payload)) + payload


def _echo_server() -> tuple[socket.socket, threading.Thread]:
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))

    def echo() -> None:
        while True:
            try:
                payload, peer = server.recvfrom(65_535)
            except OSError:
                return
            server.sendto(payload, peer)

    thread = threading.Thread(target=echo, daemon=True)
    thread.start()
    return server, thread


def test_udp_flow_counter_forwards_exact_bytes_and_separates_phases() -> None:
    server, thread = _echo_server()
    counter = UdpFlowCounter(server.getsockname())
    counter.start()
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client.settimeout(2)
    try:
        counter.authorize_client_process(os.getpid())
        setup_payload = _quic_datagram(b"setup")
        client.sendto(setup_payload, counter.relay_endpoint)
        assert client.recvfrom(2048)[0] == setup_payload
        setup = send_phase(counter.control_endpoint, "setup-complete")
        assert setup == {
            "client_to_server": {"bytes": 1200, "packets": 1},
            "server_to_client": {"bytes": 1200, "packets": 1},
        }

        client.sendto(b"warmup-is-excluded", counter.relay_endpoint)
        assert client.recvfrom(64)[0] == b"warmup-is-excluded"
        send_phase(counter.control_endpoint, "measurement-start")

        for payload in (b"one", b"twenty-bytes-payload"):
            client.sendto(payload, counter.relay_endpoint)
            assert client.recvfrom(64)[0] == payload
        established = send_phase(counter.control_endpoint, "measurement-stop")
        assert established == {
            "client_to_server": {"bytes": 23, "packets": 2},
            "server_to_client": {"bytes": 23, "packets": 2},
        }
    finally:
        client.close()
        counter.close()
        server.close()
        thread.join(timeout=2)


def test_udp_flow_counter_rejects_an_unrelated_source() -> None:
    server, thread = _echo_server()
    counter = UdpFlowCounter(server.getsockname())
    counter.start()
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    unrelated = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client.settimeout(2)
    unrelated.settimeout(0.1)
    try:
        counter.authorize_client_process(os.getpid())
        owner = _quic_datagram(b"owner")
        client.sendto(owner, counter.relay_endpoint)
        assert client.recvfrom(2048)[0] == owner
        unrelated.sendto(b"contamination", counter.relay_endpoint)
        with pytest.raises(TimeoutError):
            unrelated.recvfrom(64)
        result = counter.result()
        assert result["rejected_datagrams"] == 1
        assert result["phases"]["setup"]["client_to_server"] == {"bytes": 1200, "packets": 1}
    finally:
        client.close()
        unrelated.close()
        counter.close()
        server.close()
        thread.join(timeout=2)


def test_udp_flow_counter_rejects_a_first_datagram_from_an_unauthorized_process() -> None:
    server, thread = _echo_server()
    counter = UdpFlowCounter(server.getsockname())
    counter.start()
    unrelated = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    unrelated.settimeout(0.1)
    try:
        counter.authorize_client_process(os.getpid() + 1_000_000)
        unrelated.sendto(_quic_datagram(b"race"), counter.relay_endpoint)
        with pytest.raises(TimeoutError):
            unrelated.recvfrom(2048)
        assert counter.result()["rejected_datagrams"] == 1
    finally:
        unrelated.close()
        counter.close()
        server.close()
        thread.join(timeout=2)


def _record(path: str, repeat: int, measured_bytes: int, packets: int) -> dict:
    return {
        "path": path,
        "repeat": repeat,
        "payload_bytes": 1024,
        "streams": 64,
        "operations_per_stream": 10,
        "completed_operations": 640,
        "expected_operations": 640,
        "errors": 0,
        "timeouts": 0,
        "capture_method": "isolated-udp-relay",
        "measured_unit": "UDP payload bytes and UDP datagrams",
        "benchmark_build": "cargo release with benchmark-harness feature",
        "model": "one-outstanding-per-stream",
        "warmup_seconds": 3.0,
        "phase_semantics": "setup then excluded warmup then established fixed operations without teardown",
        "application_bytes": 1_310_720,
        "application_bytes_definition": "aggregate request plus response payload bytes",
        "setup": {
            "client_to_server": {"bytes": 100, "packets": 2},
            "server_to_client": {"bytes": 120, "packets": 2},
        },
        "established": {
            "client_to_server": {"bytes": measured_bytes // 2, "packets": packets // 2},
            "server_to_client": {"bytes": measured_bytes // 2, "packets": packets // 2},
        },
    }


def test_analyze_pairs_derives_incremental_udp_payload_overhead() -> None:
    records = []
    for repeat, direct, nbsr in ((1, 1_400_000, 1_470_000), (2, 1_402_000, 1_472_100), (3, 1_398_000, 1_467_900)):
        records.extend((_record("direct", repeat, direct, 1400), _record("nbsr", repeat, nbsr, 1470)))

    analysis = analyze_pairs(records)

    assert analysis["classification"] == "PASS"
    assert analysis["application_bytes_definition"] == "aggregate request plus response payload bytes"
    cell = analysis["cells"][0]
    assert cell["valid_pairs"] == 3
    assert cell["median_direct_measured_udp_payload_bytes"] == 1_400_000
    assert cell["median_nbsr_measured_udp_payload_bytes"] == 1_470_000
    assert cell["median_incremental_bytes"] == 70_000
    assert cell["median_incremental_overhead_percent"] == 5.0
    assert cell["representative_pair"] == {
        "repeat": 2,
        "direct_measured_udp_payload_bytes": 1_402_000,
        "nbsr_measured_udp_payload_bytes": 1_472_100,
        "incremental_bytes": 70_100,
        "incremental_overhead_percent": 5.0,
    }
    assert cell["median_direct_setup_udp_payload_bytes"] == 220
    assert cell["median_nbsr_setup_udp_payload_bytes"] == 220
    assert cell["median_setup_incremental_bytes"] == 0
    assert cell["median_setup_incremental_overhead_percent"] == 0.0
    assert cell["direct_bytes_per_application_byte"] == pytest.approx(1_400_000 / 1_310_720)
    assert cell["nbsr_packets_per_operation"] == pytest.approx(1470 / 640)
    assert cell["median_direct_derived_ipv4_udp_bytes"] == 1_400_000 + 1400 * 28
    assert cell["median_nbsr_derived_ipv4_udp_bytes"] == 1_470_000 + 1470 * 28


def test_analyze_pairs_rejects_mismatched_or_failed_workloads() -> None:
    direct = _record("direct", 1, 1000, 10)
    nbsr = _record("nbsr", 1, 1100, 11)
    nbsr["completed_operations"] = 639
    failed = _record("nbsr", 2, 1100, 11)
    failed["errors"] = 1

    analysis = analyze_pairs([direct, nbsr, _record("direct", 2, 1000, 10), failed])

    assert analysis["classification"] == "INCONCLUSIVE"
    assert analysis["cells"][0]["valid_pairs"] == 0
    assert {item["reason"] for item in analysis["invalid_pairs"]} == {
        "completed operations differ",
        "errors or timeouts present",
    }


def test_analyze_pairs_rejects_incompatible_measurement_semantics() -> None:
    direct = _record("direct", 1, 1000, 10)
    nbsr = _record("nbsr", 1, 1100, 11)
    nbsr["phase_semantics"] = "different"

    analysis = analyze_pairs([direct, nbsr])

    assert analysis["cells"][0]["valid_pairs"] == 0
    assert analysis["invalid_pairs"][0]["reason"] == "incompatible measurement semantics: phase_semantics"


def test_failure_record_preserves_invalid_repeat_metadata() -> None:
    record = failure_record(
        path="nbsr",
        cell={"payload_bytes": 1024, "streams": 64, "operations_per_stream": 10},
        repeat=2,
        warmup_seconds=3.0,
        error=RuntimeError("server failed"),
    )

    assert record["path"] == "nbsr"
    assert record["repeat"] == 2
    assert record["errors"] == 1
    assert record["status"] == "invalid"
    assert record["failure"] == "RuntimeError: server failed"


def test_summary_preserves_an_inconclusive_cell_without_a_valid_pair() -> None:
    direct = _record("direct", 1, 1000, 10)
    failed = failure_record(
        path="nbsr",
        cell={"payload_bytes": 1024, "streams": 64, "operations_per_stream": 10},
        repeat=1,
        warmup_seconds=3.0,
        error=RuntimeError("failed"),
    )
    analysis = analyze_pairs([direct, failed])

    summary = _render_summary(
        analysis,
        {"repository_sha": "abc", "os": "Windows", "cpu": "test", "memory_bytes": 1},
        "test command",
    )

    assert "INCONCLUSIVE" in summary
    assert "no valid pair" in summary


def test_analyze_pairs_requires_three_repeats_and_classifies_noise_overlap() -> None:
    records = []
    for repeat, direct, nbsr in ((1, 1000, 1010), (2, 1020, 1000), (3, 990, 1015)):
        records.extend((_record("direct", repeat, direct, 10), _record("nbsr", repeat, nbsr, 10)))

    analysis = analyze_pairs(records)

    assert analysis["classification"] == "INCONCLUSIVE"
    assert analysis["cells"][0]["stability"] == "difference-within-pair-dispersion"


def test_counter_result_is_json_serializable() -> None:
    server, thread = _echo_server()
    counter = UdpFlowCounter(server.getsockname())
    counter.start()
    try:
        counter.authorize_client_process(os.getpid())
        json.dumps(counter.result())
    finally:
        counter.close()
        server.close()
        thread.join(timeout=2)


def test_authoritative_workloads_use_only_previously_stable_cells() -> None:
    assert workload_cells(smoke=False) == [
        {"payload_bytes": 1024, "streams": 64, "operations_per_stream": 10_000},
        {"payload_bytes": 16_384, "streams": 8, "operations_per_stream": 10_000},
    ]
    assert workload_cells(smoke=True) == [
        {"payload_bytes": 1024, "streams": 1, "operations_per_stream": 10}
    ]
