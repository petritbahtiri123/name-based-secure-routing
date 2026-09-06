import json

import pytest

from scripts.performance.b5_ownership import OwnershipHistory, OwnershipTail
from scripts.performance.post_close_cleanup import FIELDS


def snapshot(index, value=1, role="source"):
    return dict(schema="nbsr-rust-ownership-v1", event="diagnostic", role=role,
                timestamp_ns=index * 1_000_000_000,
                phase="b5_initial" if index == 0 else "b5_sample",
                **dict.fromkeys(FIELDS, value))


def test_every_role_required_and_history_bounded():
    history = OwnershipHistory(groups=1, max_samples=100)
    for index in range(80):
        history.accept("source", snapshot(index), index * 1_000_000_000)
    assert history.retained("source") == 60
    with pytest.raises(ValueError, match="missing"):
        history.finish(duration_ns=70_000_000_000)
    for index in range(80):
        value = snapshot(index, role="destination")
        value["phase"] = "initial" if index == 0 else "sample"
        history.accept("destination_0", value, index * 1_000_000_000)
    assert history.finish(duration_ns=70_000_000_000)["classification"] == "SAMPLED_NO_SUSTAINED_GROWTH"


@pytest.mark.parametrize("change", ["boolean", "missing", "wrong_role", "clock", "overflow"])
def test_invalid_ownership_cannot_pass(change):
    history = OwnershipHistory(groups=1, max_samples=1 if change == "overflow" else 100)
    history.accept("source", snapshot(0), 0)
    value = snapshot(1)
    if change == "boolean":
        value[FIELDS[0]] = True
    elif change == "missing":
        del value[FIELDS[0]]
    elif change == "wrong_role":
        value["role"] = "destination"
    elif change == "clock":
        value["timestamp_ns"] = 0
    with pytest.raises(ValueError):
        history.accept("source", value, 1_000_000_000)


def test_setup_plateau_is_distinct_from_staircase():
    plateau = OwnershipHistory(groups=1, max_samples=100)
    for index in range(60):
        plateau.accept("source", snapshot(index, value=1 if index < 4 else 2), index * 1_000_000_000)
    growing = OwnershipHistory(groups=1, max_samples=100)
    with pytest.raises(ValueError, match="sampled ownership growth"):
        for index in range(60):
            growing.accept("source", snapshot(index, value=index + 1), index * 1_000_000_000)


def test_tail_retains_partial_line_then_rejects_truncated_eof(tmp_path):
    path = tmp_path / "ownership.ndjson"
    received = []
    tail = OwnershipTail(path, lambda value: received.append(value), max_line_bytes=4096)
    assert tail.poll() == 0
    data = json.dumps(snapshot(0, role="destination")).encode()
    path.write_bytes(data[:10])
    assert tail.poll() == 0
    with path.open("ab") as output:
        output.write(data[10:] + b"\n{")
    assert tail.poll() == 1 and len(received) == 1
    with pytest.raises(ValueError, match="partial"):
        tail.finish()
    tail.close()


def test_tail_rejects_duplicate_keys_and_oversized_lines(tmp_path):
    for index, data in enumerate((b'{"x":1,"x":2}\n', b"a" * 100)):
        path = tmp_path / str(index)
        path.write_bytes(data)
        tail = OwnershipTail(path, lambda value: None, max_line_bytes=80)
        with pytest.raises(ValueError):
            tail.poll()
        assert path.read_bytes() == data
        tail.close()


def test_tail_rejects_replaced_file(tmp_path, monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace
    path = tmp_path / "current"
    path.write_bytes(b"{}\n")
    tail = OwnershipTail(path, lambda value: None)
    tail.poll()
    original = path.stat()
    monkeypatch.setattr(Path, "stat", lambda _: SimpleNamespace(
        st_size=original.st_size, st_dev=original.st_dev, st_ino=original.st_ino + 1))
    with pytest.raises(ValueError, match="replaced"):
        tail.poll()
    tail.close()


def test_source_observer_flag_is_opt_in():
    from scripts.run_b5_v2 import source_command
    cell = dict(path="nbsr", endpoint_groups=1, streams_per_group=1,
                outstanding_per_stream=1, payload_bytes=1024)
    arguments = source_command(cell, {"nbsr": "source"}, "authority", ["endpoint"],
                               warmup=3, duration=30, progress=10, rate=(2000, 1),
                               report="cleanup", ownership_sampling=True)
    assert arguments[-2:] == ["--diagnostics", "1"]


def test_silent_controller_polls_ownership():
    from scripts.run_b5_v2 import consume
    class Source:
        def poll(self):
            return None
    class Stream:
        def check(self, **kwargs):
            pass
    called = []
    def poll():
        called.append(True)
        raise ValueError("ownership failed")
    with pytest.raises(ValueError, match="ownership failed"):
        consume(Source(), None, Stream(), poll=poll)
    assert called == [True]
