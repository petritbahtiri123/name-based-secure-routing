from types import SimpleNamespace
import time
import pytest
from scripts.performance import b4_linux as b4


def row(**changes):
    return (
        dict(
            pid=11,
            start_ticks=3,
            cpu_ns=10,
            timestamp_ns=1,
            state="R",
            flags=0,
            affinity=[0],
            thread_ids=[11],
            fd_count=4,
            fd_count_state="MEASURED",
            rss_bytes=100,
            pss_bytes=90,
            private_resident_bytes=80,
            private_hugetlb_bytes=0,
            memory_state="MEASURED",
            memory_basis="linux_smaps_rollup",
        )
        | changes
    )


def exiting(**changes):
    return (
        row(
            state="R",
            flags=4194572,
            cpu_ns=20,
            timestamp_ns=2,
            fd_count=None,
            fd_count_state="UNAVAILABLE_EXITING",
            memory_state="UNAVAILABLE_EXITING",
            rss_bytes=None,
            pss_bytes=None,
            private_resident_bytes=None,
            private_hugetlb_bytes=None,
        )
        | changes
    )


def test_exit_transition_requires_owned_completion():
    values = iter([row(), exiting()])
    child = SimpleNamespace(pid=11, returncode=None)
    child.poll = lambda: child.returncode
    backend = b4.LinuxB4Backend([0], "taskset", sample_fn=lambda *_: next(values), host_fn=lambda: {"timestamp_ns": time.monotonic_ns()})
    samples = []
    backend.sample({"source": child}, samples)
    backend.sample({"source": child}, samples)
    with pytest.raises(RuntimeError, match="exit"):
        backend.summarize(samples)
    child.returncode = 0
    result = backend.summarize(samples)
    assert result["peak_private_resident_bytes"] == 80
    assert result["exit_transitions"]["source"]["confirmed_exit_code"] == 0
    assert samples[-1]["fd_count"] is None


@pytest.mark.parametrize("changes", [{"flags": 0}, {"start_ticks": 4}, {"private_resident_bytes": 0}])
def test_unverified_transition_rejected(changes):
    values = iter([row(), exiting(**changes)])
    backend = b4.LinuxB4Backend([0], "taskset", sample_fn=lambda *_: next(values), host_fn=lambda: {"timestamp_ns": time.monotonic_ns()})
    child = SimpleNamespace(pid=11, poll=lambda: None)
    samples = []
    backend.sample({"source": child}, samples)
    with pytest.raises((RuntimeError, ValueError)):
        backend.sample({"source": child}, samples)


def test_permission_fallback_is_exiting_only(monkeypatch):
    def denied(*_):
        raise PermissionError("original denial")

    monkeypatch.setattr(b4, "sample_linux_process", denied)

    def partial(*args, **kwargs):
        assert kwargs == {"allow_exiting": True}
        return exiting()

    monkeypatch.setattr(b4, "sample_process", partial, raising=False)
    assert b4.sample_b4_process(11, [0])["memory_state"] == "UNAVAILABLE_EXITING"
    monkeypatch.setattr(b4, "sample_process", lambda *a, **kw: row(), raising=False)
    with pytest.raises(PermissionError, match="original denial"):
        b4.sample_b4_process(11, [0])


def test_exit_without_prior_live_identity_rejected():
    backend = b4.LinuxB4Backend([0], "taskset", sample_fn=lambda *_: exiting(), host_fn=lambda: {"timestamp_ns": time.monotonic_ns()})
    with pytest.raises(RuntimeError, match="unverified"):
        backend.sample({"source": SimpleNamespace(pid=11, poll=lambda: None)}, [])


def test_exiting_cannot_return_to_live():
    values = iter([row(), exiting(), row(timestamp_ns=3, cpu_ns=30)])
    backend = b4.LinuxB4Backend([0], "taskset", sample_fn=lambda *_: next(values), host_fn=lambda: {"timestamp_ns": time.monotonic_ns()})
    child = SimpleNamespace(pid=11, poll=lambda: None)
    samples = []
    backend.sample({"source": child}, samples)
    backend.sample({"source": child}, samples)
    with pytest.raises(RuntimeError, match="returned live"):
        backend.sample({"source": child}, samples)
