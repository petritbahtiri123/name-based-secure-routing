"""Strict IPv4 loopback packet accounting; no physical Ethernet inference."""
from __future__ import annotations

import re
import struct
import ipaddress


def probe_tokens(probe):
    tokens = {bytes.fromhex(probe["token_hex"])}
    if "terminal_token_hex" in probe:
        terminal = bytes.fromhex(probe["terminal_token_hex"])
        if terminal in tokens:
            raise ValueError("terminal probe token must be distinct")
        tokens.add(terminal)
    if any(len(token) != 32 for token in tokens):
        raise ValueError("readiness probe token must have 32 bytes")
    return tokens


def probe_frames_from_pcapng(data, probe, *, expected_linktype=0):
    """Inspect explicitly declared NULL/Ethernet IPv4 EPBs; final uses TShark.

    A trailing block being written is ignored, never interpreted as a packet.
    This avoids launching an offline reader against a file still held by dumpcap.
    """
    if expected_linktype not in (0, 1):
        raise ValueError("unsupported readiness link type")
    probe_addresses = (ipaddress.IPv4Address(probe.get('source_address', '127.0.0.1')).packed
                       + ipaddress.IPv4Address(probe.get('destination_address', '127.0.0.1')).packed)
    if len(data) < 28:
        return {}
    if data[:4] != b"\x0a\x0d\x0d\x0a":
        raise ValueError("readiness requires pcapng section header")
    magic = data[8:12]
    endian = "<" if magic == b"\x4d\x3c\x2b\x1a" else ">" if magic == b"\x1a\x2b\x3c\x4d" else None
    if endian is None:
        raise ValueError("invalid pcapng byte order")
    offset, number = 0, 0
    interfaces, payloads = [], {}
    while offset + 12 <= len(data):
        kind, length = struct.unpack_from(endian + "II", data, offset)
        if length < 12 or length % 4:
            raise ValueError("invalid pcapng block length")
        if offset + length > len(data):
            break
        if struct.unpack_from(endian + "I", data, offset + length - 4)[0] != length:
            raise ValueError("pcapng block trailer mismatch")
        body = data[offset + 8:offset + length - 4]
        if kind == 0x0A0D0D0A and offset:
            raise ValueError("multiple readiness capture sections")
        if kind == 1:
            if len(body) < 8:
                raise ValueError("short pcapng interface block")
            interfaces.append(struct.unpack_from(endian + "H", body)[0])
        elif kind in (2, 3):
            raise ValueError("unsupported readiness packet block")
        elif kind == 6:
            number += 1
            if len(body) < 20:
                raise ValueError("short enhanced packet block")
            interface, _, _, captured, original = struct.unpack_from(endian + "IIIII", body)
            if interface >= len(interfaces) or interfaces[interface] != expected_linktype or captured != original or len(body) < 20 + captured:
                raise ValueError("unexpected readiness encapsulation or truncated packet")
            frame = body[20:20 + captured]
            if expected_linktype == 0:
                if len(frame) < 32 or struct.unpack_from(endian + "I", frame)[0] != 2:
                    raise ValueError("readiness requires NULL IPv4 packet")
                ip = frame[4:]
            else:
                if len(frame) < 42 or frame[12:14] != b"\x08\x00":
                    raise ValueError("readiness requires untagged Ethernet IPv4 packet")
                ip = frame[14:]
            header = (ip[0] & 15) * 4
            if ip[0] >> 4 != 4 or header < 20 or len(ip) < header + 8 or ip[9] != 17:
                raise ValueError("invalid readiness IPv4/UDP header")
            source, destination, udp_length = struct.unpack_from("!HHH", ip, header)
            if (source, destination) == (probe["source_port"], probe["destination_port"]):
                if ip[12:20] != probe_addresses or int.from_bytes(ip[6:8], "big") & 0x3FFF:
                    raise ValueError("invalid readiness probe address or fragment")
                if int.from_bytes(ip[2:4], "big") != header + udp_length or len(ip) != header + udp_length:
                    raise ValueError("invalid readiness probe lengths")
                payload = ip[header + 8:]
                if payload not in probe_tokens(probe):
                    raise ValueError("readiness probe token mismatch")
                payloads[number] = payload.hex()
        offset += length
    return payloads


def capture_drop_counts(stderr):
    captured = re.findall(r"^Packets captured:\s*(\d+)\s*$", stderr, re.MULTILINE)
    stats = re.findall(
        r"^Packets received/dropped on interface '([^']+)': (\d+)/(\d+) "
        r"\(pcap:(\d+)/dumpcap:(\d+)/flushed:(\d+)/ps_ifdrop:(\d+)\)",
        stderr, re.MULTILINE,
    )
    if len(captured) != 1 or len(stats) != 1:
        raise ValueError("missing or ambiguous capture/drop evidence")
    interface, received, dropped, pcap, dumpcap, flushed, interface_drops = stats[0]
    values = {"captured": int(captured[0]), "received": int(received), "dropped": int(dropped),
              "pcap_drops": int(pcap), "dumpcap_drops": int(dumpcap), "flushed": int(flushed),
              "interface_drops": int(interface_drops)}
    if values["captured"] != values["received"] or not values["captured"]:
        raise ValueError("capture packet counts do not reconcile")
    if any(value for key, value in values.items() if key not in {"captured", "received"}):
        raise ValueError("nonzero capture loss")
    return {"interface": interface, **values}


def account_packets(packets, *, server_port, captured_packets, readiness_probe=None, probe_payloads=None):
    if not packets or len(packets) != captured_packets:
        raise ValueError("packet inventory does not cover the entire capture")
    totals = {"captured_frame_bytes": 0, "ip_bytes": 0, "udp_bytes": 0, "udp_payload_bytes": 0}
    flows = set()
    probe_frames = set()
    probe_bytes = 0
    if readiness_probe is not None:
        frame_numbers = [int(p["frame.number"]) for p in packets]
        if frame_numbers != list(range(1, captured_packets + 1)):
            raise ValueError("packet inventory frame numbers are incomplete or duplicated")
        probe_ports = (readiness_probe["source_port"], readiness_probe["destination_port"])
        if server_port in probe_ports or probe_ports[0] == probe_ports[1]:
            raise ValueError("readiness probe must use separate ports")
        tokens = probe_tokens(readiness_probe)
        probe_payloads = probe_payloads or {}
    directions = {"client_to_server": 0, "server_to_client": 0}
    for packet in packets:
        if packet["ip.src"] != "127.0.0.1" or packet["ip.dst"] != "127.0.0.1":
            raise ValueError("unexpected non-loopback IPv4 flow")
        frame, captured, ip, header, udp = (int(packet[key]) for key in
                                           ("frame.len", "frame.cap_len", "ip.len", "ip.hdr_len", "udp.length"))
        fragment_flag = packet["ip.flags.mf"]
        if fragment_flag not in {"0", "1", "False", "True"}:
            raise ValueError("unknown fragmentation flag")
        if fragment_flag in {"1", "True"} or int(packet["ip.frag_offset"]):
            raise ValueError("fragmented traffic requires separate reassembly accounting")
        if frame != captured or frame < ip or not 20 <= header <= 60 or header % 4 or udp < 8 or ip != header + udp:
            raise ValueError("truncated packet or inconsistent layer lengths")
        source, destination = int(packet["udp.srcport"]), int(packet["udp.dstport"])
        if readiness_probe is not None and (source, destination) == probe_ports:
            number = int(packet["frame.number"])
            payload = bytes.fromhex(probe_payloads.get(number, "").replace(":", ""))
            if payload not in tokens or udp - 8 != len(payload):
                raise ValueError("readiness probe payload mismatch or missing evidence")
            probe_frames.add(number)
            probe_bytes += frame
            continue
        if not 0 < source <= 65535 or not 0 < destination <= 65535 or (source == server_port) == (destination == server_port):
            raise ValueError("packet does not belong to the selected server flow")
        outbound = destination == server_port
        flows.add(source if outbound else destination)
        directions["client_to_server" if outbound else "server_to_client"] += 1
        totals["captured_frame_bytes"] += frame
        totals["ip_bytes"] += ip
        totals["udp_bytes"] += udp
        totals["udp_payload_bytes"] += udp - 8
    if len(flows) != 1:
        raise ValueError("multiple client flows in single-connection accounting capture")
    if readiness_probe is not None:
        observed = set(readiness_probe.get("observed_frame_numbers", []))
        if not observed or not observed <= probe_frames or probe_frames != set(probe_payloads):
            raise ValueError("readiness probe inventory does not reconcile")
        if any(bytes.fromhex(probe_payloads[n].replace(":", "")) != bytes.fromhex(readiness_probe["token_hex"]) for n in observed):
            raise ValueError("initial readiness inventory contains terminal marker")
        if "terminal_token_hex" in readiness_probe:
            terminal = set(readiness_probe.get("terminal_observed_frame_numbers", []))
            if not terminal or not terminal <= probe_frames or any(
                    bytes.fromhex(probe_payloads[n].replace(":", "")) != bytes.fromhex(readiness_probe["terminal_token_hex"])
                    for n in terminal):
                raise ValueError("terminal probe inventory does not reconcile")
    return {"schema": "nbsr-b1-v2-loopback-packet-accounting-v1", "packet_count": len(packets) - len(probe_frames),
            "capture_inventory_packets": len(packets), "readiness_probe_packets": len(probe_frames),
            "readiness_probe_frame_bytes": probe_bytes,
            "capture_inventory_frame_bytes": totals["captured_frame_bytes"] + probe_bytes,
            "directions": directions, **totals, "physical_ethernet_bytes": None,
            "scope": "Captured IPv4/UDP workload flow totals, excluding only validated readiness probes; not incremental Direct-versus-NBSR cost by itself."}
