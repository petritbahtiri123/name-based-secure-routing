import json

import pytest

from scripts import run_b3_session_lifecycle as b3


class Marker:
    name = "destination-0.active"

    def __init__(self, replies):
        self.replies = iter(replies)

    def read_text(self, **_kwargs):
        value = next(self.replies)
        if isinstance(value, Exception):
            raise value
        return value


def clock(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(b3.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(b3.time, "sleep", lambda seconds: now.__setitem__(0, now[0] + seconds))
    return now


def test_transient_marker_sharing_failure_is_retried_inside_original_gate(monkeypatch):
    now = clock(monkeypatch)
    marker = Marker([PermissionError(13, "sharing"), '{"ready":true}'])
    assert b3.wait_json_paths([marker], [], .1) == [{"ready": True}]
    assert 0 < now[0] <= .1


def test_missing_and_locked_markers_share_one_deadline(monkeypatch):
    now = clock(monkeypatch)
    marker = Marker([FileNotFoundError()] + [PermissionError()] * 20)
    with pytest.raises(RuntimeError, match="JSON marker timeout"):
        b3.wait_json_paths([marker], [], .025)
    assert now[0] == .025


def test_malformed_published_json_is_not_retried(monkeypatch):
    now = clock(monkeypatch)
    with pytest.raises(json.JSONDecodeError):
        b3.wait_json_paths([Marker(["invalid"])], [], 1)
    assert now[0] == 0


def test_failed_child_does_not_wait_for_locked_marker(monkeypatch):
    clock(monkeypatch)

    class Failed:
        returncode = 7

        def poll(self):
            return self.returncode

    with pytest.raises(RuntimeError, match="process exited"):
        b3.wait_json_paths([Marker([PermissionError()])], [Failed()], 120)
