from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
from datetime import datetime


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence" / "wp8-task10"
CAPTURE_PORT = 45975
CAPTURE_INTERFACE = r"\Device\NPF_Loopback"
CAPTURE_FILTER = f"udp port {CAPTURE_PORT} and host 127.0.0.1"


def test_capture_wrapper_uses_only_approved_npcap_loopback_flow() -> None:
    script = (ROOT / "scripts" / "capture_wp8_live_interop.ps1").read_text(encoding="utf-8")
    assert "PktMon" not in script
    assert "dumpcap.exe" in script
    assert "tshark.exe" in script
    assert CAPTURE_INTERFACE in script
    assert CAPTURE_FILTER in script
    assert '$captureArguments = "-i `"$captureInterface`" -f `"$captureFilter`"' in script
    assert "-ArgumentList $captureArguments" in script
    assert 'NBSR_WP8_CAPTURE_PORT = "$capturePort"' in script
    assert "Stop-Process" in script
    assert "packet_count" in script
    assert "interface_identifier" in script
    assert "capture_tool_version" in script
    assert "test_correlation" in script


def _enhanced_packets(wire: bytes) -> list[tuple[int, bytes]]:
    packets: list[tuple[int, bytes]] = []
    link_types: list[int] = []
    offset = 0
    endian = "<"
    while offset < len(wire):
        assert offset + 12 <= len(wire)
        block_type = wire[offset : offset + 4]
        if block_type == b"\x0a\x0d\x0d\x0a":
            magic = wire[offset + 8 : offset + 12]
            endian = "<" if magic == b"\x4d\x3c\x2b\x1a" else ">"
        length = struct.unpack_from(endian + "I", wire, offset + 4)[0]
        assert length >= 12 and length % 4 == 0 and offset + length <= len(wire)
        assert struct.unpack_from(endian + "I", wire, offset + length - 4)[0] == length
        if block_type == struct.pack(endian + "I", 1):
            link_types.append(struct.unpack_from(endian + "H", wire, offset + 8)[0])
        if block_type == struct.pack(endian + "I", 6):
            interface_id = struct.unpack_from(endian + "I", wire, offset + 8)[0]
            captured = struct.unpack_from(endian + "I", wire, offset + 20)[0]
            assert interface_id < len(link_types)
            packets.append((link_types[interface_id], wire[offset + 28 : offset + 28 + captured]))
        offset += length
    assert offset == len(wire) and packets
    return packets


def _exact_loopback_udp(link_type: int, packet: bytes, capture_port: int = CAPTURE_PORT) -> tuple[int, int, bytes]:
    assert link_type == 0  # LINKTYPE_NULL from the Npcap loopback adapter.
    assert len(packet) >= 4 + 20 + 8
    assert struct.unpack_from("<I", packet)[0] == 2  # AF_INET
    ip = packet[4:]
    header_length = (ip[0] & 0x0F) * 4
    assert ip[0] >> 4 == 4 and header_length >= 20 and ip[9] == 17
    assert ip[12:16] == b"\x7f\x00\x00\x01"
    assert ip[16:20] == b"\x7f\x00\x00\x01"
    source_port, destination_port = struct.unpack_from("!HH", ip, header_length)
    assert capture_port in (source_port, destination_port)
    udp_length = struct.unpack_from("!H", ip, header_length + 4)[0]
    assert udp_length >= 9 and header_length + udp_length <= len(ip)
    return source_port, destination_port, ip[header_length + 8 : header_length + udp_length]


def test_public_packet_capture_is_real_closed_and_privacy_safe() -> None:
    capture = EVIDENCE / "live-federation.pcapng"
    manifest = json.loads((EVIDENCE / "capture-manifest.json").read_text(encoding="utf-8"))
    wire = capture.read_bytes()
    assert wire[:4] == b"\x0a\x0d\x0d\x0a"
    assert len(wire) >= 256
    assert set(manifest) == {
        "capture",
        "capture_tool_version",
        "interface_identifier",
        "filter",
        "flow",
        "packet_count",
        "dropped_count",
        "length",
        "sha256",
        "privacy",
        "test_correlation",
    }
    assert manifest["capture"] == "live-federation.pcapng"
    assert manifest["capture_tool_version"].startswith("Dumpcap (Wireshark) ")
    assert manifest["interface_identifier"] == CAPTURE_INTERFACE
    assert manifest["filter"] == CAPTURE_FILTER
    assert manifest["flow"] == (f"127.0.0.1 UDP/{CAPTURE_PORT} QUIC/TLS nbsr/1 shared-rust-transport")
    assert manifest["dropped_count"] == 0
    assert manifest["length"] == len(wire)
    assert manifest["sha256"] == hashlib.sha256(wire).hexdigest()
    assert manifest["privacy"] == (
        "public-safe deterministic test identities; no decryption secrets; complete packet inventory allowlisted"
    )
    correlation = manifest["test_correlation"]
    assert correlation["test"] == ("federated_two_operator_route_transfers_only_after_f75_admission")
    assert correlation["result"] == "passed"
    assert correlation["test"] in correlation["command"]
    assert datetime.fromisoformat(correlation["capture_started_utc"]) < datetime.fromisoformat(correlation["capture_stopped_utc"])
    forbidden = [
        b"PRIVATE KEY",
        b"subscriber",
        b"origin.internal",
        b"NBSR-WP8-TASK10-LIVE-v1",
    ]
    assert all(value not in wire for value in forbidden)
    packets = _enhanced_packets(wire)
    assert manifest["packet_count"] == len(packets)
    flows = [_exact_loopback_udp(link_type, packet) for link_type, packet in packets]
    assert any(destination == CAPTURE_PORT for _, destination, _ in flows)
    assert any(source == CAPTURE_PORT for source, _, _ in flows)
    assert any(payload[0] & 0x80 == 0 for _, _, payload in flows), (
        "capture must include protected QUIC short-header traffic after the Initial exchange"
    )


def test_task10b_independent_capture_is_closed_and_public_safe() -> None:
    evidence = ROOT / "evidence" / "wp8-task10b"
    capture = evidence / "independent-go-rust.pcapng"
    manifest = json.loads((evidence / "capture-manifest.json").read_text(encoding="utf-8"))
    wire = capture.read_bytes()
    port = 45976
    assert manifest["capture"] == capture.name
    assert manifest["interface_identifier"] == CAPTURE_INTERFACE
    assert manifest["filter"] == f"udp port {port} and host 127.0.0.1"
    assert manifest["flow"] == f"127.0.0.1 UDP/{port} QUIC/TLS nbsr-quic-1 Go-source to Rust-destination"
    assert manifest["dropped_count"] == 0
    assert manifest["length"] == len(wire)
    assert manifest["sha256"] == hashlib.sha256(wire).hexdigest()
    assert manifest["test_correlation"]["result"] == "passed"
    assert "test_independent_wire_peer.py" in manifest["test_correlation"]["command"]
    assert all(
        marker not in wire
        for marker in (
            b"PRIVATE KEY",
            b"subscriber",
            b"origin.internal",
            b"NBSR-WP8-TASK10B-INDEPENDENT-WIRE",
        )
    )
    packets = _enhanced_packets(wire)
    assert manifest["packet_count"] == len(packets)
    flows = [_exact_loopback_udp(link_type, packet, port) for link_type, packet in packets]
    assert any(destination == port for _, destination, _ in flows)
    assert any(source == port for source, _, _ in flows)
    assert any(payload[0] & 0x80 == 0 for _, _, payload in flows)
