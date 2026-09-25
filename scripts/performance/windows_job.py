"""Owned Windows benchmark descendants; no system-wide policy changes."""
import ctypes
from ctypes import wintypes as w
import os
import subprocess
import time


class Limits(ctypes.Structure):
    _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                ("flags", w.DWORD), ("minimum", ctypes.c_size_t),
                ("maximum", ctypes.c_size_t), ("processes", w.DWORD),
                ("affinity", ctypes.c_size_t), ("priority", w.DWORD),
                ("scheduling", w.DWORD)]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [("basic", Limits), ("io", ctypes.c_uint64 * 6),
                ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]


class ThreadEntry(ctypes.Structure):
    _fields_ = [("size", w.DWORD), ("usage", w.DWORD), ("tid", w.DWORD),
                ("pid", w.DWORD), ("priority", w.LONG), ("delta", w.LONG),
                ("flags", w.DWORD)]


def kernel():
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    declarations = {
        "CreateJobObjectW": ([ctypes.c_void_p, w.LPCWSTR], w.HANDLE),
        "SetInformationJobObject": ([w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD], w.BOOL),
        "QueryInformationJobObject": ([w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p], w.BOOL),
        "AssignProcessToJobObject": ([w.HANDLE, w.HANDLE], w.BOOL),
        "TerminateJobObject": ([w.HANDLE, w.UINT], w.BOOL),
        "CloseHandle": ([w.HANDLE], w.BOOL),
        "CreateToolhelp32Snapshot": ([w.DWORD, w.DWORD], w.HANDLE),
        "Thread32First": ([w.HANDLE, ctypes.POINTER(ThreadEntry)], w.BOOL),
        "Thread32Next": ([w.HANDLE, ctypes.POINTER(ThreadEntry)], w.BOOL),
        "OpenThread": ([w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
        "ResumeThread": ([w.HANDLE], w.DWORD),
    }
    for name, (arguments, result) in declarations.items():
        function = getattr(api, name)
        function.argtypes, function.restype = arguments, result
    return api


class WindowsJob:
    def __init__(self):
        if os.name != "nt":
            raise OSError("Windows job requested on another platform")
        self.api, self.handle = kernel(), None
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            limits = ExtendedLimits()
            limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway.
            if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                raise ctypes.WinError(ctypes.get_last_error())
        except BaseException:
            self.close()
            raise

    def assign(self, process):
        # Popen owns this process handle until disposal, preventing PID-only targeting.
        if not self.api.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def resume(self, process):
        snapshot = self.api.CreateToolhelp32Snapshot(4, 0)  # TH32CS_SNAPTHREAD
        if snapshot == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            entry, threads = ThreadEntry(), []
            entry.size = ctypes.sizeof(entry)
            found = self.api.Thread32First(snapshot, ctypes.byref(entry))
            while found:
                if entry.pid == process.pid:
                    threads.append(entry.tid)
                entry.size = ctypes.sizeof(entry)
                found = self.api.Thread32Next(snapshot, ctypes.byref(entry))
            if ctypes.get_last_error() != 18:  # ERROR_NO_MORE_FILES
                raise ctypes.WinError(ctypes.get_last_error())
            if len(threads) != 1:
                raise RuntimeError("suspended benchmark parent must have one initial thread")
            thread = self.api.OpenThread(2, False, threads[0])  # THREAD_SUSPEND_RESUME
            if not thread:
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                if self.api.ResumeThread(thread) != 1:
                    raise RuntimeError("unexpected suspended benchmark thread state")
            finally:
                self.api.CloseHandle(thread)
        finally:
            self.api.CloseHandle(snapshot)

    def members(self):
        # An excessive job is rejected; TerminateJobObject still terminates all members.
        maximum = 4096
        data = ctypes.create_string_buffer(8 + maximum * ctypes.sizeof(ctypes.c_size_t))
        if not self.api.QueryInformationJobObject(self.handle, 3, data, len(data), None):
            raise ctypes.WinError(ctypes.get_last_error())
        assigned, count = (w.DWORD * 2).from_buffer(data)
        if assigned != count or count > maximum:
            raise RuntimeError("incomplete job process inventory")
        return list((ctypes.c_size_t * count).from_buffer(data, 8))

    def terminate(self):
        # Capture errors never prevent terminating the owned job.
        try:
            members = self.members()
        finally:
            if not self.api.TerminateJobObject(self.handle, 1):
                raise ctypes.WinError(ctypes.get_last_error())
        deadline = time.monotonic() + 5
        while self.members():
            if time.monotonic() >= deadline:
                return members, False
            time.sleep(0.02)
        return members, True

    def close(self):
        if self.handle is not None:
            handle, self.handle = self.handle, None
            if not self.api.CloseHandle(handle):
                raise ctypes.WinError(ctypes.get_last_error())


def spawn_owned(command, **options):
    """Start no child instructions before assigning the Windows job."""
    if os.name != "nt":
        return subprocess.Popen(command, **options)
    job, process = WindowsJob(), None
    try:
        options["creationflags"] = options.get("creationflags", 0) | 4  # CREATE_SUSPENDED
        process = subprocess.Popen(command, **options)
        job.assign(process)
        job.resume(process)
        process.nbsr_job = job
        return process
    except BaseException:
        try:
            if process is not None:
                process.kill()
                process.wait(timeout=5)
        finally:
            job.close()
        raise
