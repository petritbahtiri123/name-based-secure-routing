import os
from types import SimpleNamespace

import pytest

HEADER = "sl local_address rem_address st tx_queue rx_queue tr tm->when retrnsmt uid timeout inode ref pointer drops\n"
ROW = "1: 0100007F:1234 00000000:0000 07 00000000:00000100 00:00000000 00000000 65532 0 99 2 000000003d1e5711 42\n"


def module():
    from scripts.performance import linux_udp_failure

    return linux_udp_failure


def stat(start=3, user_ticks=0, system_ticks=0):
    fields = ["S"] + ["0"] * 49
    fields[11] = str(user_ticks)
    fields[12] = str(system_ticks)
    fields[19] = str(start)
    return "11 (fixture) " + " ".join(fields)


def test_parse_owned_udp_excludes_unowned_and_kernel_pointer():
    values = module().parse_udp(HEADER + ROW + ROW.replace(" 99 ", " 100 "), {99}, family="udp")
    assert len(values) == 1
    assert values[0]["inode"] == 99 and values[0]["drops"] == 42
    assert values[0]["rx_queue_bytes"] == 256
    assert "3d1e5711" not in str(values)


@pytest.mark.parametrize("text", [HEADER + ROW.replace(" 42", " -1"), HEADER + ROW + ROW, "bad\n" + ROW])
def test_malformed_table_is_unavailable(text):
    with pytest.raises(ValueError):
        module().parse_udp(text, {99}, family="udp")


def test_snapshot_requires_prior_owned_identity(tmp_path, monkeypatch):
    udp = module()
    base = tmp_path / "11"
    (base / "fd").mkdir(parents=True)
    (base / "net").mkdir()
    (base / "fd" / "3").touch()
    (base / "stat").write_text(stat(user_ticks=125, system_ticks=75))
    (base / "net" / "udp").write_text(HEADER + ROW)
    (base / "net" / "udp6").write_text(HEADER.replace("rem_address", "remote_address"))
    monkeypatch.setattr(os, "readlink", lambda path: "socket:[99]")
    children = {"destination": SimpleNamespace(pid=11, poll=lambda: None)}
    result = udp.capture_owned_udp(children, {11: 3}, proc_root=tmp_path)
    assert result["roles"]["destination"]["status"] == "MEASURED_FAILURE_SNAPSHOT"
    assert result["roles"]["destination"]["live_socket_drops"] == 42
    assert result["roles"]["destination"]["cpu_ticks"] == 200
    assert result["roles"]["destination"]["cpu_sample_monotonic_ns"] >= result['timestamp_ns']
    assert udp.capture_owned_udp(children, {11: 4}, proc_root=tmp_path)["roles"]["destination"]["status"] == "UNAVAILABLE"
    assert udp.capture_owned_udp(children, {}, proc_root=tmp_path)["roles"]["destination"]["status"] == "UNAVAILABLE"
    (base / "stat").write_text(stat(4))
    assert udp.capture_owned_udp(children, {11: 3}, proc_root=tmp_path)["roles"]["destination"]["status"] == "UNAVAILABLE"


def test_missing_proc_preserves_unavailable(tmp_path):
    child = SimpleNamespace(pid=11, poll=lambda: None)
    result = module().capture_owned_udp({"source": child}, {11: 3}, proc_root=tmp_path)
    assert result["roles"]["source"]["status"] == "UNAVAILABLE"


def test_actual_udp6_header():
    header = HEADER.replace("rem_address", "remote_address")
    assert module().parse_udp(header, set(), family="udp6") == []


def test_bounded_reader_rejects_truncation(tmp_path):
    p = tmp_path / 'bounded'
    p.write_bytes(b'12345')
    with pytest.raises(ValueError, match='bound'):
        module().read_bounded(p, 4)
