from __future__ import annotations

import socket
import struct

import pytest
from dnslib import DNSRecord, RCODE

from nbsr.dns_stub import ClientRoute, DnsStub, RouteTable
from nbsr.name_node_server import NameNodeLabServer


def route_for(hostname: str) -> ClientRoute:
    assert hostname == "api.example"
    return ClientRoute(
        hostname=hostname,
        synthetic_ipv4="127.80.0.1",
        synthetic_ipv6="fd00:6e62:7372::1",
        route_binding="route-id",
        expires_in=30,
    )


def dns_stub() -> DnsStub:
    return DnsStub(route_for, RouteTable())


def query_udp(address: tuple[str, int], packet: bytes, *, timeout: float = 1) -> bytes:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        client.settimeout(timeout)
        client.sendto(packet, address)
        return client.recvfrom(4096)[0]


def query_tcp(address: tuple[str, int], packet: bytes, *, timeout: float = 1) -> bytes:
    with socket.create_connection(address, timeout=timeout) as client:
        client.settimeout(timeout)
        client.sendall(struct.pack(">H", len(packet)) + packet)
        length = struct.unpack(">H", recv_exact(client, 2))[0]
        return recv_exact(client, length)


def recv_exact(client: socket.socket, length: int) -> bytes:
    chunks: list[bytes] = []
    remaining = length
    while remaining:
        chunk = client.recv(remaining)
        if not chunk:
            raise EOFError("connection closed before framed response completed")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def test_udp_and_tcp_return_equivalent_synthetic_answers() -> None:
    server = NameNodeLabServer(dns_stub())
    server.start()
    try:
        request = DNSRecord.question("api.example", "A").pack()
        udp = query_udp(server.udp_address, request)
        tcp = query_tcp(server.tcp_address, request)
    finally:
        server.close()

    udp_answer = DNSRecord.parse(udp)
    tcp_answer = DNSRecord.parse(tcp)
    assert str(udp_answer.rr) == str(tcp_answer.rr)
    assert str(udp_answer.rr[0].rdata).startswith("127.")
    assert udp_answer.header.rcode == RCODE.NOERROR


@pytest.mark.parametrize(
    "invalid_frame",
    (
        struct.pack(">H", 4_097),
        struct.pack(">H", 20) + b"truncated",
    ),
)
def test_tcp_rejects_oversized_or_truncated_frames_and_remains_available(invalid_frame: bytes) -> None:
    server = NameNodeLabServer(
        dns_stub(),
        request_timeout_seconds=0.05,
    )
    server.start()
    try:
        with socket.create_connection(server.tcp_address, timeout=1) as client:
            client.settimeout(1)
            client.sendall(invalid_frame)
            assert client.recv(1) == b""

        answer = DNSRecord.parse(
            query_tcp(
                server.tcp_address,
                DNSRecord.question("api.example", "A").pack(),
            )
        )
        assert answer.header.rcode == RCODE.NOERROR
    finally:
        server.close()


def test_udp_oversized_packet_is_dropped() -> None:
    server = NameNodeLabServer(dns_stub(), request_timeout_seconds=0.05)
    server.start()
    try:
        with pytest.raises(TimeoutError):
            query_udp(server.udp_address, b"x" * 4_097, timeout=0.1)
    finally:
        server.close()


def test_worker_capacity_rejects_extra_request_without_unbounded_queueing() -> None:
    server = NameNodeLabServer(
        dns_stub(),
        max_concurrent_requests=1,
        request_timeout_seconds=0.2,
    )
    server.start()
    blocker = socket.create_connection(server.tcp_address, timeout=1)
    try:
        blocker.sendall(struct.pack(">H", 100) + b"{")
        with pytest.raises(TimeoutError):
            query_udp(
                server.udp_address,
                DNSRecord.question("api.example", "A").pack(),
                timeout=0.1,
            )
    finally:
        blocker.close()
        server.close()


def test_non_loopback_bind_is_rejected_before_listener_creation() -> None:
    with pytest.raises(ValueError, match="loopback"):
        NameNodeLabServer(dns_stub(), host="0.0.0.0")


def test_start_and_close_are_idempotent_without_a_tunnel_process() -> None:
    server = NameNodeLabServer(dns_stub())

    server.start()
    first_udp = server.udp_address
    first_tcp = server.tcp_address
    server.start()

    assert server.udp_address == first_udp
    assert server.tcp_address == first_tcp

    server.close()
    server.close()
