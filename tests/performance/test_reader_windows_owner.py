import unittest
from scripts.performance.reader_windows_owner import WindowsOwner
from scripts.performance import reader_settlement as m


class Backend:
    def __init__(self):
        self.code = 0
        self.active = 0
        self.closed = []
        self.close_error = False

    def create_job(self):
        return object()

    def create_suspended(self, argv):
        return object(), object()

    def assign(self, j, p):
        pass

    def resume(self, t):
        pass

    def observe(self, j, p, a):
        return self.code, self.active

    def close(self, h):
        if self.close_error:
            raise OSError("close failure")
        self.closed.append(h)


class BoundForTest(WindowsOwner):
    identity = "owner-1"
    drain_failure = None


class OwnerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.b = Backend()
        self.o = BoundForTest(("fake-only",), backend=self.b, cancel=lambda: None)
        self.o.start()
        self.life = m.Lifecycle(
            run="next",
            source="stdout",
            owner="owner-1",
            anchor=0.0,
            deadline=150.0,
            caps={"capture": 16, "receipts": 16},
            clock=lambda: 1.0,
        )
        self.capture = lambda: dict(run="next", source="stdout", owner="owner-1", quiescent=True, final_valid=True, sha256="a" * 64)

    def test_real_reap_closes_all_three_handles(self):
        self.life.checkpoint(self.o, self.capture)
        self.assertFalse(self.o.owned)
        self.assertEqual(len(self.b.closed), 3)
        self.assertEqual(self.life.state, "CLOSED_UNSETTLED")

    def test_real_live_descendant_blocks_release(self):
        self.b.active = 1
        self.life.checkpoint(self.o, self.capture)
        self.assertTrue(self.o.owned)
        self.assertEqual(self.life.state, "OPEN")

    def test_handle_close_failure_preserves_ownership_and_invalidates(self):
        self.b.close_error = True
        with self.assertRaises(OSError):
            self.life.checkpoint(self.o, self.capture)
        self.assertTrue(self.o.owned)
        self.assertEqual(self.life.state, "INVALID")

    def test_cancel_signal_after_closure_is_still_fatal(self):
        self.life.checkpoint(self.o, self.capture)
        self.o.signal("INT")
        with self.assertRaises(ValueError):
            self.life.begin_post()


if __name__ == "__main__":
    unittest.main()


def test_real_draining_owner_waits_for_descendant_then_closes():
    from scripts.performance.reader_windows_drain import DrainingOwner

    b = Backend()
    b.active = 1
    b.member_pids = lambda job: [17]
    now = [0.0]
    o = DrainingOwner(("fake-only",), backend=b, cancel=lambda: None, deadline=10.0, clock=lambda: now[0])
    o.start()
    assert o.observe() == (None, True)
    assert o.owned
    now[0] = 1.0
    b.active = 0
    assert o.observe() == (0, False)
    o.reap()
    assert not o.owned and o.drain_failure is None


def test_real_draining_owner_expiry_never_recovers():
    from scripts.performance.reader_windows_drain import DrainingOwner

    b = Backend()
    b.active = 1
    b.member_pids = lambda job: [17]
    killed = []
    b.terminate = lambda job, process, assigned: killed.append(job)
    now = [0.0]
    o = DrainingOwner(("fake-only",), backend=b, cancel=lambda: None, deadline=10.0, clock=lambda: now[0])
    o.start()
    assert o.observe() == (None, True)
    now[0] = 2.1
    import pytest

    with pytest.raises(TimeoutError):
        o.observe()
    assert o.drain_failure == "TimeoutError" and o.killed and len(killed) == 1
    b.active = 0
    assert o.observe() == (0, False)
    assert o.drain_failure == "TimeoutError"


def test_coherent_backend_refreshes_after_leader_exit(monkeypatch):
    import ctypes
    from scripts.performance.reader_windows_drain import CoherentBackend
    from scripts.performance.reader_windows_backend import Win32Backend, Accounting

    monkeypatch.setattr(Win32Backend, "observe", lambda self, *args: (0, 1))

    class Kernel:
        def QueryInformationJobObject(self, job, kind, ptr, size, unused):
            ctypes.cast(ptr, ctypes.POINTER(Accounting)).contents.ActiveProcesses = 0
            return True

    b = CoherentBackend.__new__(CoherentBackend)
    b.kernel = Kernel()
    b.exit_observations = []
    assert b.observe(object(), object(), True) == (0, 0)
    assert b.exit_observations[0]["sampled_before_exit_check"] == 1
    assert b.exit_observations[0]["refreshed_after_exit_check"] == 0


def test_assignment_failure_retains_unassigned_process_for_outer_cleanup():
    import pytest

    b = Backend()
    calls = []

    def fail(*args):
        raise OSError("assign")

    b.assign = fail
    b.terminate = lambda j, p, a: calls.append((j, p, a))
    o = WindowsOwner(("fake",), backend=b, cancel=lambda: None)
    with pytest.raises(OSError):
        o.start()
    assert o.owned and not o.assigned
    o.signal("KILL")
    assert calls[0][2] is False and calls[0][1] is o.process
    o.reap()
    assert not o.owned


def test_resume_failure_retains_assigned_job_for_outer_cleanup():
    import pytest

    b = Backend()
    calls = []

    def fail(*args):
        raise OSError("resume")

    b.resume = fail
    b.terminate = lambda j, p, a: calls.append((j, p, a))
    o = WindowsOwner(("fake",), backend=b, cancel=lambda: None)
    with pytest.raises(OSError):
        o.start()
    assert o.owned and o.assigned
    o.signal("KILL")
    assert calls[0][2] is True
    o.reap()
    assert not o.owned


def test_partial_close_keeps_failed_handle_and_remaining_handles():
    import pytest

    b = Backend()
    o = WindowsOwner(("fake",), backend=b, cancel=lambda: None)
    o.start()
    process, job = o.process, o.job

    def close(h):
        if h is process:
            raise OSError("partial close")
        b.closed.append(h)

    b.close = close
    with pytest.raises(OSError):
        o.reap()
    assert o.thread is None and o.process is process and o.job is job and o.owned
    b.close = lambda h: b.closed.append(h)
    o.reap()
    assert not o.owned


def test_failed_unassigned_termination_never_implies_cleanup():
    import pytest

    b = Backend()
    b.code = None
    b.active = 1

    def fail(*args):
        raise OSError("failed containment")

    b.assign = fail
    b.terminate = fail
    o = WindowsOwner(("fake",), backend=b, cancel=lambda: None)
    with pytest.raises(OSError):
        o.start()
    with pytest.raises(OSError):
        o.signal("KILL")
    with pytest.raises(Exception):
        o.reap()
    assert o.owned


def test_backend_configuration_and_close_failure_retains_job():
    import pytest
    from scripts.performance.reader_windows_backend import Win32Backend, RetainedJobError

    class Kernel:
        def CreateJobObjectW(self, *args):
            return 17

        def SetInformationJobObject(self, *args):
            return 0

        def CloseHandle(self, *args):
            return 0

    b = Win32Backend.__new__(Win32Backend)
    b.kernel = Kernel()
    with pytest.raises(RetainedJobError) as error:
        b.create_job()
    assert error.value.job == 17
    o = WindowsOwner(("fake",), backend=b, cancel=lambda: None)
    with pytest.raises(RetainedJobError):
        o.start()
    assert o.job == 17 and o.owned


def test_backend_termination_targets_exact_assigned_or_unassigned_handle():
    from scripts.performance.reader_windows_backend import Win32Backend

    calls = []

    class Kernel:
        def TerminateJobObject(self, h, c):
            calls.append(("job", h))
            return 1

        def TerminateProcess(self, h, c):
            calls.append(("process", h))
            return 1

    b = Win32Backend.__new__(Win32Backend)
    b.kernel = Kernel()
    b.terminate(17, 23, False)
    b.terminate(17, 23, True)
    assert calls == [("process", 23), ("job", 17)]


def test_promoted_owner_binding_and_settlement_integrate_without_double_reap():
    from scripts.performance.reader_windows_drain import DrainingOwner
    from scripts.performance.reader_settlement import BoundReaderOwner, Lifecycle

    b = Backend()
    now = [0.0]
    native = DrainingOwner(("fake-only",), backend=b, cancel=lambda: None, deadline=150.0, clock=lambda: now[0])
    native.start()
    bound = BoundReaderOwner(native, run="next", source="stdout", request_sha256="a" * 64, argv=("fake-only",), deadline=150.0)
    life = Lifecycle(
        run="next",
        source="stdout",
        owner=bound.identity,
        anchor=0.0,
        deadline=150.0,
        caps={"capture": 16, "receipts": 16},
        clock=lambda: now[0],
    )

    def capture():
        return dict(run="next", source="stdout", owner=life.identity["owner"], quiescent=True, final_valid=True, sha256="b" * 64)

    order = []

    def scan(tick):
        for second in (20.0, 30.0, 40.0):
            now[0] = second
            tick()
        order.append("settled")
        return dict(valid=True, receipt_sha256="c" * 64)

    def probe(permit):
        order.append("clock-only")
        assert permit["operation"] == "clock-probes-only"
        return dict(span_ns=20_000_000_000, probes_valid=True)

    life.reconcile(scan, bound, capture, probe)
    assert len(b.closed) == 3 and not native.owned
    assert order == ["clock-only", "settled"]
    assert life.accept()["campaign_validity"] == "REQUIRES_OTHER_GATES"
