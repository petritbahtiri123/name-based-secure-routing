"""Fake Win32 calls only: no DLL loading, process creation, signals or jobs."""
import importlib


def api():
    name = 'scripts.performance.windows_job_backend'
    assert importlib.util.find_spec(name) is not None, 'native binding missing'
    return importlib.import_module(name)


class Function:
    def __init__(self, call):
        self.call = call

    def __call__(self, *args):
        return self.call(*args)


class Kernel:
    def __init__(self):
        self.calls = []
        self.wait = 258
        self.active = 1
        self.code = 259
        for name in ('CreateJobObjectW', 'SetInformationJobObject', 'CreateProcessW',
                     'AssignProcessToJobObject', 'ResumeThread', 'QueryInformationJobObject',
                     'WaitForSingleObject', 'GetExitCodeProcess', 'TerminateJobObject',
                     'TerminateProcess', 'CloseHandle'):
            setattr(self, name, Function(lambda *args, n=name: self.invoke(n, args)))

    def invoke(self, name, args):
        self.calls.append((name, args))
        if name == 'CreateJobObjectW':
            return 10
        if name == 'CreateProcessW':
            assert args[4] is False  # no inherited daemon, pipe, or job handles
            assert args[5] & 4  # primary thread remains suspended
            assert not args[5] & 0x01000000  # no breakaway
            args[-1]._obj.hProcess = 20
            args[-1]._obj.hThread = 21
        if name == 'SetInformationJobObject':
            assert args[2]._obj.BasicLimitInformation.LimitFlags == 0x2000
        if name == 'QueryInformationJobObject':
            args[2]._obj.ActiveProcesses = self.active
        if name == 'WaitForSingleObject':
            assert args[1] == 0
            return self.wait
        if name == 'GetExitCodeProcess':
            args[1]._obj.value = self.code
        return 1


def test_exact_native_handle_calls_with_suspension_and_no_inheritance():
    mod = api()
    kernel = Kernel()
    backend = mod.Win32Backend(kernel=kernel)
    job = backend.create_job()
    process, thread = backend.create_suspended(['C:/Python/python.exe', '-B', 'worker.py'])
    backend.assign(job, process)
    backend.resume(thread)
    assert (job, process, thread) == (10, 20, 21)
    assert backend.observe(job, process, True) == (None, 1)
    kernel.wait, kernel.active = 0, 0
    # Exit status259 is legitimate after the process handle becomes signalled.
    assert backend.observe(job, process, True) == (259, 0)
    backend.terminate(job, process, True)
    assert kernel.calls[-1][0] == 'TerminateJobObject'
    backend.terminate(job, process, False)
    assert kernel.calls[-1][0] == 'TerminateProcess'
    backend.close(thread)
    assert kernel.calls[-1] == ('CloseHandle', (21,))


def test_unassigned_suspended_process_cannot_disappear_with_empty_job():
    mod = api()
    kernel = Kernel()
    backend = mod.Win32Backend(kernel=kernel)
    kernel.active = 0
    assert backend.observe(10, 20, False) == (None, 1)
    kernel.wait = 0
    assert backend.observe(10, 20, False) == (259, 0)


def test_exit_between_native_observations_retains_until_next_poll():
    from scripts.performance.windows_native_management import WindowsOwner

    class ExitDuringObservation(Kernel):
        def invoke(self, name, args):
            result = super().invoke(name, args)
            if name in ('WaitForSingleObject', 'QueryInformationJobObject'):
                # Termination occurs after the first sampled value, before the second.
                self.wait, self.active, self.code = 0, 0, 1
            return result

    kernel = ExitDuringObservation()
    owner = WindowsOwner(['C:/Python/python.exe'],
                         backend=api().Win32Backend(kernel=kernel), cancel=lambda: None)
    owner.start()
    assert owner.observe() == (1, True)
    assert owner.owned
    assert not any(name == 'CloseHandle' for name, _ in kernel.calls)
    owner.reap()
    assert not owner.owned
    assert [args for name, args in kernel.calls if name == 'CloseHandle'] == [(21,), (20,), (10,)]
