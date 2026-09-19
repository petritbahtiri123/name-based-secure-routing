"""Read-only native IPv4/UDP pcapng accounting, not physical-wire acceptance."""

import argparse
import ipaddress
import json
import mmap
from pathlib import Path
import re
import struct

from scripts.analyze_b1_v2_capture import capture_drop_counts
from scripts.performance.linux_b5_ceiling import require
from scripts.performance.linux_loopback import digest


def endpoint(value):
    host, port = value
    address = ipaddress.IPv4Address(host)
    require(not (address.is_unspecified or address.is_loopback or address.is_multicast)
            and str(address) != '255.255.255.255', 'native unicast IPv4 endpoint required')
    require(type(port) is int and 0 < port <= 65535, 'invalid UDP port')
    return str(address), port


def options(data, endian):
    result, offset = {}, 0
    while offset < len(data):
        require(offset + 4 <= len(data), 'truncated pcapng option')
        kind, length = struct.unpack_from(endian + 'HH', data, offset)
        offset += 4
        require(offset + ((length + 3) & ~3) <= len(data), 'truncated pcapng option value')
        if kind == 0:
            require(length == 0 and offset == len(data), 'invalid pcapng end option')
            return result
        result.setdefault(kind, []).append(bytes(data[offset:offset + length]))
        offset += (length + 3) & ~3
    return result


def packet_fields(frame, client, server, mtu):
    require(len(frame) >= 42 and frame[12:14] == b'\x08\x00',
            'requires untagged Ethernet IPv4/UDP; VLAN/tunnels unsupported')
    ip = frame[14:]
    header, length = (ip[0] & 15) * 4, int.from_bytes(ip[2:4], 'big')
    require(ip[0] >> 4 == 4 and 20 <= header <= 60 and header + 8 <= length <= len(ip)
            and ip[9] == 17, 'invalid IPv4/UDP lengths or protocol')
    require(length <= mtu, 'packet exceeds declared MTU; segmentation/coalescing unsupported')
    require(int.from_bytes(ip[6:8], 'big') & 0xBFFF == 0, 'IPv4 fragment/reserved flag unsupported')
    source_port, destination_port, udp_length = struct.unpack_from('!HHH', ip, header)
    require(udp_length >= 8 and length == header + udp_length, 'inconsistent UDP/IP length')
    source = (str(ipaddress.IPv4Address(bytes(ip[12:16]))), source_port)
    destination = (str(ipaddress.IPv4Address(bytes(ip[16:20]))), destination_port)
    require((source, destination) in ((client, server), (server, client)), 'unrelated IPv4/UDP flow')
    return ('client_to_server' if source == client else 'server_to_client'), dict(
        packet_count=1, captured_frame_bytes=len(frame), ip_bytes=length,
        udp_bytes=udp_length, udp_payload_bytes=udp_length - 8)


def zero_drops(values, kinds, endian):
    for kind in kinds:
        counters = values.get(kind, [])
        require(len(counters) <= 1, 'ambiguous embedded drop counter')
        for counter in counters:
            require(len(counter) == 8 and struct.unpack(endian + 'Q', counter)[0] == 0,
                    'nonzero/unknown embedded capture drops')


def account_capture(data, *, interface, client, server, drop_log, mtu=1500):
    client, server = endpoint(client), endpoint(server)
    require(client[0] != server[0], 'native endpoints must use distinct addresses')
    require(re.fullmatch('[A-Za-z0-9_][A-Za-z0-9_.:-]{0,14}', interface)
            and interface not in ('lo', 'any'), 'one named native interface required')
    require(type(mtu) is int and 68 <= mtu <= 65535, 'invalid MTU')
    drops = capture_drop_counts(drop_log)
    require(drops['interface'] == interface, 'drop-log interface mismatch')
    require(28 <= len(data) <= 2 * 1024**3 and data[:4] == b'\x0a\x0d\x0d\x0a',
            'complete bounded pcapng capture required')
    endian = {b'\x4d\x3c\x2b\x1a': '<', b'\x1a\x2b\x3c\x4d': '>'}.get(bytes(data[8:12]))
    require(endian is not None, 'invalid pcapng byte order')
    totals = dict(packet_count=0, captured_frame_bytes=0, ip_bytes=0, udp_bytes=0, udp_payload_bytes=0)
    directions = {name: dict(totals) for name in ('client_to_server', 'server_to_client')}
    offset, interfaces = 0, 0
    while offset < len(data):
        require(offset + 12 <= len(data), 'truncated pcapng block')
        kind, size = struct.unpack_from(endian + 'II', data, offset)
        require(12 <= size <= 1048576 and size % 4 == 0 and offset + size <= len(data), 'invalid pcapng block size')
        require(struct.unpack_from(endian + 'I', data, offset + size - 4)[0] == size,
                'pcapng block trailer mismatch')
        body = data[offset + 8:offset + size - 4]
        if kind == 0x0A0D0D0A:
            require(offset == 0 and len(body) >= 16, 'multiple/short pcapng section')
            require(struct.unpack_from(endian + 'HH', body, 4) == (1, 0), 'unsupported pcapng version')
            options(body[16:], endian)
        elif kind == 1:
            require(interfaces == 0 and len(body) >= 8, 'multiple/short interface block')
            linktype, reserved, snaplen = struct.unpack_from(endian + 'HHI', body)
            require(linktype == 1 and reserved == 0 and snaplen >= mtu + 14, 'unsupported interface encapsulation/snaplen')
            names = options(body[8:], endian).get(2, [])
            require(names == [interface.encode()], 'pcapng interface name mismatch/ambiguity')
            interfaces += 1
        elif kind == 6:
            require(interfaces == 1 and len(body) >= 20, 'packet without complete interface')
            interface_id, _, _, captured, original = struct.unpack_from(endian + 'IIIII', body)
            padded = (captured + 3) & ~3
            require(interface_id == 0 and captured == original and captured <= snaplen and 20 + padded <= len(body),
                    'truncated packet or wrong interface')
            zero_drops(options(body[20 + padded:], endian), (4,), endian)
            direction, fields = packet_fields(body[20:20 + captured], client, server, mtu)
            for name, value in fields.items():
                totals[name] += value
                directions[direction][name] += value
        elif kind == 5:
            require(interfaces == 1 and len(body) >= 12 and struct.unpack_from(endian + 'I', body)[0] == 0,
                    'invalid interface statistics block')
            # Optional embedded loss must not contradict the required dumpcap log.
            zero_drops(options(body[12:], endian), (5, 7), endian)
        else:
            raise ValueError('unsupported pcapng block; no silent packet or metadata omission')
        offset += size
    require(totals['packet_count'] == drops['captured'], 'capture packet inventory does not reconcile')
    require(all(row['packet_count'] for row in directions.values()), 'bidirectional workload packets required')
    return dict(schema='nbsr-native-packet-accounting-v1', status='DIAGNOSTIC_PACKET_ACCOUNTING_ONLY',
        interface=interface, client=list(client), server=list(server), declared_mtu=mtu,
        **totals, directions=directions, capture_drops=drops, physical_wire_bytes=None,
        readiness_and_terminal_coverage='NOT_PROVEN', setup_vs_established='NOT_PROVEN',
        offload_state='NOT_PROVEN', performance_timing='NOT_QUALIFIED',
        packet_checksums='NOT_VALIDATED; transmit checksum offload may affect captured headers',
        scope='Whole retained exact flow only. Capture truncation in time is not excluded. '
              'Captured frame bytes may include padding/FCS; preamble/IFG/physical wire not inferred. '
              'No workload completion, ownership, Direct/NBSR equivalence or overhead claim.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pcap', type=Path, required=True)
    parser.add_argument('--drop-log', type=Path, required=True)
    parser.add_argument('--interface', required=True)
    parser.add_argument('--client', required=True, help='Exact IPv4:UDP-port')
    parser.add_argument('--server', required=True, help='Exact IPv4:UDP-port')
    parser.add_argument('--mtu', type=int, required=True)
    args = parser.parse_args()
    peers = {name: (getattr(args, name).rsplit(':', 1)[0], int(getattr(args, name).rsplit(':', 1)[1]))
             for name in ('client', 'server')}
    with args.drop_log.open() as stream:
        log = stream.read(1048577)
    require(len(log) <= 1048576, 'drop log exceeds bound')
    with args.pcap.open('rb') as stream:
        require(28 <= args.pcap.stat().st_size <= 2 * 1024**3, 'capture exceeds file bound')
        with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
            result = account_capture(data, interface=args.interface, drop_log=log, mtu=args.mtu, **peers)
    result.update(pcap_sha256=digest(args.pcap), drop_log_sha256=digest(args.drop_log))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
