"""Final CPU evidence must survive Linux's inaccessible zombie FD directory."""
from pathlib import Path

import pytest

from scripts.performance.linux_loopback import sample_process


def stat(state, *, pid=123, start=99, cpu=10):
    fields = [state] + ["0"] * 49
    fields[11], fields[19] = str(cpu), str(start)
    return f"{pid} (peer) " + " ".join(fields)


def fixture(root, state="S"):
    base = root / "123"
    task = base / "task" / "123"
    task.mkdir(parents=True)
    (task / "status").write_text("Cpus_allowed_list:\t0\n")
    (task / "children").write_text("")
    (base / "stat").write_text(stat(state))
    (base / "fd").mkdir()
    (base / "fd" / "0").touch()
    return base


def test_known_zombie_does_not_enumerate_fd_and_preserves_final_cpu(tmp_path, monkeypatch):
    base = fixture(tmp_path, "Z")
    original = Path.iterdir

    def guarded(path):
        assert path != base / "fd", "zombie FD directory must not be enumerated"
        return original(path)

    monkeypatch.setattr(Path, "iterdir", guarded)
    sample = sample_process(123, [0], tmp_path, 100, 4096)
    assert sample["state"] == "Z"
    assert sample["fd_count"] is None
    assert sample["fd_count_state"] == "UNAVAILABLE_ZOMBIE"
    assert sample["start_ticks"] == 99 and sample["cpu_ns"] == 100_000_000
    assert sample["thread_ids"] == [123]


@pytest.mark.parametrize("final_state,start,pid", [("Z", 99, 123), ("S", 99, 123), ("Z", 100, 123), ("Z", 99, 124)])
def test_fd_permission_race_requires_same_identity_zombie(tmp_path, monkeypatch, final_state, start, pid):
    base = fixture(tmp_path)
    original = Path.iterdir

    def exiting(path):
        if path == base / "fd":
            (base / "stat").write_text(stat(final_state, pid=pid, start=start, cpu=20))
            raise PermissionError(13, "FD unavailable")
        return original(path)

    monkeypatch.setattr(Path, "iterdir", exiting)
    if (final_state, start, pid) != ("Z", 99, 123):
        with pytest.raises((PermissionError, RuntimeError)):
            sample_process(123, [0], tmp_path, 100, 4096)
    else:
        sample = sample_process(123, [0], tmp_path, 100, 4096)
        assert sample["state"] == "Z" and sample["start_ticks"] == 99
        assert sample["cpu_ns"] == 200_000_000  # Re-read final CPU, not stale live CPU.
        assert sample["fd_count"] is None
        assert sample["fd_count_state"] == "UNAVAILABLE_ZOMBIE"


def test_live_fd_count_remains_measured(tmp_path):
    fixture(tmp_path)
    sample = sample_process(123, [0], tmp_path, 100, 4096)
    assert sample["fd_count"] == 1
    assert sample["fd_count_state"] == "MEASURED"
