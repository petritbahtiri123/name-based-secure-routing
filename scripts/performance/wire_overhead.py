"""Isolated UDP-flow accounting and Direct/NBSR wire-overhead analysis."""

from __future__ import annotations

from collections.abc import Iterable
import json
import socket
import statistics
import subprocess
import threading
from typing import Any


def _empty_counters() -> dict[str, dict[str, int]]:
    return {
        "client_to_server": {"bytes": 0, "packets": 0},
        "server_to_client": {"bytes": 0, "packets": 0},
    }


def _copy_counters(value: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
    return {direction: dict(counters) for direction, counters in value.items()}


def _udp_owner_pid(peer: tuple[str, int]) -> int | None:
    result = subprocess.run(
        ["netstat", "-ano", "-p", "udp"],
        capture_output=True,
        text=True,
        check=False,
        timeout=2,
    )
    for line in result.stdout.splitlines():
        columns = line.split()
        if len(columns) >= 4 and columns[0] == "UDP" and columns[1].rsplit(":", 1)[-1] == str(peer[1]):
            return int(columns[-1])
    return None


class UdpFlowCounter:
    """Forward and count exactly one loopback UDP client/server flow."""

    def __init__(self, server: tuple[str, int]) -> None:
        self._server = (str(server[0]), int(server[1]))
        self._udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._udp.bind(("127.0.0.1", 0))
        self._udp.settimeout(0.05)
        self._control = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._control.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._control.bind(("127.0.0.1", 0))
        self._control.listen(4)
        self._control.settimeout(0.05)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._client: tuple[str, int] | None = None
        self._expected_client_pid: int | None = None
        self._phase = "setup"
        self._current = _empty_counters()
        self._phases = {"setup": _empty_counters(), "established": _empty_counters()}
        self._rejected = 0
        self._threads: list[threading.Thread] = []

    @property
    def relay_endpoint(self) -> tuple[str, int]:
        return self._udp.getsockname()

    @property
    def control_endpoint(self) -> tuple[str, int]:
        return self._control.getsockname()

    def start(self) -> None:
        if self._threads:
            raise RuntimeError("counter already started")
        self._threads = [
            threading.Thread(target=self._relay_loop, name="nbsr-b1-udp-relay", daemon=True),
            threading.Thread(target=self._control_loop, name="nbsr-b1-counter-control", daemon=True),
        ]
        for thread in self._threads:
            thread.start()

    def authorize_client_process(self, pid: int) -> None:
        if pid <= 0:
            raise ValueError("client PID must be positive")
        with self._lock:
            if self._client is not None or self._expected_client_pid is not None:
                raise RuntimeError("client ownership already established")
            self._expected_client_pid = pid

    def _relay_loop(self) -> None:
        while not self._stop.is_set():
            try:
                payload, peer = self._udp.recvfrom(65_535)
            except TimeoutError:
                continue
            except OSError:
                return
            destination: tuple[str, int] | None = None
            direction = ""
            with self._lock:
                if peer == self._server:
                    if self._client is None:
                        self._rejected += 1
                    else:
                        destination = self._client
                        direction = "server_to_client"
                elif self._client is None:
                    if self._expected_client_pid is not None and _udp_owner_pid(peer) == self._expected_client_pid:
                        self._client = peer
                        destination = self._server
                        direction = "client_to_server"
                    else:
                        self._rejected += 1
                elif peer == self._client:
                    destination = self._server
                    direction = "client_to_server"
                else:
                    self._rejected += 1
                if destination is not None and self._phase in {"setup", "established"}:
                    self._current[direction]["bytes"] += len(payload)
                    self._current[direction]["packets"] += 1
            if destination is not None:
                try:
                    self._udp.sendto(payload, destination)
                except OSError:
                    return

    def _control_loop(self) -> None:
        while not self._stop.is_set():
            try:
                connection, _ = self._control.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            with connection:
                connection.settimeout(2)
                try:
                    phase = connection.recv(128).decode("ascii").strip()
                    snapshot = self._transition(phase)
                    response = {"status": "ok", "phase": phase, "counters": snapshot}
                except (OSError, UnicodeError, ValueError) as error:
                    response = {"status": "error", "error": str(error)}
                connection.sendall((json.dumps(response, separators=(",", ":")) + "\n").encode("ascii"))

    def _transition(self, phase: str) -> dict[str, dict[str, int]]:
        with self._lock:
            if phase == "setup-complete" and self._phase == "setup":
                self._phases["setup"] = _copy_counters(self._current)
                snapshot = _copy_counters(self._current)
                self._current = _empty_counters()
                self._phase = "warmup"
                return snapshot
            if phase == "measurement-start" and self._phase == "warmup":
                self._current = _empty_counters()
                self._phase = "established"
                return _copy_counters(self._current)
            if phase == "measurement-stop" and self._phase == "established":
                self._phases["established"] = _copy_counters(self._current)
                snapshot = _copy_counters(self._current)
                self._phase = "stopped"
                return snapshot
            raise ValueError(f"invalid phase transition: {self._phase} -> {phase}")

    def result(self) -> dict[str, Any]:
        with self._lock:
            phases = {name: _copy_counters(value) for name, value in self._phases.items()}
            if self._phase in phases:
                phases[self._phase] = _copy_counters(self._current)
            return {
                "schema": "nbsr-b1-udp-flow-counter-v1",
                "capture_method": "isolated-udp-relay",
                "measured_unit": "UDP payload bytes and UDP datagrams",
                "client_ownership": "OS UDP endpoint ownership must match the authorized benchmark client PID",
                "relay_endpoint": f"{self.relay_endpoint[0]}:{self.relay_endpoint[1]}",
                "server_endpoint": f"{self._server[0]}:{self._server[1]}",
                "rejected_datagrams": self._rejected,
                "phases": phases,
            }

    def close(self) -> None:
        self._stop.set()
        self._udp.close()
        self._control.close()
        for thread in self._threads:
            thread.join(timeout=2)


def send_phase(endpoint: tuple[str, int], phase: str) -> dict[str, dict[str, int]]:
    with socket.create_connection(endpoint, timeout=2) as connection:
        connection.sendall((phase + "\n").encode("ascii"))
        response = b""
        while not response.endswith(b"\n"):
            chunk = connection.recv(4096)
            if not chunk:
                break
            response += chunk
    decoded = json.loads(response)
    if decoded.get("status") != "ok":
        raise RuntimeError(decoded.get("error", "counter control failed"))
    return decoded["counters"]


def _total(phase: dict[str, dict[str, int]], field: str) -> int:
    return int(phase["client_to_server"][field]) + int(phase["server_to_client"][field])


def _median(values: Iterable[int | float]) -> float:
    return statistics.median(values)


def analyze_pairs(records: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[tuple[int, int, int], dict[int, dict[str, dict[str, Any]]]] = {}
    for record in records:
        key = (int(record["payload_bytes"]), int(record["streams"]), int(record["operations_per_stream"]))
        grouped.setdefault(key, {}).setdefault(int(record["repeat"]), {})[str(record["path"])] = record

    cells = []
    invalid_pairs = []
    for (payload, streams, operations_per_stream), repeats in sorted(grouped.items()):
        valid: list[tuple[int, dict[str, Any], dict[str, Any]]] = []
        for repeat, paths in sorted(repeats.items()):
            if set(paths) != {"direct", "nbsr"}:
                invalid_pairs.append({"payload_bytes": payload, "streams": streams, "repeat": repeat, "reason": "missing Direct/NBSR peer"})
                continue
            direct, nbsr = paths["direct"], paths["nbsr"]
            if any(int(item.get("errors", 0)) or int(item.get("timeouts", 0)) for item in (direct, nbsr)):
                invalid_pairs.append({"payload_bytes": payload, "streams": streams, "repeat": repeat, "reason": "errors or timeouts present"})
                continue
            if int(direct["completed_operations"]) != int(nbsr["completed_operations"]):
                invalid_pairs.append({"payload_bytes": payload, "streams": streams, "repeat": repeat, "reason": "completed operations differ"})
                continue
            compatibility_fields = (
                "expected_operations",
                "capture_method",
                "measured_unit",
                "benchmark_build",
                "model",
                "warmup_seconds",
                "phase_semantics",
                "application_bytes",
                "application_bytes_definition",
            )
            mismatch = next(
                (field for field in compatibility_fields if direct.get(field) != nbsr.get(field)),
                None,
            )
            if mismatch is not None:
                invalid_pairs.append(
                    {
                        "payload_bytes": payload,
                        "streams": streams,
                        "repeat": repeat,
                        "reason": f"incompatible measurement semantics: {mismatch}",
                    }
                )
                continue
            expected = streams * operations_per_stream
            if any(int(item.get("completed_operations", -1)) != expected for item in (direct, nbsr)):
                invalid_pairs.append(
                    {"payload_bytes": payload, "streams": streams, "repeat": repeat, "reason": "expected operation count not met"}
                )
                continue
            valid.append((repeat, direct, nbsr))

        direct_bytes = [_total(direct["established"], "bytes") for _, direct, _ in valid]
        nbsr_bytes = [_total(nbsr["established"], "bytes") for _, _, nbsr in valid]
        direct_packets = [_total(direct["established"], "packets") for _, direct, _ in valid]
        nbsr_packets = [_total(nbsr["established"], "packets") for _, _, nbsr in valid]
        direct_setup_bytes = [_total(direct["setup"], "bytes") for _, direct, _ in valid]
        nbsr_setup_bytes = [_total(nbsr["setup"], "bytes") for _, _, nbsr in valid]
        direct_setup_packets = [_total(direct["setup"], "packets") for _, direct, _ in valid]
        nbsr_setup_packets = [_total(nbsr["setup"], "packets") for _, _, nbsr in valid]
        deltas = [nbsr - direct for direct, nbsr in zip(direct_bytes, nbsr_bytes, strict=True)]
        enough = len(valid) >= 3
        dispersion = max(deltas) - min(deltas) if deltas else 0
        median_delta = _median(deltas) if deltas else 0
        stable = enough and dispersion < abs(median_delta) if median_delta else enough and dispersion == 0
        completed = int(valid[0][1]["completed_operations"]) if valid else streams * operations_per_stream
        application_bytes = completed * payload * 2
        median_direct = _median(direct_bytes) if direct_bytes else 0
        median_nbsr = _median(nbsr_bytes) if nbsr_bytes else 0
        paired = sorted(
            (
                {
                    "repeat": repeat,
                    "direct_measured_udp_payload_bytes": direct_bytes[index],
                    "nbsr_measured_udp_payload_bytes": nbsr_bytes[index],
                    "incremental_bytes": deltas[index],
                    "incremental_overhead_percent": 100 * deltas[index] / direct_bytes[index],
                }
                for index, (repeat, _, _) in enumerate(valid)
            ),
            key=lambda item: (item["incremental_overhead_percent"], item["repeat"]),
        )
        representative = paired[len(paired) // 2] if paired else None
        cell = {
            "payload_bytes": payload,
            "streams": streams,
            "operations_per_stream": operations_per_stream,
            "completed_operations": completed,
            "valid_pairs": len(valid),
            "invalid_pairs": len(repeats) - len(valid),
            "stability": "stable" if stable else ("insufficient-valid-repeats" if not enough else "difference-within-pair-dispersion"),
            "pair_incremental_bytes": deltas,
            "pair_incremental_overhead_percent": [100 * delta / direct for delta, direct in zip(deltas, direct_bytes, strict=True)],
            "median_direct_measured_udp_payload_bytes": median_direct,
            "median_nbsr_measured_udp_payload_bytes": median_nbsr,
            "median_direct_packets": _median(direct_packets) if direct_packets else 0,
            "median_nbsr_packets": _median(nbsr_packets) if nbsr_packets else 0,
            "median_direct_derived_ipv4_udp_bytes": (
                median_direct + _median(direct_packets) * 28 if direct_packets else 0
            ),
            "median_nbsr_derived_ipv4_udp_bytes": (
                median_nbsr + _median(nbsr_packets) * 28 if nbsr_packets else 0
            ),
            "median_direct_setup_udp_payload_bytes": _median(direct_setup_bytes) if direct_setup_bytes else 0,
            "median_nbsr_setup_udp_payload_bytes": _median(nbsr_setup_bytes) if nbsr_setup_bytes else 0,
            "median_setup_incremental_bytes": (
                _median(nbsr_setup_bytes) - _median(direct_setup_bytes)
                if direct_setup_bytes
                else None
            ),
            "median_setup_incremental_overhead_percent": (
                100 * (_median(nbsr_setup_bytes) - _median(direct_setup_bytes)) / _median(direct_setup_bytes)
                if direct_setup_bytes and _median(direct_setup_bytes)
                else None
            ),
            "median_direct_setup_packets": _median(direct_setup_packets) if direct_setup_packets else 0,
            "median_nbsr_setup_packets": _median(nbsr_setup_packets) if nbsr_setup_packets else 0,
            "median_incremental_bytes": median_delta,
            "median_incremental_overhead_percent": 100 * median_delta / median_direct if median_direct else None,
            "representative_pair": representative,
            "direct_bytes_per_application_byte": median_direct / application_bytes if application_bytes else None,
            "nbsr_bytes_per_application_byte": median_nbsr / application_bytes if application_bytes else None,
            "direct_packets_per_operation": (_median(direct_packets) / completed) if completed and direct_packets else None,
            "nbsr_packets_per_operation": (_median(nbsr_packets) / completed) if completed and nbsr_packets else None,
            "packet_count_delta": (_median(nbsr_packets) - _median(direct_packets)) if direct_packets else None,
        }
        cells.append(cell)

    accepted = bool(cells) and all(cell["valid_pairs"] >= 3 and cell["stability"] == "stable" for cell in cells)
    return {
        "schema": "nbsr-b1-wire-overhead-analysis-v1",
        "classification": "PASS" if accepted else "INCONCLUSIVE",
        "measurement": "UDP payload bytes and UDP datagrams forwarded by an isolated single-flow relay",
        "application_bytes_definition": "aggregate request plus response payload bytes",
        "physical_l2_bytes": "not measured",
        "retransmissions": "not measurable with the available non-privileged instrumentation",
        "cells": cells,
        "invalid_pairs": invalid_pairs,
    }
