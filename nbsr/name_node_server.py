"""Bounded loopback-only UDP/TCP DNS service for WP2A lab use."""

from __future__ import annotations

import socketserver
import struct
from ipaddress import ip_address
from threading import BoundedSemaphore, RLock, Thread
from typing import Any

from nbsr.dns_stub import DnsStub


_MAX_DNS_FRAME_BYTES = 4_096
_MAX_CONCURRENT_REQUESTS = 32
_MAX_REQUEST_TIMEOUT_SECONDS = 2.0


class _BoundedThreadingMixIn(socketserver.ThreadingMixIn):
    daemon_threads = True
    block_on_close = True
    _request_slots: BoundedSemaphore

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self._request_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._request_slots.release()
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._request_slots.release()


class _ThreadingUdpServer(_BoundedThreadingMixIn, socketserver.UDPServer):
    allow_reuse_address = True


class _ThreadingTcpServer(_BoundedThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True


class _UdpHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        packet, response_socket = self.request
        owner: NameNodeLabServer = self.server.owner
        if not packet or len(packet) > owner.max_frame_size:
            return
        response = owner.resolve_query(packet)
        if len(response) <= owner.max_frame_size:
            response_socket.sendto(response, self.client_address)


class _TcpHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        owner: NameNodeLabServer = self.server.owner
        self.request.settimeout(owner.request_timeout_seconds)
        prefix = self._receive_exact(2)
        if prefix is None:
            return
        length = struct.unpack(">H", prefix)[0]
        if not 1 <= length <= owner.max_frame_size:
            return
        packet = self._receive_exact(length)
        if packet is None:
            return
        response = owner.resolve_query(packet)
        if len(response) > owner.max_frame_size:
            return
        self.request.sendall(struct.pack(">H", len(response)) + response)

    def _receive_exact(self, length: int) -> bytes | None:
        chunks: list[bytes] = []
        remaining = length
        try:
            while remaining:
                chunk = self.request.recv(remaining)
                if not chunk:
                    return None
                chunks.append(chunk)
                remaining -= len(chunk)
        except (ConnectionError, OSError, TimeoutError):
            return None
        return b"".join(chunks)


class NameNodeLabServer:
    """Serve one bounded DNS request per loopback UDP datagram/TCP connection."""

    def __init__(
        self,
        dns_stub: DnsStub,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        max_frame_size: int = _MAX_DNS_FRAME_BYTES,
        request_timeout_seconds: float = _MAX_REQUEST_TIMEOUT_SECONDS,
        max_concurrent_requests: int = _MAX_CONCURRENT_REQUESTS,
    ) -> None:
        if not callable(getattr(dns_stub, "resolve_query", None)):
            raise TypeError("dns_stub must provide resolve_query")
        try:
            bind_address = ip_address(host)
        except ValueError as exc:
            raise ValueError("Name Node lab server requires an IP loopback address") from exc
        if not bind_address.is_loopback:
            raise ValueError("Name Node lab server requires a loopback address")
        if type(port) is not int or not 0 <= port <= 65_535:
            raise ValueError("port is outside its allowed bound")
        if type(max_frame_size) is not int or not 1 <= max_frame_size <= _MAX_DNS_FRAME_BYTES:
            raise ValueError("max_frame_size is outside its allowed bound")
        if type(request_timeout_seconds) not in (int, float) or not 0 < request_timeout_seconds <= _MAX_REQUEST_TIMEOUT_SECONDS:
            raise ValueError("request_timeout_seconds is outside its allowed bound")
        if type(max_concurrent_requests) is not int or not 1 <= max_concurrent_requests <= _MAX_CONCURRENT_REQUESTS:
            raise ValueError("max_concurrent_requests is outside its allowed bound")
        if bind_address.version != 4:
            raise ValueError("WP2A lab server currently requires an IPv4 loopback address")

        self._dns_stub = dns_stub
        self._host = str(bind_address)
        self._port = port
        self.max_frame_size = max_frame_size
        self.request_timeout_seconds = float(request_timeout_seconds)
        self._max_concurrent_requests = max_concurrent_requests
        self._udp_server: _ThreadingUdpServer | None = None
        self._tcp_server: _ThreadingTcpServer | None = None
        self._threads: tuple[Thread, ...] = ()
        self._closed = False
        self._lock = RLock()

    def start(self) -> None:
        with self._lock:
            if self._udp_server is not None:
                return
            if self._closed:
                raise RuntimeError("Name Node lab server is closed")
            slots = BoundedSemaphore(self._max_concurrent_requests)
            udp_server = _ThreadingUdpServer((self._host, self._port), _UdpHandler)
            udp_server._request_slots = slots
            udp_server.owner = self
            try:
                tcp_server = _ThreadingTcpServer((self._host, self._port), _TcpHandler)
            except Exception:
                udp_server.server_close()
                raise
            tcp_server._request_slots = slots
            tcp_server.owner = self

            threads = (
                Thread(
                    target=udp_server.serve_forever,
                    name="nbsr-name-node-udp",
                    daemon=True,
                ),
                Thread(
                    target=tcp_server.serve_forever,
                    name="nbsr-name-node-tcp",
                    daemon=True,
                ),
            )
            self._udp_server = udp_server
            self._tcp_server = tcp_server
            self._threads = threads
            for thread in threads:
                thread.start()

    def close(self) -> None:
        with self._lock:
            servers = tuple(server for server in (self._udp_server, self._tcp_server) if server is not None)
            threads = self._threads
            self._udp_server = None
            self._tcp_server = None
            self._threads = ()
            self._closed = True
        for server in servers:
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=_MAX_REQUEST_TIMEOUT_SECONDS + 1)

    @property
    def udp_address(self) -> tuple[str, int]:
        with self._lock:
            if self._udp_server is None:
                raise RuntimeError("Name Node lab server is not running")
            return self._udp_server.server_address

    @property
    def tcp_address(self) -> tuple[str, int]:
        with self._lock:
            if self._tcp_server is None:
                raise RuntimeError("Name Node lab server is not running")
            return self._tcp_server.server_address

    def resolve_query(self, packet: bytes) -> bytes:
        return self._dns_stub.resolve_query(packet)
