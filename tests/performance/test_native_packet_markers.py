import struct

import pytest

from tests.performance.test_linux_native_packet_accounting import CLIENT, SERVER, capture, frame


PROBE = dict(source_address=CLIENT[0], destination_address=SERVER[0], source_port=43000,
             destination_port=44000, token_hex='ab' * 32, terminal_token_hex='cd' * 32)


def marker(terminal=False):
    return frame((CLIENT[0], 43000), (SERVER[0], 44000),
                 bytes.fromhex(PROBE['terminal_token_hex' if terminal else 'token_hex']))


def analyze(frames, probe=None):
    from scripts.performance.linux_native_packet_accounting import account_capture
    n = len(frames)
    log = f"Packets captured: {n}\nPackets received/dropped on interface 'eth0': {n}/0 " \
          "(pcap:0/dumpcap:0/flushed:0/ps_ifdrop:0)\n"
    return account_capture(capture(frames), interface='eth0', client=CLIENT, server=SERVER,
                           drop_log=log, probe=PROBE if probe is None else probe)


def test_declared_markers_are_excluded_but_counted_and_do_not_prove_whole_workload():
    result = analyze([marker(), frame(), frame(SERVER, CLIENT), marker(True)])
    assert result['packet_count'] == 2 and result['capture_inventory_packets'] == 4
    assert result['probe_packet_count'] == 2 and result['probe_frame_bytes'] == 148
    assert result['ip_bytes'] == 64
    assert result['readiness_and_terminal_coverage'] == 'MARKERS_BRACKET_RETAINED_FLOW'
    assert result['setup_vs_established'] == 'NOT_PROVEN'
    assert result['status'] == 'DIAGNOSTIC_PACKET_ACCOUNTING_ONLY'


@pytest.mark.parametrize('frames', [
    [frame(), marker(), frame(SERVER, CLIENT), marker(True)],
    [marker(), frame(), marker(True), frame(SERVER, CLIENT)],
    [marker(), frame(), frame(SERVER, CLIENT)],
    [frame(), frame(SERVER, CLIENT), marker(True)],
    [marker(), frame(), frame(SERVER, CLIENT), marker(), marker(True)],
    [marker(True), frame(), frame(SERVER, CLIENT), marker()],
])
def test_missing_or_misordered_markers_never_allow_silent_truncation(frames):
    with pytest.raises(ValueError, match='marker'):
        analyze(frames)


@pytest.mark.parametrize('change', [dict(source_address='192.0.2.30'), dict(source_port=CLIENT[1]),
                                   dict(terminal_token_hex=PROBE['token_hex']), dict(token_hex='ab')])
def test_marker_identity_and_token_confusion_reject(change):
    with pytest.raises(ValueError):
        analyze([marker(), frame(), frame(SERVER, CLIENT), marker(True)], PROBE | change)


def test_nonloopback_live_prefix_reader_validates_probe_addresses_and_tokens():
    from scripts.analyze_b1_v2_capture import probe_frames_from_pcapng
    data = capture([marker()])
    assert probe_frames_from_pcapng(data, PROBE, expected_linktype=1) == {1: PROBE['token_hex']}
    assert probe_frames_from_pcapng(data + struct.pack('<II', 6, 100), PROBE, expected_linktype=1) == {1: PROBE['token_hex']}
    with pytest.raises(ValueError, match='address'):
        probe_frames_from_pcapng(data, PROBE | {'source_address': '192.0.2.30'}, expected_linktype=1)
