import pytest

from scripts import run_b3_session_lifecycle as b3


def test_final_cooldown_precedes_report_release(monkeypatch, tmp_path):
    events = []
    release = tmp_path / "destination.report-release"

    def ready(paths, processes, timeout):
        assert paths == [tmp_path / "destination.report-ready"]
        assert timeout == 120
        events.append("ready")

    def capture(*args, **kwargs):
        assert events == ["ready"]
        assert kwargs["phase"] == "cooldown" and kwargs["cycle"] == 49
        assert not release.exists()
        events.append("cooldown")

    monkeypatch.setattr(b3, "wait_paths", ready)
    monkeypatch.setattr(b3, "capture", capture)
    phase = b3.capture_final_cooldown([], object(), [], tmp_path,
                                     cycle=49, seconds=2, cadence=0.5,
                                     report_gate=True)
    assert events == ["ready", "cooldown"]
    assert release.read_text() == "release\n"
    assert phase["phase"] == "report_generation"
    assert phase["started_unix_ns"] > 0


def test_failed_cooldown_does_not_release_report(monkeypatch, tmp_path):
    monkeypatch.setattr(b3, "wait_paths", lambda *args: None)

    def fail(*args, **kwargs):
        raise RuntimeError("sampling failed")

    monkeypatch.setattr(b3, "capture", fail)
    with pytest.raises(RuntimeError, match="sampling failed"):
        b3.capture_final_cooldown([], object(), [], tmp_path,
                                 cycle=0, seconds=2, cadence=0.5,
                                 report_gate=True)
    assert not (tmp_path / "destination.report-release").exists()


@pytest.mark.parametrize("role", ["destination", "source"])
def test_capture_skips_exit_race_only_after_fresh_poll(monkeypatch, role):
    class Process:
        pid = 123

        def __init__(self, statuses):
            self.statuses = iter(statuses)

        def poll(self):
            return next(self.statuses)

    def missing(pid):
        raise ProcessLookupError(pid)

    clock = iter([0, 0, 2])
    monkeypatch.setattr(b3.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(b3.time, "sleep", lambda _: None)
    monkeypatch.setattr(b3, "sample_windows_process", missing)
    process = Process([None, 0])
    destination = process if role == "destination" else Process([0])
    clients = [process] if role == "source" else []
    samples = []
    b3.capture(samples, destination, clients, phase="cooldown", cycle=0, seconds=1, cadence=0.5)
    assert samples == []


def test_capture_propagates_sampling_failure_for_live_process(monkeypatch):
    class Process:
        pid = 123

        def poll(self):
            return None

    def missing(pid):
        raise ProcessLookupError(pid)

    monkeypatch.setattr(b3, "sample_windows_process", missing)
    with pytest.raises(ProcessLookupError):
        b3.capture([], Process(), [], phase="active", cycle=0, seconds=1, cadence=0.5)
