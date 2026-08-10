from __future__ import annotations

from collections import deque
import ctypes
from ctypes import wintypes
import gzip
import hashlib
import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import threading
import time
from typing import Any, Iterable, TextIO


TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


class DurableEvidenceOverflow(RuntimeError):
    pass


class DurableNdjsonWriter:
    def __init__(
        self, path: Path, *, capacity: int, flush_records: int, flush_interval_seconds: float,
    ) -> None:
        if capacity < 1 or flush_records < 1 or flush_records > capacity:
            raise ValueError("invalid durable evidence buffer bounds")
        if flush_interval_seconds <= 0:
            raise ValueError("flush interval must be positive")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.capacity = capacity
        self.flush_records = flush_records
        self.flush_interval_seconds = flush_interval_seconds
        self._pending: deque[str] = deque()
        self._handle = path.open("w", encoding="utf-8", newline="\n")
        self._last_flush = time.monotonic()
        self.written = 0

    def append(self, document: dict[str, Any]) -> None:
        if len(self._pending) >= self.capacity:
            raise DurableEvidenceOverflow(f"durable evidence buffer exceeded capacity {self.capacity}")
        self._pending.append(json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n")
        if len(self._pending) >= self.flush_records or time.monotonic() - self._last_flush >= self.flush_interval_seconds:
            self.flush()

    def flush_if_due(self) -> None:
        if self._pending and time.monotonic() - self._last_flush >= self.flush_interval_seconds:
            self.flush()

    def flush(self) -> None:
        while self._pending:
            self._handle.write(self._pending.popleft())
            self.written += 1
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self._last_flush = time.monotonic()

    def close(self) -> None:
        if self._handle.closed:
            return
        try:
            self.flush()
        finally:
            self._handle.close()


def _windows_process_table() -> dict[int, int]:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == INVALID_HANDLE_VALUE:
        raise ctypes.WinError(ctypes.get_last_error())
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(entry)
    table: dict[int, int] = {}
    try:
        found = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while found:
            table[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
            found = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return table


def _descendants(root_pid: int, table: dict[int, int]) -> list[int]:
    found: list[int] = []
    frontier = [root_pid]
    while frontier:
        parent = frontier.pop()
        children = sorted(pid for pid, parent_pid in table.items() if parent_pid == parent and pid not in found)
        found.extend(children)
        frontier.extend(children)
    return found


def _windows_process_active(pid: int) -> bool:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    exit_code = wintypes.DWORD()
    try:
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _terminate_process_tree(process: subprocess.Popen[str]) -> tuple[list[int], bool]:
    if os.name == "nt":
        table = _windows_process_table()
        process_ids = [process.pid, *_descendants(process.pid, table)]
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True, check=False, text=True,
        )
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and any(_windows_process_active(pid) for pid in process_ids):
            time.sleep(0.02)
        return process_ids, not any(_windows_process_active(pid) for pid in process_ids)
    process_ids = [process.pid]
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=5)
    return process_ids, process.poll() is not None


def _read_lines(stream: TextIO, events: queue.Queue[object], stop: object) -> None:
    try:
        for line in stream:
            events.put(line)
    except BaseException as error:
        events.put(error)
    finally:
        events.put(stop)


def _close_writers(writers: Iterable[DurableNdjsonWriter]) -> list[BaseException]:
    errors: list[BaseException] = []
    for writer in writers:
        try:
            writer.close()
        except BaseException as error:
            errors.append(error)
    return errors


def finalize_completed_request_journal(path: Path) -> dict[str, Any]:
    compressed = path.with_suffix(path.suffix + ".gz")
    if compressed.exists():
        raise FileExistsError(compressed)
    digest = hashlib.sha256()
    uncompressed_bytes = 0
    with path.open("rb") as source, compressed.open("xb") as target:
        with gzip.GzipFile(filename="", mode="wb", fileobj=target, mtime=0) as archive:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
                uncompressed_bytes += len(chunk)
                archive.write(chunk)
        target.flush()
        os.fsync(target.fileno())
    verified = hashlib.sha256()
    verified_bytes = 0
    with gzip.open(compressed, "rb") as archive:
        while chunk := archive.read(1024 * 1024):
            verified.update(chunk)
            verified_bytes += len(chunk)
    if verified.digest() != digest.digest() or verified_bytes != uncompressed_bytes:
        raise RuntimeError("completed request journal compression verification failed")
    path.unlink()
    return {
        "path": compressed.name,
        "uncompressed_bytes": uncompressed_bytes,
        "uncompressed_sha256": digest.hexdigest(),
    }


def run_durable_memory_child(
    command: list[str], *, output: Path, timeout_seconds: float, offered_requests: int,
    authoritative_run: bool = True,
    buffer_capacity: int = 1024, flush_records: int = 128, flush_interval_seconds: float = 1.0,
    cwd: Path | None = None,
) -> dict[str, Any]:
    if timeout_seconds <= 0 or offered_requests < 0:
        raise ValueError("invalid durable memory run limits")
    output.mkdir(parents=True, exist_ok=False)
    stderr_path = output / "stderr.log"
    writers = {
        "request": DurableNdjsonWriter(
            output / "raw.ndjson", capacity=buffer_capacity, flush_records=flush_records,
            flush_interval_seconds=flush_interval_seconds,
        ),
        "resource": DurableNdjsonWriter(
            output / "resources.ndjson", capacity=buffer_capacity, flush_records=flush_records,
            flush_interval_seconds=flush_interval_seconds,
        ),
        "runtime": DurableNdjsonWriter(
            output / "runtime.ndjson", capacity=buffer_capacity, flush_records=flush_records,
            flush_interval_seconds=flush_interval_seconds,
        ),
        "diagnostic": DurableNdjsonWriter(
            output / "diagnostics.ndjson", capacity=buffer_capacity, flush_records=flush_records,
            flush_interval_seconds=flush_interval_seconds,
        ),
    }
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    start_new_session = os.name != "nt"
    terminal_state = "failed"
    cleanup_verified = True
    terminated_process_ids: list[int] = []
    started = completed = failed = 0
    runner_error: str | None = None
    child_return_code: int | None = None
    process: subprocess.Popen[str] | None = None
    stop = object()
    events: queue.Queue[object] = queue.Queue(maxsize=buffer_capacity)
    reader: threading.Thread | None = None
    try:
        with stderr_path.open("w", encoding="utf-8", newline="\n") as stderr:
            process = subprocess.Popen(
                command, cwd=cwd, stdout=subprocess.PIPE, stderr=stderr, text=True,
                encoding="utf-8", creationflags=creationflags, start_new_session=start_new_session,
            )
            if process.stdout is None:
                raise RuntimeError("durable memory child stdout unavailable")
            reader = threading.Thread(target=_read_lines, args=(process.stdout, events, stop), daemon=True)
            reader.start()
            deadline = time.monotonic() + timeout_seconds
            stream_closed = False
            while not stream_closed:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    terminal_state = "timed_out"
                    terminated_process_ids, cleanup_verified = _terminate_process_tree(process)
                    break
                try:
                    event = events.get(timeout=min(0.05, remaining))
                except queue.Empty:
                    for writer in writers.values():
                        writer.flush_if_due()
                    if process.poll() is not None and reader is not None and not reader.is_alive():
                        stream_closed = True
                    continue
                if event is stop:
                    stream_closed = True
                    continue
                if isinstance(event, BaseException):
                    raise RuntimeError("durable child output reader failed") from event
                document = json.loads(str(event))
                event_type = document.get("event")
                if event_type not in writers:
                    raise ValueError(f"unknown durable evidence event {event_type!r}")
                record = dict(document)
                record.pop("event")
                writers[str(event_type)].append(record)
                if event_type == "request":
                    if record.get("started") is not True:
                        raise ValueError("request evidence omitted started state")
                    started += 1
                    if record.get("result") == "completed":
                        completed += 1
                    elif record.get("result") == "failed":
                        failed += 1
                    else:
                        raise ValueError("request evidence has no terminal result")
            if terminal_state != "timed_out":
                return_code = process.wait(timeout=5)
                child_return_code = return_code
                terminal_state = "completed" if return_code == 0 else "failed"
    except BaseException as error:
        runner_error = f"{type(error).__name__}: {error}"
        if process is not None and process.poll() is None:
            terminated_process_ids, cleanup_verified = _terminate_process_tree(process)
        if process is not None:
            child_return_code = process.returncode
        terminal_state = "failed"
    finally:
        close_errors = _close_writers(writers.values())
        if close_errors and runner_error is None:
            runner_error = f"{type(close_errors[0]).__name__}: {close_errors[0]}"
            terminal_state = "failed"
        if reader is not None:
            reader.join(timeout=1)

    persisted = writers["request"].written
    if process is not None and child_return_code is None:
        child_return_code = process.returncode
    timed_out = max(0, offered_requests - started) if terminal_state == "timed_out" else 0
    reconciled = started == completed + failed and persisted == started and started <= offered_requests
    if terminal_state == "completed":
        reconciled = reconciled and started == offered_requests
    authoritative = (
        authoritative_run and terminal_state == "completed" and reconciled
        and failed == 0 and cleanup_verified
    )
    request_evidence = (
        finalize_completed_request_journal(writers["request"].path)
        if terminal_state == "completed"
        else {
            "path": writers["request"].path.name,
            "uncompressed_bytes": writers["request"].path.stat().st_size,
            "uncompressed_sha256": hashlib.sha256(writers["request"].path.read_bytes()).hexdigest(),
        }
    )
    manifest: dict[str, Any] = {
        "schema": "nbsr-durable-memory-terminal-v1",
        "authoritative_run": authoritative_run,
        "terminal_state": terminal_state,
        "child_return_code": child_return_code,
        "partial_but_durable": terminal_state != "completed" and any(
            writer.written > 0 for writer in writers.values()
        ),
        "authoritative_pass_eligible": authoritative,
        "cleanup_verified": cleanup_verified,
        "terminated_process_ids": terminated_process_ids,
        "counters_reconciled": reconciled,
        "counters": {
            "offered": offered_requests,
            "started": started,
            "completed": completed,
            "failed": failed,
            "timed_out": timed_out,
            "persisted": persisted,
        },
        "series_counts": {
            "requests": persisted,
            "resources": writers["resource"].written,
            "runtime": writers["runtime"].written,
            "diagnostics": writers["diagnostic"].written,
        },
        "runner_error": runner_error,
        "request_evidence": request_evidence,
    }
    manifest_path = output / "terminal-manifest.json"
    with manifest_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return manifest
