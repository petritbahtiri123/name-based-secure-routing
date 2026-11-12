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

    def create_job(self, name=None):
        job = self._check(self.kernel.CreateJobObjectW(None, name))
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
                    0x00000004 | 0x08000000, None, str(Path(__file__).resolve().parent),
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
import json
import math
import signal
import sys
import threading
import uuid
import time

IS_WINDOWS = os.name == 'nt'
OUTPUT_LIMIT = 4 * 1024 * 1024


def _validate(argv, cwd, env, timeout):
    if (not isinstance(argv, list) or not argv
            or any(type(a) is not str or '\0' in a for a in argv)
            or not Path(argv[0]).is_absolute()):
        raise ValueError('absolute executable and NUL-free argv required')
    if Path(argv[0]).suffix.lower() in ('.bat', '.cmd'):
        raise ValueError('shell scripts are not accepted')
    if not Path(cwd).is_absolute() or not Path(cwd).is_dir():
        raise ValueError('existing absolute cwd required')
    if not math.isfinite(timeout) or not 0 < timeout <= 95:
        raise ValueError('timeout must be in (0, 95]')
    if not isinstance(env, dict) or any(
        type(k) is not str or type(v) is not str or not k or '=' in k
        or '\0' in k or '\0' in v for k, v in env.items()
    ):
        raise ValueError('invalid environment')


def _capture(stream, target, budget, lock, exceeded):
    with stream, open(target, 'wb') as output:
        while True:
            # Read available bytes without waiting for a full buffer or EOF.
            chunk = stream.read1(8192)
            if not chunk:
                return
            with lock:
                count = min(len(chunk), max(0, OUTPUT_LIMIT - budget[0]))
                output.write(chunk[:count])
                output.flush()  # Preserve short progress before owned forced cleanup.
                budget[0] += count
                if count < len(chunk):
                    exceeded.set()


def _helper(request):
    """Independent deadline owner. Request lives in a unique private run directory."""
    spec = json.loads(Path(request).read_text(encoding='utf-8'))
    directory = Path(request).parent
    start = time.monotonic()
    # On POSIX this helper is the session/group leader and deliberately stays alive
    # after the child finishes; the controller never reaps it before group signalling.
    if not IS_WINDOWS:
        signal.signal(signal.SIGTERM, lambda *_: None)
    watchdog_job = None
    watchdog_backend = None
    if IS_WINDOWS:
        watchdog_backend = Win32Backend()
        opener = watchdog_backend.kernel.OpenJobObjectW
        opener.argtypes, opener.restype = [W.DWORD, W.BOOL, W.LPCWSTR], W.HANDLE
        watchdog_job = opener(0x0008, False, spec['job_name'])
        if not watchdog_job:
            (directory / 'result.json').write_text(json.dumps({'reason': 'ownership_error', 'exit_code': None}), encoding='utf-8')
            return
    proc = None
    reason, code = 'launch_error', None
    exceeded = threading.Event()
    try:
        proc = subprocess.Popen(spec['argv'], cwd=spec['cwd'], env=spec['env'],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, close_fds=True)
        budget, lock = [0], threading.Lock()
        readers = [threading.Thread(target=_capture,
                   args=(stream, directory / name, budget, lock, exceeded), daemon=True)
                   for stream, name in ((proc.stdout, 'stdout.log'), (proc.stderr, 'stderr.log'))]
        for reader in readers:
            reader.start()
        while True:
            if exceeded.is_set():
                reason = 'output_limit'
                break
            if (directory / 'cancel').exists():
                reason = 'cancelled'
                break
            if time.monotonic() - start >= spec['timeout']:
                reason = 'timeout'
                break
            code = proc.poll()
            if code is not None:
                for reader in readers:
                    reader.join(0.05)
                if exceeded.is_set():
                    reason = 'output_limit'
                elif all(not reader.is_alive() for reader in readers):
                    reason = 'completed'
                else:
                    time.sleep(0.02)
                    continue
                break
            time.sleep(0.02)
    except Exception:
        reason = 'launch_error'
    (directory / 'result.json').write_text(json.dumps({'reason': reason, 'exit_code': code}), encoding='utf-8')
    if not IS_WINDOWS:
        # The independent helper enforces its own deadline even if the API dies.
        os.killpg(os.getpgrp(), signal.SIGTERM)
        time.sleep(0.3)
        os.killpg(os.getpgrp(), signal.SIGKILL)
    else:
        # Independent deadline owner terminates the entire Job, including itself.
        watchdog_backend._check(watchdog_backend.kernel.TerminateJobObject(watchdog_job, 1))


def run_owned(argv, cwd, env, log_dir, timeout=95, cancel=None):
    """Run trusted local commands only. No shell, downloads, or global process scans.

    The caller supplies a fresh log directory and an explicit environment. POSIX
    process groups are ownership boundaries, not a sandbox against setsid/daemonize.
    Native macOS validation is required before claiming that platform verified.
    """
    _validate(argv, cwd, env, timeout)
    start = time.monotonic()
    directory = Path(log_dir).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    request = directory / 'request.json'
    job_name = 'Local\\NBSRDemoLab-' + uuid.uuid4().hex
    request.write_text(json.dumps({'argv': argv, 'cwd': str(cwd), 'env': env,
                                  'timeout': timeout, 'job_name': job_name}), encoding='utf-8')
    for name in ('stdout.log', 'stderr.log'):
        (directory / name).touch()
    command = [sys.executable, str(Path(__file__).resolve()), '--helper', str(request)]
    reason, code, clean = 'launch_error', None, False
    backend = job = process = thread = None
    assigned = False
    child = None
    try:
        if IS_WINDOWS:
            backend = Win32Backend()
            job = backend.create_job(job_name)
            process, thread = backend.create_suspended(command)
            backend.assign(job, process)
            assigned = True
            backend.resume(thread)
        else:
            child = subprocess.Popen(command, cwd=str(cwd), stdin=subprocess.DEVNULL,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     close_fds=True, start_new_session=True)
        reason = 'timeout'
        while time.monotonic() - start < timeout:
            result_path = directory / 'result.json'
            if result_path.exists():
                try:
                    result = json.loads(result_path.read_text(encoding='utf-8'))
                    reason, code = result['reason'], result['exit_code']
                    break
                except (ValueError, KeyError):
                    pass  # Writer may still be finishing the small receipt.
            if cancel is not None and cancel.is_set():
                reason = 'cancelled'
                break
            time.sleep(0.02)
    except Exception:
        reason = 'ownership_error' if process is not None or child is not None else 'launch_error'
    finally:
        if backend is not None and process is not None:
            try:
                backend.terminate(job, process, assigned)
                end = time.monotonic() + 5
                while time.monotonic() < end:
                    leader_code, active = backend.observe(job, process, assigned)
                    if leader_code is not None and active == 0:
                        clean = True
                        break
                    time.sleep(0.02)
            except Exception:
                clean = False
        elif child is not None:
            try:
                # Do not poll/wait before signalling: an unreaped leader reserves PID.
                os.killpg(child.pid, signal.SIGTERM)
                time.sleep(0.3)
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=3)
                end = time.monotonic() + 2
                while time.monotonic() < end:
                    try:
                        os.killpg(child.pid, 0)
                    except ProcessLookupError:
                        clean = True
                        break
                    time.sleep(0.02)
            except Exception:
                clean = False
        else:
            clean = True  # No process was created.
        if backend is not None:
            for handle in (thread, process, job):
                if handle is not None:
                    try:
                        backend.close(handle)
                    except Exception:
                        clean = False
        # Avoid retaining environment values in durable logs.
        request.unlink(missing_ok=True)
    return {'exit_code': code, 'cleanup': 'CLEAN' if clean else 'UNCONFIRMED',
            'reason': reason, 'elapsed': time.monotonic() - start}


if __name__ == '__main__':
    if len(sys.argv) != 3 or sys.argv[1] != '--helper':
        raise SystemExit(2)
    _helper(sys.argv[2])
