import json
from types import SimpleNamespace

import pytest

from tests.performance.test_linux_native_packet_accounting import CLIENT, SERVER, capture, frame
from tests.performance.test_native_packet_markers import PROBE, marker


def observer(**kwargs):
    from scripts.performance.linux_native_capture import NativePacketObserver
    return NativePacketObserver('dumpcap', 'tshark', interface=kwargs.get('interface', 'eth0'),
        local_address=CLIENT[0], server=kwargs.get('server', SERVER), probe_port=kwargs.get('probe_port', 44000))


def test_capture_filter_and_bounds_are_specific_and_do_not_capture_unrelated_hosts(tmp_path):
    value = observer()
    value.probe = PROBE
    argv = value.capture_command(SERVER[1], tmp_path / 'native.pcapng')
    expression = argv[argv.index('-f') + 1]
    assert CLIENT[0] in expression and SERVER[0] in expression
    assert 'src port 43000' in expression and 'dst port 44000' in expression
    assert 'duration:120' in argv and 'filesize:2097152' in argv
    assert '-p' in argv and argv[argv.index('-s') + 1] == '0'
    assert value.capture_name == 'native.pcapng'
    assert value.export_timeout == 30


@pytest.mark.parametrize('kwargs', [dict(interface='any'), dict(interface='lo'), dict(interface='../../eth0'),
                                   dict(probe_port=SERVER[1]), dict(server=('127.0.0.1', 1234))])
def test_capture_rejects_ambiguous_interface_or_probe_endpoint(kwargs):
    with pytest.raises(ValueError):
        observer(**kwargs)


def test_native_accounting_requires_unique_workload_flow_and_resets_valid_on_failure(tmp_path):
    value = observer()
    value.probe = PROBE | dict(status='PASS', terminal_status='PASS')
    value.report.update(valid=True, packet_count=2, flows=[dict(client_port=CLIENT[1])])
    (tmp_path / 'native.pcapng').write_bytes(capture([marker(), frame(), frame(SERVER, CLIENT), marker(True)]))
    (tmp_path / 'dumpcap.stderr').write_text("Packets captured: 4\nPackets received/dropped on interface 'eth0': 4/0 "
                                           "(pcap:0/dumpcap:0/flushed:0/ps_ifdrop:0)\n")
    value.account_native(tmp_path)
    assert value.report['packet_accounting']['packet_count'] == 2
    assert value.report['endpoint_process_ownership'] == 'NOT_PROVEN'
    value.report['flows'].append(dict(client_port=41001))
    with pytest.raises(ValueError, match='flow'):
        value.account_native(tmp_path)
    assert value.report['valid'] is False


def test_exited_capture_cannot_generate_a_terminal_marker(tmp_path):
    value = observer()
    value.probe = PROBE.copy()
    with pytest.raises(RuntimeError, match='exited'):
        value.finish_capture(SimpleNamespace(poll=lambda: 0), tmp_path / 'native.pcapng', tmp_path)


def test_stop_file_requires_exact_fresh_token_and_bounded_identity(tmp_path):
    from scripts.performance.linux_native_capture import stop_requested
    path = tmp_path / 'capture-stop.json'
    assert stop_requested(path, 'abc') is False
    path.write_text(json.dumps(dict(token='other')))
    with pytest.raises(ValueError, match='token'):
        stop_requested(path, 'abc')
    path.write_text(json.dumps(dict(token='abc')))
    assert stop_requested(path, 'abc') is True
