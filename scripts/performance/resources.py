from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import threading
import time


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
    slope_lower_95: float
    slope_upper_95: float
    r_squared: float


@dataclass(frozen=True)
class TimedProcessResourceSample:
    role: str
    timestamp_ns: int
    pid: int
    user_cpu_ns: int
    kernel_cpu_ns: int
    cpu_percent_one_core: float
    cpu_percent_assigned: float
    working_set_bytes: int
    peak_working_set_bytes: int
    private_bytes: int
    thread_count: int


@dataclass(frozen=True)
class MemorySample:
    timestamp_ns: int
    working_set_bytes: int
    private_bytes: int
    peak_working_set_bytes: int
    cpu_percent_assigned: float
    processed_requests: int
    active_concurrency: int
    queue_depth: int
    phase: str


@dataclass(frozen=True)
class MemoryWindow:
    sample_count: int
    working_set_full: MemoryTrend
    working_set_second_half: MemoryTrend
    working_set_final_quarter: MemoryTrend
    private_bytes_full: MemoryTrend
    private_bytes_second_half: MemoryTrend
    private_bytes_final_quarter: MemoryTrend
    working_set_second_half_range: int
    private_bytes_second_half_range: int
    working_set_bytes_end: int
    private_bytes_end: int
    processed_request_delta: int
    working_set_bytes_per_request: float | None
    private_bytes_per_request: float | None


@dataclass(frozen=True)
class MemoryConclusion:
    path: str
    status: str
    reason: str


class ProcessResourceSampler:
    def __init__(
        self,
        processes: dict[str, int],
        *,
        interval_seconds: float = 1.0,
        assigned_logical_processors: int,
    ) -> None:
        if not processes or interval_seconds <= 0 or assigned_logical_processors < 1:
            raise ValueError("invalid resource sampler configuration")
        self.processes = dict(processes)
        self.interval_seconds = interval_seconds
        self.assigned_logical_processors = assigned_logical_processors
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._records: list[TimedProcessResourceSample] = []
        self._error: BaseException | None = None

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("resource sampler already started")
        self._thread = threading.Thread(target=self._run, name="nbsr-resource-sampler", daemon=True)
        self._thread.start()

    def stop(self) -> list[TimedProcessResourceSample]:
        if self._thread is None:
            raise RuntimeError("resource sampler was not started")
        self._stop.set()
        self._thread.join(timeout=max(5.0, self.interval_seconds * 2))
        if self._thread.is_alive():
            raise RuntimeError("resource sampler did not stop")
        if self._error is not None:
            raise RuntimeError("authoritative resource sample disappeared") from self._error
        if not self._records:
            raise RuntimeError("no authoritative resource samples collected")
        return list(self._records)

    def _run(self) -> None:
        previous: dict[str, tuple[int, int]] = {}
        observed_roles: set[str] = set()
        origin = time.perf_counter_ns()
        try:
            while not self._stop.is_set():
                timestamp = time.perf_counter_ns()
                for role, pid in self.processes.items():
                    sample = sample_windows_process(pid)
                    observed_roles.add(role)
                    cpu_total = sample.user_cpu_ns + sample.kernel_cpu_ns
                    prior = previous.get(role)
                    cpu_one_core = 0.0 if prior is None else 100.0 * (cpu_total - prior[1]) / (timestamp - prior[0])
                    previous[role] = (timestamp, cpu_total)
                    self._records.append(
                        TimedProcessResourceSample(
                            role=role,
                            timestamp_ns=timestamp - origin,
                            pid=pid,
                            user_cpu_ns=sample.user_cpu_ns,
                            kernel_cpu_ns=sample.kernel_cpu_ns,
                            cpu_percent_one_core=cpu_one_core,
                            cpu_percent_assigned=cpu_one_core / self.assigned_logical_processors,
                            working_set_bytes=sample.working_set_bytes,
                            peak_working_set_bytes=sample.peak_working_set_bytes,
                            private_bytes=sample.private_bytes,
                            thread_count=sample.thread_count,
                        )
                    )
                self._stop.wait(self.interval_seconds)
        except ProcessLookupError as error:
            if observed_roles != set(self.processes):
                self._error = error
        except BaseException as error:
            self._error = error


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
        intercept = mean_memory - slope * mean_seconds
        residuals = [value - (intercept + slope * second) for second, value in zip(seconds, memory, strict=True)]
        residual_sum = sum(value * value for value in residuals)
        standard_error = (residual_sum / max(1, observed - 2) / denominator) ** 0.5
        total_sum = sum((value - mean_memory) ** 2 for value in memory)
        return MemoryTrend(
            sample_count=observed,
            slope_bytes_per_second=slope,
            slope_lower_95=slope - 1.96 * standard_error,
            slope_upper_95=slope + 1.96 * standard_error,
            r_squared=1.0 - residual_sum / total_sum if total_sum else 1.0,
        )


def _trend(samples: list[MemorySample], field: str) -> MemoryTrend:
    series = ResourceSeries(expected_samples=len(samples))
    for sample in samples:
        series.record(timestamp_ns=sample.timestamp_ns, working_set_bytes=int(getattr(sample, field)))
    return series.finish()


def analyze_memory_window(
    samples: list[MemorySample], *, warmup_end_ns: int, expected_cadence_ns: int,
) -> MemoryWindow:
    if expected_cadence_ns <= 0:
        raise ValueError("memory sample cadence must be positive")
    steady = [sample for sample in samples if sample.timestamp_ns >= warmup_end_ns and sample.phase == "steady"]
    for previous, current in zip(steady, steady[1:], strict=False):
        gap = current.timestamp_ns - previous.timestamp_ns
        if gap <= 0 or gap > expected_cadence_ns * 3 // 2:
            raise ValueError(f"memory sample cadence gap: {gap} ns")
    if len(steady) < 4:
        raise ValueError("at least four post-warm-up memory samples are required")
    second_half = steady[len(steady) // 2 :]
    final_quarter = steady[3 * len(steady) // 4 :]
    if len(final_quarter) < 2:
        final_quarter = steady[-2:]
    request_delta = steady[-1].processed_requests - steady[0].processed_requests
    working_delta = steady[-1].working_set_bytes - steady[0].working_set_bytes
    private_delta = steady[-1].private_bytes - steady[0].private_bytes
    return MemoryWindow(
        sample_count=len(steady),
        working_set_full=_trend(steady, "working_set_bytes"),
        working_set_second_half=_trend(second_half, "working_set_bytes"),
        working_set_final_quarter=_trend(final_quarter, "working_set_bytes"),
        private_bytes_full=_trend(steady, "private_bytes"),
        private_bytes_second_half=_trend(second_half, "private_bytes"),
        private_bytes_final_quarter=_trend(final_quarter, "private_bytes"),
        working_set_second_half_range=max(item.working_set_bytes for item in second_half)
        - min(item.working_set_bytes for item in second_half),
        private_bytes_second_half_range=max(item.private_bytes for item in second_half)
        - min(item.private_bytes for item in second_half),
        working_set_bytes_end=steady[-1].working_set_bytes,
        private_bytes_end=steady[-1].private_bytes,
        processed_request_delta=request_delta,
        working_set_bytes_per_request=working_delta / request_delta if request_delta > 0 else None,
        private_bytes_per_request=private_delta / request_delta if request_delta > 0 else None,
    )


def _bounded(window: MemoryWindow) -> bool:
    return (
        window.working_set_second_half_range <= max(1.0, window.working_set_bytes_end * 0.02)
        and window.private_bytes_second_half_range <= max(1.0, window.private_bytes_end * 0.02)
    )


def _sustained_growth(window: MemoryWindow) -> bool:
    trends = (window.working_set_full, window.working_set_final_quarter, window.private_bytes_full, window.private_bytes_final_quarter)
    return (
        window.processed_request_delta > 0
        and window.working_set_bytes_per_request is not None
        and window.working_set_bytes_per_request > 0
        and window.private_bytes_per_request is not None
        and window.private_bytes_per_request > 0
        and all(trend.slope_lower_95 > 0 and trend.r_squared >= 0.8 for trend in trends)
    )


def classify_memory_stability(path: str, load_results: dict[int, MemoryWindow]) -> MemoryConclusion:
    if set(load_results) != {50, 75}:
        return MemoryConclusion(path, "INCONCLUSIVE", "both 50% and 75% stable-load runs are required")
    windows = [load_results[50], load_results[75]]
    if all(_bounded(window) for window in windows):
        return MemoryConclusion(path, "PASS", "both stable loads show bounded post-warm-up retention")
    if all(_sustained_growth(window) for window in windows):
        return MemoryConclusion(path, "FAIL", "both stable loads show sustained request-correlated growth")
    return MemoryConclusion(path, "INCONCLUSIVE", "post-warm-up behavior does not reproduce as bounded or sustained growth")


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
