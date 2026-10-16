"""Explicit Win32 job binding. Offline tests inject kernel calls; no live proof.

Construction without an injected kernel loads Windows APIs but creates nothing.
Calling methods is a separate, explicitly authorized live action. No privilege
adjustment, breakaway, daemon socket, inherited handles or fallback is used.
"""
import ctypes as C
import os
import subprocess
from pathlib import Path
from ctypes import wintypes as W


class BasicLimits(C.Structure):
    _fields_ = [('PerProcessUserTimeLimit', C.c_int64), ('PerJobUserTimeLimit', C.c_int64),
                ('LimitFlags', W.DWORD), ('MinimumWorkingSetSize', C.c_size_t),
                ('MaximumWorkingSetSize', C.c_size_t), ('ActiveProcessLimit', W.DWORD),
                ('Affinity', C.c_size_t), ('PriorityClass', W.DWORD), ('SchedulingClass', W.DWORD)]


class IoCounters(C.Structure):
    _fields_ = [(name, C.c_uint64) for name in (
        'ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount',
        'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]


class ExtendedLimits(C.Structure):
    _fields_ = [('BasicLimitInformation', BasicLimits), ('IoInfo', IoCounters),
                ('ProcessMemoryLimit', C.c_size_t), ('JobMemoryLimit', C.c_size_t),
                ('PeakProcessMemoryUsed', C.c_size_t), ('PeakJobMemoryUsed', C.c_size_t)]


class Accounting(C.Structure):
    _fields_ = [(name, C.c_int64) for name in (
        'TotalUserTime', 'TotalKernelTime', 'ThisPeriodTotalUserTime', 'ThisPeriodTotalKernelTime')]
    _fields_ += [(name, W.DWORD) for name in (
        'TotalPageFaultCount', 'TotalProcesses', 'ActiveProcesses', 'TotalTerminatedProcesses')]


class Startup(C.Structure):
    _fields_ = [('cb', W.DWORD), ('lpReserved', W.LPWSTR), ('lpDesktop', W.LPWSTR),
                ('lpTitle', W.LPWSTR)]
    _fields_ += [(name, W.DWORD) for name in (
        'dwX', 'dwY', 'dwXSize', 'dwYSize', 'dwXCountChars', 'dwYCountChars', 'dwFillAttribute', 'dwFlags')]
    _fields_ += [('wShowWindow', W.WORD), ('cbReserved2', W.WORD),
                 ('lpReserved2', C.POINTER(C.c_ubyte)), ('hStdInput', W.HANDLE),
                 ('hStdOutput', W.HANDLE), ('hStdError', W.HANDLE)]


class ProcessInfo(C.Structure):
    _fields_ = [('hProcess', W.HANDLE), ('hThread', W.HANDLE),
                ('dwProcessId', W.DWORD), ('dwThreadId', W.DWORD)]


class RetainedJobError(OSError):
    def __init__(self, job):
        super().__init__('job configuration/close failed; handle retained')
        self.job = job


class Win32Backend:
    def __init__(self, *, kernel=None):
        if kernel is None:
            if os.name != 'nt':
                raise OSError('Windows backend required')
            kernel = C.WinDLL('kernel32', use_last_error=True)
        self.kernel = kernel
        signatures = {
            'CreateJobObjectW': ([C.c_void_p, W.LPCWSTR], W.HANDLE),
            'SetInformationJobObject': ([W.HANDLE, C.c_int, C.c_void_p, W.DWORD], W.BOOL),
            'CreateProcessW': ([W.LPCWSTR, W.LPWSTR, C.c_void_p, C.c_void_p, W.BOOL,
                                W.DWORD, C.c_void_p, W.LPCWSTR, C.POINTER(Startup),
                                C.POINTER(ProcessInfo)], W.BOOL),
            'AssignProcessToJobObject': ([W.HANDLE, W.HANDLE], W.BOOL),
            'ResumeThread': ([W.HANDLE], W.DWORD),
            'QueryInformationJobObject': ([W.HANDLE, C.c_int, C.c_void_p, W.DWORD,
                                          C.POINTER(W.DWORD)], W.BOOL),
            'WaitForSingleObject': ([W.HANDLE, W.DWORD], W.DWORD),
            'GetExitCodeProcess': ([W.HANDLE, C.POINTER(W.DWORD)], W.BOOL),
            'TerminateJobObject': ([W.HANDLE, W.UINT], W.BOOL),
            'TerminateProcess': ([W.HANDLE, W.UINT], W.BOOL),
            'CloseHandle': ([W.HANDLE], W.BOOL),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(kernel, name)
            function.argtypes, function.restype = arguments, result

    @staticmethod
    def _check(value):
        if not value:
            raise OSError('Win32 operation failed')
        return value

    def create_job(self):
        job = self._check(self.kernel.CreateJobObjectW(None, None))
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE, no breakaway
        try:
            self._check(self.kernel.SetInformationJobObject(job, 9, C.byref(limits), C.sizeof(limits)))
        except BaseException:
            try:
                self.close(job)
            except BaseException as exc:
                raise RetainedJobError(job) from exc
            raise
        return job

    def create_suspended(self, argv):
        if (not argv or not os.path.isabs(argv[0])
                or any(type(arg) is not str or '\0' in arg for arg in argv)):
            raise ValueError('absolute executable and exact argv required')
        command = C.create_unicode_buffer(subprocess.list2cmdline(argv))
        startup, process = Startup(), ProcessInfo()
        startup.cb = C.sizeof(startup)
        # No inherited handles or console. The worker opens its own scoped logs.
        self._check(self.kernel.CreateProcessW(argv[0], command, None, None, False,
                    0x00000004 | 0x08000000, None, str(Path(__file__).resolve().parents[2]),
                    C.byref(startup), C.byref(process)))
        return process.hProcess, process.hThread

    def assign(self, job, process):
        self._check(self.kernel.AssignProcessToJobObject(job, process))

    def resume(self, thread):
        if self.kernel.ResumeThread(thread) == 0xFFFFFFFF:
            raise OSError('ResumeThread failed')

    def observe(self, job, process, assigned):
        # Sample the job first: exit between these non-atomic reads may retain
        # stale positive ownership, but cannot pair an old live leader with a
        # newly empty job. A later poll still requires both completion proofs.
        accounting = Accounting()
        if assigned:
            self._check(self.kernel.QueryInformationJobObject(job, 1, C.byref(accounting),
                                                             C.sizeof(accounting), None))
        state = self.kernel.WaitForSingleObject(process, 0)
        if state not in (0, 258):
            raise OSError('process observation failed')
        code = None
        if state == 0:
            value = W.DWORD()
            self._check(self.kernel.GetExitCodeProcess(process, C.byref(value)))
            code = value.value
        if not assigned:
            return code, int(state != 0)
        return code, accounting.ActiveProcesses

    def terminate(self, job, process, assigned):
        function, handle = (self.kernel.TerminateJobObject, job) if assigned else (
            self.kernel.TerminateProcess, process)
        self._check(function(handle, 1))

    def close(self, handle):
        self._check(self.kernel.CloseHandle(handle))
