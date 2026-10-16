"""Deterministic cleanup boundaries: no real children, threads, sleeps or sockets."""

import io
import json
from types import SimpleNamespace

import pytest

from scripts.performance import linux_native_lifecycle_coordinator as coordinator


class Clock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Stream(io.BytesIO):
    def __init__(self, fail=False):
        super().__init__()
        self.fail = fail
        self.close_attempted = False

    def close(self):
        self.close_attempted = True
        if self.fail:
            raise OSError("private-sentinel-do-not-retain")
        super().close()


class Child:
    def __init__(self, *, code=None, failures=()):
        self.returncode = code
        self.failures = set(failures)
        self.calls = []
        self.stdin, self.stdout = Stream(), Stream()

    def poll(self):
        if "poll" in self.failures:
            raise OSError("private-sentinel-do-not-retain")
        return self.returncode

    def terminate(self):
        self.calls.append("terminate")
        if "terminate" in self.failures:
            raise OSError("private-sentinel-do-not-retain")
        if "terminate_timeout" not in self.failures:
            self.returncode = -15

    def kill(self):
        self.calls.append("kill")
        if "kill" in self.failures:
            raise OSError("private-sentinel-do-not-retain")
        self.returncode = -9

    def wait(self, timeout):
        self.calls.append(("wait", timeout))
        if "wait" in self.failures:
            raise OSError("private-sentinel-do-not-retain")
        if self.returncode is None:
            raise coordinator.subprocess.TimeoutExpired("synthetic", timeout)
        return self.returncode


class Reader:
    def __init__(self, *, started=True, fail=False, alive=False):
        self.ident = 1 if started else None
        self.fail, self.alive = fail, alive
        self.joined = False

    def join(self, timeout):
        assert self.ident is not None, "unstarted reader must not be joined"
        self.joined = True
        if self.fail:
            raise RuntimeError("private-sentinel-do-not-retain")

    def is_alive(self):
        return self.alive


@pytest.fixture
def manager(tmp_path, monkeypatch):
    clock = Clock()
    monkeypatch.setattr(coordinator.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(coordinator.time, "sleep", clock.sleep)
    value = coordinator.Manager(16, tmp_path, timeout=1, cleanup_timeout=.01)
    value.children = dict(source=Child(), destination=Child())
    value.readers = {role: Reader() for role in value.children}
    value.errors = {role: Stream() for role in value.children}
    value.test_clock = clock
    yield value
    # Test-owned files only; fake stream failure is disabled for fixture teardown.
    pipes = [stream for child in value.children.values() for stream in (child.stdin, child.stdout)]
    for stream in [value.log, *value.errors.values(), *pipes]:
        if isinstance(stream, Stream):
            stream.fail = False
        stream.close()


def test_terminate_failure_does_not_skip_sibling_or_handle_cleanup(manager):
    source = manager.children["source"]
    source.failures = {"terminate", "kill", "wait"}
    result = manager.close()
    assert "terminate" in manager.children["destination"].calls
    assert source is manager.children["source"]  # Unconfirmed ownership retained.
    assert result["source"]["exit_code"] is None
    assert result["source"]["local_relay_reaped"] is False
    assert result["source"]["remote_cleanup"] == "UNCONFIRMED"
    assert {e["stage"] for e in result["source"]["local_cleanup_errors"]} >= {"terminate", "kill", "wait"}
    assert all(stream.closed for stream in manager.errors.values())
    assert manager.log.closed
    assert "private-sentinel" not in json.dumps(result)


@pytest.mark.parametrize("failure", ["poll", "terminate_timeout", "wait", "reader", "reader_alive", "stdin", "stdout", "stderr", "log_write", "log_close"])
def test_cleanup_action_failure_isolated_and_visible(manager, failure):
    source = manager.children["source"]
    if failure in {"poll", "terminate_timeout", "wait"}:
        source.failures.add(failure)
    elif failure == "reader":
        manager.readers["source"].fail = True
    elif failure == "reader_alive":
        manager.readers["source"].alive = True
    elif failure in {"stdin", "stdout"}:
        getattr(source, failure).fail = True
    elif failure == "stderr":
        manager.errors["source"].fail = True
    else:
        manager.log.close()

        class Log(Stream):
            def write(self, data):
                if failure == "log_write":
                    raise OSError("private-sentinel-do-not-retain")
                return len(data)

        manager.log = Log(fail=failure == "log_close")
    result = manager.close()
    assert "terminate" in manager.children["destination"].calls
    assert result["source"]["local_cleanup_errors"]
    assert result["source"]["remote_cleanup"] == "UNCONFIRMED"
    assert len(result["source"]["local_cleanup_errors"]) <= 16
    assert "private-sentinel" not in json.dumps(result)
    assert manager.errors["destination"].closed


def test_zero_exit_remains_only_local_evidence(manager):
    for child in manager.children.values():
        child.returncode = 0
    result = manager.close()
    coordinator.require_relay_cleanup(result)
    for row in result.values():
        assert row == dict(exit_code=0, local_relay_forced=False,
                          remote_cleanup="REQUIRES_EVIDENCE", local_relay_reaped=True,
                          local_cleanup_errors=[])


@pytest.mark.parametrize("trigger", ["timeout", "disconnect", "cancel"])
def test_driver_failure_still_cleans_both_owned_relays(manager, trigger):
    if trigger == "timeout":
        manager.test_clock.now = manager.deadline
        error = TimeoutError
    elif trigger == "disconnect":
        manager.children["source"].returncode = 255
        manager.messages.put(("source", None))
        error = InterruptedError
    else:
        def cancel():
            raise InterruptedError("synthetic cancellation")
        manager.check_cancelled = cancel
        error = InterruptedError
    try:
        with pytest.raises(error):
            manager.wait("source", "prepared")
    finally:
        result = manager.close()
    assert "terminate" in manager.children["destination"].calls
    assert result["source"]["remote_cleanup"] == "UNCONFIRMED"
    assert manager.log.closed


@pytest.mark.parametrize("reader_state", ["missing", "unstarted"])
def test_owned_child_without_started_reader_is_still_reaped(manager, reader_state):
    if reader_state == "missing":
        del manager.readers["source"]
    else:
        manager.readers["source"] = Reader(started=False)
    result = manager.close()
    assert result["source"]["local_relay_reaped"] is True
    assert "terminate" in manager.children["destination"].calls


def test_failed_second_popen_closes_its_stderr_and_cleans_first(manager, monkeypatch):
    del manager.children["destination"]
    del manager.readers["destination"]
    manager.errors["destination"].close()
    del manager.errors["destination"]

    def fail(*args, **kwargs):
        raise OSError("synthetic Popen failure")

    monkeypatch.setattr(coordinator.subprocess, "Popen", fail)
    with pytest.raises(OSError):
        manager.start_command("destination", ["never-executed"])
    result = manager.close()
    assert manager.errors["destination"].closed
    assert result["source"]["local_relay_reaped"] is True
    assert "destination" not in manager.children


def test_thread_start_failure_retains_and_reaps_exact_new_child(manager, monkeypatch):
    old = manager.children.pop("destination")
    old.stdin.close()
    old.stdout.close()
    del manager.readers["destination"]
    manager.errors.pop("destination").close()
    child = Child()

    class Unstarted(Reader):
        def __init__(self, **kwargs):
            super().__init__(started=False)

        def start(self):
            raise RuntimeError("synthetic thread start failure")

    monkeypatch.setattr(coordinator.subprocess, "Popen", lambda *a, **k: child)
    monkeypatch.setattr(coordinator.threading, "Thread", Unstarted)
    with pytest.raises(RuntimeError, match="thread start"):
        manager.start_command("destination", ["never-executed"])
    assert manager.children["destination"] is child
    result = manager.close()
    assert "terminate" in child.calls
    assert result["destination"]["local_relay_reaped"] is True
    assert all(stream.closed for stream in manager.errors.values())


@pytest.mark.parametrize("kind", ["finite", "lifecycle"])
@pytest.mark.parametrize("driver_fails", [False, True])
@pytest.mark.parametrize("cleanup_write_fails", [False, True])
def test_coordinators_keep_cleanup_failure_and_never_reach_pass(tmp_path, monkeypatch, kind, driver_fails, cleanup_write_fails):
    from scripts.performance import linux_native_finite_run, linux_native_lifecycle_run
    from tests.performance.test_linux_native_finite_run import config as finite_config
    from tests.performance.test_linux_native_lifecycle_coordinator import config as lifecycle_config

    run, config = (linux_native_finite_run, finite_config) if kind == "finite" else (linux_native_lifecycle_run, lifecycle_config)
    outcome = {role: dict(exit_code=0, local_relay_forced=False, local_relay_reaped=True,
                         remote_cleanup="UNCONFIRMED", local_cleanup_errors=[dict(stage="stdout_close", error_type="OSError")])
               for role in ("source", "destination")}

    class Manager:
        def __init__(self, *args, **kwargs):
            self.children = dict(source=object(), destination=object())
            self.ledger = SimpleNamespace(positions=dict(source=0, destination=0))

        start_command = wait = send = finish = sleep = lambda *args: None

        def close(self):
            return outcome

    def drive(*args, **kwargs):
        if driver_fails:
            raise InterruptedError("synthetic driver failure")

    monkeypatch.setattr(run, "Manager", Manager)
    monkeypatch.setattr(run, "drive", drive)
    monkeypatch.setattr(run, "check_endpoint", lambda *a, **k: pytest.fail("cleanup failure reached PASS validation"))
    monkeypatch.setattr(run, "collect", lambda *a, **k: pytest.fail("unowned output collected"))
    original_write = run.write_json

    def write(path, value):
        if cleanup_write_fails and path.name == "cleanup.json":
            raise OSError("synthetic evidence write failure")
        original_write(path, value)

    monkeypatch.setattr(run, "write_json", write)
    output = tmp_path / "output"
    expected_error = OSError if cleanup_write_fails else (InterruptedError if driver_fails else ValueError)
    with pytest.raises(expected_error):
        run.execute(config(), output)
    if not cleanup_write_fails:
        assert json.loads((output / "cleanup.json").read_text()) == outcome
    if driver_fails:
        assert json.loads((output / "driver-failure.json").read_text()) == {"error_type": "InterruptedError"}
    assert (output / "failure.json").exists()
    assert not (output / "result.json").exists()


@pytest.mark.parametrize("change", [
    {"exit_code": None}, {"exit_code": True}, {"exit_code": 255},
    {"local_relay_forced": True}, {"local_relay_reaped": False},
    {"remote_cleanup": "UNCONFIRMED"}, {"local_cleanup_errors": None},
])
def test_cleanup_gate_rejects_incomplete_or_unconfirmed_local_results(change):
    outcomes = {role: dict(exit_code=0, local_relay_forced=False,
                          remote_cleanup="REQUIRES_EVIDENCE", local_relay_reaped=True,
                          local_cleanup_errors=[]) for role in ("source", "destination")}
    outcomes["source"].update(change)
    with pytest.raises(ValueError, match="relay cleanup failed"):
        coordinator.require_relay_cleanup(outcomes)
