"""Keep Linux terminal process evidence available until explicit reaping."""

from types import SimpleNamespace
import queue

import pytest

from scripts import run_b5_v2 as b5


@pytest.mark.parametrize("code", [0, 7, -9])
def test_consume_injected_exit_never_polls_or_reaps(code):
    class Source:
        def poll(self):
            raise AssertionError("reaping poll forbidden")

    reader = SimpleNamespace(queue=queue.Queue())
    reader.queue.put(b"final-record\n")
    reader.queue.put(None)
    calls = []

    class Stream:
        def check(self, **kwargs):
            calls.append(("check", kwargs))

        def feed(self, value, **kwargs):
            calls.append(("feed", value))

        def finish(self, actual):
            assert actual == code
            return actual

    assert b5.consume(Source(), reader, Stream(), observe_exit=lambda: code) == code
    assert ("feed", b"final-record\n") in calls


def test_exit_observer_error_is_not_hidden_as_running():
    def denied():
        raise PermissionError("waitid denied")

    with pytest.raises(PermissionError, match="waitid denied"):
        b5.consume(None, None, None, observe_exit=denied)


@pytest.mark.parametrize("status,expected", [(None, None), ((1, 0), 0), ((1, 7), 7), ((2, 9), -9), ((3, 6), -6)])
def test_linux_waitid_uses_nowait_and_preserves_exit_status(monkeypatch, status, expected):
    from scripts.performance import linux_exit

    backend = SimpleNamespace(P_PID=1, WEXITED=4, WNOHANG=1, WNOWAIT=8,
                              CLD_EXITED=1, CLD_KILLED=2, CLD_DUMPED=3)

    def waitid(kind, pid, flags):
        assert (kind, pid, flags) == (1, 123, 13)
        return None if status is None else SimpleNamespace(si_pid=123, si_code=status[0], si_status=status[1])

    backend.waitid = waitid
    monkeypatch.setattr(linux_exit, "os", backend)
    assert linux_exit.observe_owned_exit(123) == expected


def test_linux_waitid_rejects_wrong_process(monkeypatch):
    from scripts.performance import linux_exit

    backend = SimpleNamespace(P_PID=1, WEXITED=4, WNOHANG=1, WNOWAIT=8,
                              waitid=lambda *args: SimpleNamespace(si_pid=124))
    monkeypatch.setattr(linux_exit, "os", backend)
    with pytest.raises(RuntimeError, match="identity"):
        linux_exit.observe_owned_exit(123)
