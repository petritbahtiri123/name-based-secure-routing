import hashlib
import subprocess
import sys
from contextlib import contextmanager
import time

import pytest

from scripts.benchmark_postclose import finalize_after_owner


class FixtureOwner:
    """One real idle child only; no claim of descendant or production Job proof."""

    def __init__(self, events):
        self.events = events
        self.child = subprocess.Popen(
            [sys.executable, "-I", "-B", "-c", "import sys;sys.stdin.buffer.read()"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def finish(self):
        self.child.stdin.close()
        try:
            self.child.wait(timeout=5)
        finally:
            if self.child.poll() is None:
                self.child.kill()
                self.child.wait(timeout=5)
        self.events.append("terminal")
        return dict(
            run="fixture",
            leader_reaped=True,
            group_exit_observed=True,
            owned_handles=False,
            drain_failure=None,
            cleanup_errors=[],
            exit_code=self.child.returncode,
        )


def proof():
    parent = dict(
        leader_reaped=True,
        group_exit_observed=True,
        owned_handles=False,
        drain_failure=None,
        cleanup_errors=[],
        exit_code=1,
        status="INVALID_PARTIAL",
    )
    role = dict(
        SERVICE_RESULT="success",
        EXIT_CODE="exited",
        EXIT_STATUS="0",
        tls_cleanup="REMOVED",
        cgroup_absent=True,
        tls_holder_absent=True,
        tls_path_absent=True,
        mountpoint_cleanup="CONFIRMED",
    )
    return dict(
        run="fixture",
        parent=parent,
        capture=dict(
            readers_quiescent=True,
            reader_count=2,
            reader_start_uncertain=False,
            status="CAPTURE_FAILED",
        ),
        remote=dict(
            errors={},
            receipts={
                r: dict(role, role=r, unit=r + "-unit", cgroup="/" + r)
                for r in ("source", "destination")
            },
        ),
        publisher=dict(dispatched=False, no_dispatch_confirmed=True),
    )


def setup(tmp_path):
    data = b"closed evidence\n"
    (tmp_path / "closed.log").write_bytes(data)
    return {
        "closed.log": dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    }


def reservations(events, **updates):
    @contextmanager
    def reserve(request):
        events.append("reserve")
        value = dict(
            request,
            existing_bytes=1000,
            external_reserved_bytes=1000,
            reservation_held=True,
            observed_monotonic=time.monotonic(),
        )
        value.update(updates)
        try:
            yield value
        finally:
            events.append("release")

    return reserve


def call(tmp_path, *, value=None, updates=None, events=None, owner=None):
    events = [] if events is None else events
    expected = setup(tmp_path)

    def observe():
        events.append("observe")
        return proof() if value is None else value

    return finalize_after_owner(
        owner or FixtureOwner(events),
        run="fixture",
        observe=observe,
        reserve=reservations(events, **(updates or {})),
        root=tmp_path,
        archive=tmp_path / "result.zip",
        expected=expected,
        maximum_archive_bytes=4096,
        metadata_bytes=1024,
        expected_remote={
            "source": ("source-unit", "/source"),
            "destination": ("destination-unit", "/destination"),
        },
    )


def test_real_child_terminal_then_archive_invalid_evidence(tmp_path):
    events = []
    result = call(tmp_path, events=events)
    assert events == ["terminal", "observe", "reserve", "release"]
    assert result["measurement_status"] == "INVALID_PARTIAL"
    assert result["archive"]["status"] == "VERIFIED_ZIP_ORIGINALS_RETAINED"
    assert (tmp_path / "closed.log").read_bytes() == b"closed evidence\n"


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("parent", "owned_handles", True),
        ("parent", "leader_reaped", False),
        ("parent", "drain_failure", "unknown"),
        ("capture", "readers_quiescent", False),
        ("capture", "reader_start_uncertain", True),
        ("capture", "reader_count", 1),
        ("publisher", "no_dispatch_confirmed", False),
    ],
)
def test_uncertain_closure_never_reserves_or_archives(tmp_path, section, key, value):
    p = proof()
    p[section][key] = value
    events = []
    with pytest.raises(ValueError):
        call(tmp_path, value=p, events=events)
    assert "reserve" not in events and not (tmp_path / "result.zip").exists()


@pytest.mark.parametrize(
    "change",
    [
        {"existing_bytes": 157286400},
        {"reservation_held": False},
        {"restore_bytes": 0},
        {"external_reserved_bytes": True},
    ],
)
def test_space_failures_preserve_original(tmp_path, change):
    with pytest.raises(ValueError):
        call(tmp_path, updates=change)
    assert (tmp_path / "closed.log").exists() and not (tmp_path / "result.zip").exists()


def test_remote_identity_mismatch_rejected(tmp_path):
    p = proof()
    p["remote"]["receipts"]["source"]["unit"] = "another-run"
    with pytest.raises(ValueError):
        call(tmp_path, value=p)
    assert not (tmp_path / "result.zip").exists()


def test_missing_publisher_not_inferred_closed(tmp_path):
    p = proof()
    del p["publisher"]
    with pytest.raises(ValueError):
        call(tmp_path, value=p)


def test_duplicate_archive_not_overwritten(tmp_path):
    call(tmp_path)
    before = (tmp_path / "result.zip").read_bytes()
    with pytest.raises(FileExistsError):
        call(tmp_path)
    assert (tmp_path / "result.zip").read_bytes() == before


def test_active_launcher_receipt_rejected(tmp_path):
    class NotTerminal:
        def finish(self):
            return dict(run="fixture", leader_reaped=False)

    with pytest.raises(ValueError):
        call(tmp_path, owner=NotTerminal())
    assert not (tmp_path / "result.zip").exists()


@pytest.mark.parametrize(
    "name",
    [
        "lab.sqlite",
        "lab.sqlite-wal",
        "dashboard/state.json",
        "source-manifest.json",
        "pending/item.log",
        "owner.lock",
        "binary.exe",
    ],
)
def test_operational_paths_never_admitted(name):
    from scripts.benchmark_postclose import _static_inventory

    with pytest.raises(ValueError):
        _static_inventory({name: dict(bytes=0, sha256=hashlib.sha256(b"").hexdigest())})


def test_stale_reservation_rejected(tmp_path):
    with pytest.raises(ValueError):
        call(tmp_path, updates={"observed_monotonic": time.monotonic() - 10})
    assert not (tmp_path / "result.zip").exists()


def test_dispatched_publisher_requires_own_terminal_receipt(tmp_path):
    p = proof()
    p["publisher"] = dict(
        dispatched=True, cleanup_confirmed=True, terminal=dict(p["parent"])
    )
    assert call(tmp_path, value=p)["originals_retained"] is True


def test_dispatched_publisher_retains_handles_blocks_archive(tmp_path):
    p = proof()
    p["publisher"] = dict(
        dispatched=True,
        cleanup_confirmed=True,
        terminal=dict(p["parent"], owned_handles=True),
    )
    with pytest.raises(ValueError):
        call(tmp_path, value=p)
    assert not (tmp_path / "result.zip").exists()


def test_remote_cleanup_error_blocks_archive(tmp_path):
    p = proof()
    p["remote"]["errors"] = {"source": "unconfirmed"}
    with pytest.raises(ValueError):
        call(tmp_path, value=p)
    assert not (tmp_path / "result.zip").exists()


def test_archive_failure_releases_reservation_and_retains_source(tmp_path, monkeypatch):
    from scripts import benchmark_postclose as module

    events = []

    def failed(*args, **kwargs):
        events.append("archive")
        raise OSError("injected archive failure")

    monkeypatch.setattr(module, "create_verified_zip", failed)
    with pytest.raises(OSError):
        call(tmp_path, events=events)
    assert events == ["terminal", "observe", "reserve", "archive", "release"]
    assert (tmp_path / "closed.log").read_bytes() == b"closed evidence\n"
