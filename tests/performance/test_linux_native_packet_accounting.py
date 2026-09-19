import socket
import struct

import pytest


CLIENT = ('192.0.2.10', 41000)
SERVER = ('192.0.2.20', 42000)


def block(kind, data):
    data += b'\0' * (-len(data) % 4)
    length = len(data) + 12
    return struct.pack('<II', kind, length) + data + struct.pack('<I', length)


def option(kind, data):
    return struct.pack('<HH', kind, len(data)) + data + b'\0' * (-len(data) % 4)


def frame(source=CLIENT, destination=SERVER, payload=b'test', **changes):
    udp = struct.pack('!HHHH', source[1], destination[1], 8 + len(payload), 0) + payload
    ip = bytearray(struct.pack('!BBHHHBBH4s4s', 0x45, 0, 20 + len(udp), 1, 0, 64, 17, 0,
                              socket.inet_aton(source[0]), socket.inet_aton(destination[0])) + udp)
    if 'fragment' in changes:
        ip[6:8] = struct.pack('!H', changes['fragment'])
    if 'udp_length' in changes:
        ip[24:26] = struct.pack('!H', changes['udp_length'])
    return b'\1' * 12 + changes.get('ethertype', b'\x08\x00') + ip


def capture(frames=None, *, interface='eth0', linktype=1, truncated=False, extra=b''):
    frames = [frame(), frame(SERVER, CLIENT)] if frames is None else frames
    result = block(0x0A0D0D0A, struct.pack('<IHHq', 0x1A2B3C4D, 1, 0, -1))
    result += block(1, struct.pack('<HHI', linktype, 0, 262144) + option(2, interface.encode()) + option(0, b''))
    for packet in frames:
        result += block(6, struct.pack('<IIIII', 0, 0, 1, len(packet), len(packet) + int(truncated)) + packet)
    return result + extra


def analyze(data, **kwargs):
    from scripts.performance.linux_native_packet_accounting import account_capture
    return account_capture(data, interface='eth0', client=CLIENT, server=SERVER,
                           drop_log="Packets captured: 2\nPackets received/dropped on interface 'eth0': 2/0 "
                                    "(pcap:0/dumpcap:0/flushed:0/ps_ifdrop:0)\n", **kwargs)


def test_counts_raw_complete_native_capture_without_claiming_physical_wire():
    result = analyze(capture())
    assert result['packet_count'] == 2
    assert result['captured_frame_bytes'] == 92
    assert result['ip_bytes'] == 64
    assert result['udp_bytes'] == 24
    assert result['udp_payload_bytes'] == 8
    assert result['directions']['client_to_server']['packet_count'] == 1
    assert result['physical_wire_bytes'] is None
    assert result['readiness_and_terminal_coverage'] == 'NOT_PROVEN'
    assert result['setup_vs_established'] == 'NOT_PROVEN'
    assert result['status'] == 'DIAGNOSTIC_PACKET_ACCOUNTING_ONLY'


@pytest.mark.parametrize('data', [
    capture(interface='other'), capture(linktype=0), capture(truncated=True),
    capture()[:-1], capture(extra=b'x'), capture(extra=block(3, b'\0' * 4)),
    capture() + capture(),
    capture([frame(ethertype=b'\x81\x00'), frame(SERVER, CLIENT)]),
    capture([frame(fragment=0x2000), frame(SERVER, CLIENT)]),
    capture([frame(udp_length=11), frame(SERVER, CLIENT)]),
    capture([frame(source=('192.0.2.11', 41000)), frame(SERVER, CLIENT)]),
    capture([frame(source=(CLIENT[0], 41001)), frame(SERVER, CLIENT)]),
    capture([frame(), frame()]), capture([]),
])
def test_partial_ambiguous_unrelated_or_unsupported_capture_rejects(data):
    with pytest.raises(ValueError):
        analyze(data)


def test_loss_is_rejected_and_not_excused_by_complete_packet_bytes():
    from scripts.performance.linux_native_packet_accounting import account_capture
    with pytest.raises(ValueError, match='loss'):
        account_capture(capture(), interface='eth0', client=CLIENT, server=SERVER,
                        drop_log="Packets captured: 2\nPackets received/dropped on interface 'eth0': 2/1 "
                                 "(pcap:1/dumpcap:0/flushed:0/ps_ifdrop:0)\n")


def test_drop_log_interface_must_match_pcap_interface():
    from scripts.performance.linux_native_packet_accounting import account_capture
    with pytest.raises(ValueError, match='interface'):
        account_capture(capture(), interface='eth0', client=CLIENT, server=SERVER,
                        drop_log="Packets captured: 2\nPackets received/dropped on interface 'other': 2/0 "
                                 "(pcap:0/dumpcap:0/flushed:0/ps_ifdrop:0)\n")


def test_mtu_rejects_coalesced_oversize_and_does_not_infer_offloads_disabled():
    with pytest.raises(ValueError, match='MTU'):
        analyze(capture([frame(payload=b'x' * 1600), frame(SERVER, CLIENT)]), mtu=1500)
    assert analyze(capture())['offload_state'] == 'NOT_PROVEN'


def test_ethernet_padding_is_counted_as_captured_not_udp_payload():
    result = analyze(capture([frame() + b'\0' * 14, frame(SERVER, CLIENT) + b'\0' * 14]))
    assert result['captured_frame_bytes'] == 120
    assert result['udp_payload_bytes'] == 8


def test_pcapng_block_trailer_and_interface_options_are_not_ignored():
    data = bytearray(capture())
    data[-1] ^= 1
    with pytest.raises(ValueError, match='trailer'):
        analyze(data)


def test_unknown_endpoint_or_loopback_is_not_native_capture():
    from scripts.performance.linux_native_packet_accounting import account_capture
    for endpoint in [('0.0.0.0', 1), ('127.0.0.1', 1), ('224.0.0.1', 1), (CLIENT[0], 0)]:
        with pytest.raises(ValueError):
            account_capture(capture(), interface='eth0', client=endpoint, server=SERVER, drop_log='')


@pytest.mark.parametrize('kind', ['interface', 'packet'])
def test_embedded_nonzero_drop_counters_cannot_contradict_zero_loss_log(kind):
    if kind == 'interface':
        data = capture(extra=block(5, struct.pack('<III', 0, 0, 1)
                                   + option(5, struct.pack('<Q', 1)) + option(0, b'')))
    else:
        packet = frame()
        epb = block(6, struct.pack('<IIIII', 0, 0, 1, len(packet), len(packet))
                    + packet + b'\0' * (-len(packet) % 4)
                    + option(4, struct.pack('<Q', 1)) + option(0, b''))
        data = capture(frames=[frame(SERVER, CLIENT)]) + epb
    with pytest.raises(ValueError, match='drop'):
        analyze(data)


def test_big_endian_section_and_zero_embedded_loss_are_supported():
    def big_block(kind, body):
        body += b'\0' * (-len(body) % 4)
        return struct.pack('>II', kind, len(body) + 12) + body + struct.pack('>I', len(body) + 12)
    data = big_block(0x0A0D0D0A, struct.pack('>IHHq', 0x1A2B3C4D, 1, 0, -1))
    data += big_block(1, struct.pack('>HHIHH', 1, 0, 262144, 2, 4) + b'eth0' + b'\0' * 4)
    for packet in (frame(), frame(SERVER, CLIENT)):
        data += big_block(6, struct.pack('>IIIII', 0, 0, 1, len(packet), len(packet)) + packet)
    data += big_block(5, struct.pack('>IIIHHQHH', 0, 0, 1, 5, 8, 0, 0, 0))
    assert analyze(data)['packet_count'] == 2
