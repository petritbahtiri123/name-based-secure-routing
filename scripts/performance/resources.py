from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass


PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class FILETIME(ctypes.Structure):
    _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]

    def ticks(self) -> int:
        return (self.high << 32) | self.low


class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivateUsage", ctypes.c_size_t),
    ]


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


@dataclass(frozen=True)
class ProcessResourceSample:
    pid: int
    user_cpu_ns: int
    kernel_cpu_ns: int
    working_set_bytes: int
    peak_working_set_bytes: int
    private_bytes: int
    thread_count: int


@dataclass(frozen=True)
class MemoryTrend:
    sample_count: int
    slope_bytes_per_second: float


class ResourceSeries:
    def __init__(self, *, expected_samples: int) -> None:
        if expected_samples < 2:
            raise ValueError("at least two resource samples are required")
        self.expected_samples = expected_samples
        self._samples: list[tuple[int, int]] = []

    def record(self, *, timestamp_ns: int, working_set_bytes: int) -> None:
        if self._samples and timestamp_ns <= self._samples[-1][0]:
            raise ValueError("resource timestamps must increase")
        if working_set_bytes < 0:
            raise ValueError("working set cannot be negative")
        self._samples.append((timestamp_ns, working_set_bytes))

    def finish(self) -> MemoryTrend:
        observed = len(self._samples)
        if observed != self.expected_samples:
            raise ValueError(f"expected {self.expected_samples} resource samples, observed {observed}")
        seconds = [(timestamp - self._samples[0][0]) / 1_000_000_000 for timestamp, _ in self._samples]
        memory = [value for _, value in self._samples]
        mean_seconds = sum(seconds) / observed
        mean_memory = sum(memory) / observed
        denominator = sum((value - mean_seconds) ** 2 for value in seconds)
        if denominator == 0:
            raise ValueError("resource sample duration must be positive")
        slope = sum((second - mean_seconds) * (value - mean_memory) for second, value in zip(seconds, memory, strict=True)) / denominator
        return MemoryTrend(sample_count=observed, slope_bytes_per_second=slope)


def _thread_count(pid: int) -> int:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == INVALID_HANDLE_VALUE:
        raise ctypes.WinError(ctypes.get_last_error())
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(entry)
    try:
        found = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while found:
            if entry.th32ProcessID == pid:
                return int(entry.cntThreads)
            found = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    raise ProcessLookupError(pid)


def sample_windows_process(pid: int) -> ProcessResourceSample:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not handle:
        raise ProcessLookupError(pid)
    created, exited, kernel, user = FILETIME(), FILETIME(), FILETIME(), FILETIME()
    memory = PROCESS_MEMORY_COUNTERS_EX()
    memory.cb = ctypes.sizeof(memory)
    try:
        if not kernel32.GetProcessTimes(
            handle,
            ctypes.byref(created),
            ctypes.byref(exited),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(memory), memory.cb):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel32.CloseHandle(handle)
    return ProcessResourceSample(
        pid=pid,
        user_cpu_ns=user.ticks() * 100,
        kernel_cpu_ns=kernel.ticks() * 100,
        working_set_bytes=int(memory.WorkingSetSize),
        peak_working_set_bytes=int(memory.PeakWorkingSetSize),
        private_bytes=int(memory.PrivateUsage),
        thread_count=_thread_count(pid),
    )
