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

SNMP = 'Ip: Forwarding DefaultTTL\nIp: 1 64\nUdp: InDatagrams NoPorts InErrors OutDatagrams RcvbufErrors SndbufErrors InCsumErrors IgnoredMulti MemErrors\nUdp: 12 0 7 15 6 0 1 0 0\n'


def test_parse_udp_namespace_mib():
    value = module().parse_udp_mib(SNMP)
    assert value['RcvbufErrors'] == 6 and value['InErrors'] == 7
    assert value['InCsumErrors'] == 1


@pytest.mark.parametrize('text', [
    'Ip: A\nIp: 1\n',
    SNMP + 'Udp: A\nUdp: 1\n',
    SNMP.replace('12 0 7', '12 0 -7'),
    SNMP.replace('12 0 7', '12 0'),
    SNMP.replace('NoPorts', 'InDatagrams'),
    SNMP.replace('12 0 7', '12 0 18446744073709551616'),
])
def test_udp_mib_rejects_ambiguous_or_malformed(text):
    with pytest.raises(ValueError):
        module().parse_udp_mib(text)


def test_failure_snapshot_attaches_namespace_not_socket_mib(tmp_path, monkeypatch):
    udp = module()
    base = tmp_path / '11'
    (base / 'fd').mkdir(parents=True)
    (base / 'net').mkdir()
    (base / 'fd' / '3').touch()
    (base / 'stat').write_text(stat())
    (base / 'net' / 'udp').write_text(HEADER + ROW)
    (base / 'net' / 'udp6').write_text(HEADER.replace('rem_address', 'remote_address'))
    (base / 'net' / 'snmp').write_text(SNMP)
    monkeypatch.setattr(os, 'readlink', lambda path: 'socket:[99]')
    children = {'destination': SimpleNamespace(pid=11, poll=lambda: None)}
    result = udp.capture_owned_udp(children, {11: 3}, proc_root=tmp_path)['roles']['destination']
    assert result['live_socket_drops'] == 42
    mib = result['namespace_udp_mib']
    assert mib['status'] == 'MEASURED_NAMESPACE_CUMULATIVE'
    assert mib['counters']['RcvbufErrors'] == 6
    assert 'not per-socket' in mib['scope']
    (base / 'net' / 'snmp').unlink()
    result = udp.capture_owned_udp(children, {11: 3}, proc_root=tmp_path)['roles']['destination']
    assert result['status'] == 'MEASURED_FAILURE_SNAPSHOT'
    assert result['namespace_udp_mib']['status'] == 'UNAVAILABLE'
    # Reading MIB must remain inside the owned-process epoch guard.
    original = udp.read_bounded
    def switched(path, limit=8 * 1024 * 1024):
        if path.name == 'snmp':
            (base / 'stat').write_text(stat(4))
            return SNMP
        return original(path, limit)
    monkeypatch.setattr(udp, 'read_bounded', switched)
    assert udp.capture_owned_udp(children, {11: 3}, proc_root=tmp_path)['roles']['destination']['status'] == 'UNAVAILABLE'
