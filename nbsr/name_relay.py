from __future__ import annotations

import asyncio
import heapq
import json
import socket
import struct
from dataclasses import dataclass
from time import monotonic
from typing import Protocol

from nbsr.config import Settings
from nbsr.destination_policy import DestinationDenied, DestinationPolicy
from nbsr.name_security import verify_name_binding, verify_relay_proof
from nbsr.security import SecurityError


_ALLOWED_PORTS = frozenset((80, 443))
_HANDSHAKE_FIELDS = frozenset(("hostname", "synthetic_address", "port", "gateway_id", "binding", "route_id", "nonce", "proof"))
_MAX_HANDSHAKE_BYTES = 64 * 1024
_ADMISSION_ACCEPTED = b"\x01"
_ADMISSION_REJECTED = b"\x00"


class RelayRejected(Exception):
    """The relay rejected a connection before it reached an origin."""


@dataclass(frozen=True)
class ResolvedEndpoint:
    host: str
    port: int


class Resolver(Protocol):
    async def resolve(self, hostname: str, port: int) -> list[ResolvedEndpoint]: ...


class PrivateResolver:
    def __init__(self, max_endpoints: int = 8):
        self._max_endpoints = max_endpoints

    async def resolve(self, hostname: str, port: int) -> list[ResolvedEndpoint]:
        results = await asyncio.get_running_loop().getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        endpoints: list[ResolvedEndpoint] = []
        seen: set[tuple[str, int]] = set()
        for _, _, _, _, sockaddr in results:
            endpoint = ResolvedEndpoint(sockaddr[0], sockaddr[1])
            identity = (endpoint.host, endpoint.port)
            if identity not in seen:
                seen.add(identity)
                endpoints.append(endpoint)
            if len(endpoints) == self._max_endpoints:
                break
        return endpoints


class ReplayCache:
    def __init__(self, ttl_seconds: int = 60, max_entries: int = 10_000):
        if ttl_seconds <= 0 or max_entries <= 0:
            raise ValueError("Replay cache limits must be positive")
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._consumed: dict[tuple[str, str], float] = {}
        self._expirations: list[tuple[float, tuple[str, str]]] = []

    def consume(self, route_id: str, nonce: str) -> None:
        now = monotonic()
        self._expire(now)
        key = (route_id, nonce)
        if key in self._consumed:
            raise RelayRejected("relay proof has already been used")
        if len(self._consumed) >= self._max_entries:
            raise RelayRejected("relay replay cache is at capacity")
        expires_at = now + self._ttl_seconds
        self._consumed[key] = expires_at
        heapq.heappush(self._expirations, (expires_at, key))

    def _expire(self, now: float) -> None:
        while self._expirations and self._expirations[0][0] <= now:
            expires_at, key = heapq.heappop(self._expirations)
            if self._consumed.get(key) == expires_at:
                del self._consumed[key]


class NameRelay:
    def __init__(
        self,
        *,
        settings: Settings,
        resolver: Resolver | None = None,
        replay_cache: ReplayCache | None = None,
        destination_policy: DestinationPolicy | None = None,
    ):
        self._settings = settings
        self._resolver = resolver or PrivateResolver(settings.name_relay_max_endpoints)
        self._replay_cache = replay_cache or ReplayCache(
            max(1, settings.name_binding_ttl_seconds),
            settings.name_relay_replay_cache_max_entries,
        )
        self._destination_policy = destination_policy or DestinationPolicy.from_config(settings.name_relay_trusted_origins)

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        origin_writer: asyncio.StreamWriter | None = None
        admitted = False
        try:
            handshake = await asyncio.wait_for(
                self._read_handshake(reader),
                timeout=self._settings.name_relay_handshake_timeout_seconds,
            )
            self._verify_admission(handshake)
            origin_reader, origin_writer = await self._connect_origin(handshake["hostname"], handshake["port"])
            writer.write(_ADMISSION_ACCEPTED)
            await writer.drain()
            admitted = True
            await asyncio.gather(self._copy(reader, origin_writer), self._copy(origin_reader, writer))
        except (
            RelayRejected,
            SecurityError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            struct.error,
            asyncio.IncompleteReadError,
            TimeoutError,
        ):
            if not admitted:
                try:
                    writer.write(_ADMISSION_REJECTED)
                    await writer.drain()
                except (ConnectionError, RuntimeError):
                    pass
        finally:
            if origin_writer is not None:
                origin_writer.close()
                await origin_writer.wait_closed()
            writer.close()
            await writer.wait_closed()

    async def _read_handshake(self, reader: asyncio.StreamReader) -> dict[str, object]:
        declared_length = struct.unpack(">I", await reader.readexactly(4))[0]
        if declared_length > _MAX_HANDSHAKE_BYTES:
            raise RelayRejected("handshake is too large")
        try:
            handshake = json.loads((await reader.readexactly(declared_length)).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RelayRejected("handshake is not valid JSON") from exc
        if not isinstance(handshake, dict) or set(handshake) != _HANDSHAKE_FIELDS:
            raise RelayRejected("handshake fields are invalid")
        string_fields = _HANDSHAKE_FIELDS - {"port"}
        if any(not isinstance(handshake[field], str) or not handshake[field] for field in string_fields):
            raise RelayRejected("handshake fields are invalid")
        if type(handshake["port"]) is not int or handshake["port"] not in _ALLOWED_PORTS:
            raise RelayRejected("relay port is not allowed")
        return handshake

    def _verify_admission(self, handshake: dict[str, object]) -> None:
        claims = verify_name_binding(
            handshake["binding"],
            handshake["hostname"],
            handshake["synthetic_address"],
            handshake["port"],
            handshake["gateway_id"],
            self._settings,
        )
        verify_relay_proof(
            claims,
            handshake["route_id"],
            handshake["nonce"],
            handshake["port"],
            handshake["proof"],
        )
        self._replay_cache.consume(handshake["route_id"], handshake["nonce"])

    async def _connect_origin(self, hostname: object, port: object) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        try:
            endpoints = await self._resolver.resolve(hostname, port)
        except OSError as exc:
            raise RelayRejected("gateway could not resolve the named origin") from exc
        for endpoint in endpoints[: self._settings.name_relay_max_endpoints]:
            try:
                destination = self._destination_policy.validate(hostname, endpoint.host)
            except DestinationDenied:
                continue
            try:
                return await asyncio.wait_for(
                    asyncio.open_connection(destination, endpoint.port),
                    timeout=self._settings.name_relay_connect_timeout_seconds,
                )
            except (OSError, TimeoutError):
                continue
        raise RelayRejected("gateway destination policy denied or could not connect to the named origin")

    async def _copy(self, source: asyncio.StreamReader, destination: asyncio.StreamWriter) -> None:
        while data := await source.read(65536):
            destination.write(data)
            await destination.drain()
        try:
            destination.write_eof()
            await destination.drain()
        except (AttributeError, OSError, RuntimeError):
            destination.close()
