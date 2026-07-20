import asyncio
import json
import socket
import struct
from dataclasses import dataclass
from uuid import uuid4

import pytest
import jwt

from nbsr.config import Settings
from nbsr.name_relay import NameRelay, RelayRejected, ResolvedEndpoint
from nbsr.name_security import ClientSession, issue_name_binding, sign_relay_proof


@dataclass
class Listener:
    server: asyncio.AbstractServer
    host: str
    port: int

    async def close(self) -> None:
        self.server.close()
        await self.server.wait_closed()


@dataclass(frozen=True)
class BindingCredentials:
    binding: str
    session: ClientSession
    route_id: str


class StaticResolver:
    def __init__(self, mapping: dict[str, list[tuple[str, int]]]):
        self._mapping = mapping
        self.lookups: list[tuple[str, int]] = []

    async def resolve(self, hostname: str, port: int) -> list[ResolvedEndpoint]:
        self.lookups.append((hostname, port))
        return [ResolvedEndpoint(host, endpoint_port) for host, endpoint_port in self._mapping[hostname]]


class UnresolvableResolver:
    async def resolve(self, hostname: str, port: int) -> list[ResolvedEndpoint]:
        raise socket.gaierror(socket.EAI_NONAME, "name not known")


@pytest.fixture()
def settings():
    return Settings.for_tests(
        ClientSession.generate().private_key,
        ClientSession.generate().private_key,
        ClientSession.generate().private_key,
    )


async def start_echo_origin(prefix: bytes) -> Listener:
    async def echo(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while data := await reader.read(65536):
                writer.write(prefix + data)
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(echo, "127.0.0.1", 0)
    host, port = server.sockets[0].getsockname()[:2]
    return Listener(server, host, port)


async def start_name_relay(settings: Settings, resolver: StaticResolver | UnresolvableResolver | None = None) -> Listener:
    relay = NameRelay(settings=settings, resolver=resolver)
    server = await asyncio.start_server(relay.handle, "127.0.0.1", 0)
    host, port = server.sockets[0].getsockname()[:2]
    return Listener(server, host, port)


def valid_handshake(
    settings: Settings,
    *,
    hostname: str = "facebook.test",
    port: int = 443,
    nonce: str | None = None,
    extra: dict[str, object] | None = None,
    credentials: BindingCredentials | None = None,
) -> bytes:
    credentials = credentials or issue_binding_credentials(settings, hostname, port)
    nonce = nonce or str(uuid4())
    handshake: dict[str, object] = {
        "hostname": hostname,
        "synthetic_address": "127.80.0.1",
        "port": port,
        "gateway_id": settings.name_binding_gateway_id,
        "binding": credentials.binding,
        "route_id": credentials.route_id,
        "nonce": nonce,
        "proof": sign_relay_proof(credentials.session, credentials.route_id, nonce, port),
    }
    if extra:
        handshake.update(extra)
    encoded = json.dumps(handshake, separators=(",", ":")).encode("utf-8")
    return struct.pack(">I", len(encoded)) + encoded


def issue_binding_credentials(settings: Settings, hostname: str, port: int) -> BindingCredentials:
    session = ClientSession.generate()
    binding = issue_name_binding(
        hostname=hostname,
        synthetic_ipv4="127.80.0.1",
        synthetic_ipv6="fd00:6e62:7372::1",
        gateway_id=settings.name_binding_gateway_id,
        session_public_key=session.public_key_b64,
        settings=settings,
    )
    claims = jwt.decode(binding, options={"verify_signature": False})
    return BindingCredentials(binding=binding, session=session, route_id=claims["jti"])


async def open_with_valid_binding(
    relay: Listener,
    settings: Settings,
    *,
    hostname: str = "facebook.test",
    port: int = 443,
    nonce: str | None = None,
    extra: dict[str, object] | None = None,
    credentials: BindingCredentials | None = None,
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    reader, writer = await asyncio.open_connection(relay.host, relay.port)
    writer.write(valid_handshake(settings, hostname=hostname, port=port, nonce=nonce, extra=extra, credentials=credentials))
    await writer.drain()
    return reader, writer


async def connect_with_valid_binding(
    relay: Listener,
    settings: Settings,
    *,
    hostname: str = "facebook.test",
    payload: bytes = b"opaque",
    nonce: str | None = None,
    credentials: BindingCredentials | None = None,
) -> bytes:
    reader, writer = await open_with_valid_binding(relay, settings, hostname=hostname, nonce=nonce, credentials=credentials)
    try:
        writer.write(payload)
        await writer.drain()
        response = await reader.read(len(payload) + len(b"origin:"))
        if not response:
            raise RelayRejected("relay rejected admission")
        return response
    finally:
        writer.close()
        await writer.wait_closed()


def unused_loopback_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
    finally:
        sock.close()


@pytest.mark.asyncio
async def test_relay_resolves_only_at_gateway_and_copies_opaque_bytes(settings):
    origin = await start_echo_origin(prefix=b"origin:")
    resolver = StaticResolver({"facebook.test": [("127.0.0.1", origin.port)]})
    relay = await start_name_relay(settings, resolver)
    try:
        response = await connect_with_valid_binding(relay, settings, hostname="facebook.test", payload=b"opaque-tls-record")
    finally:
        await relay.close()
        await origin.close()

    assert response == b"origin:opaque-tls-record"
    assert resolver.lookups == [("facebook.test", 443)]


@pytest.mark.asyncio
async def test_replay_nonce_is_rejected(settings):
    origin = await start_echo_origin(prefix=b"origin:")
    resolver = StaticResolver({"facebook.test": [("127.0.0.1", origin.port)]})
    relay = await start_name_relay(settings, resolver)
    credentials = issue_binding_credentials(settings, "facebook.test", 443)
    try:
        await connect_with_valid_binding(relay, settings, nonce="same-nonce", credentials=credentials)
        with pytest.raises(RelayRejected):
            await connect_with_valid_binding(relay, settings, nonce="same-nonce", credentials=credentials)
    finally:
        await relay.close()
        await origin.close()


@pytest.mark.asyncio
async def test_expired_binding_rejects_new_admission(settings):
    settings.name_binding_ttl_seconds = -1
    origin = await start_echo_origin(prefix=b"origin:")
    resolver = StaticResolver({"facebook.test": [("127.0.0.1", origin.port)]})
    relay = await start_name_relay(settings, resolver)
    try:
        with pytest.raises(RelayRejected):
            await connect_with_valid_binding(relay, settings)
    finally:
        await relay.close()
        await origin.close()


@pytest.mark.asyncio
async def test_admitted_connection_continues_after_binding_expiry(settings):
    settings.name_binding_ttl_seconds = 2
    origin = await start_echo_origin(prefix=b"origin:")
    resolver = StaticResolver({"facebook.test": [("127.0.0.1", origin.port)]})
    relay = await start_name_relay(settings, resolver)
    reader, writer = await open_with_valid_binding(relay, settings)
    try:
        await asyncio.sleep(2.1)
        writer.write(b"after-expiry")
        await writer.drain()
        assert await reader.readexactly(len(b"origin:after-expiry")) == b"origin:after-expiry"
    finally:
        writer.close()
        await writer.wait_closed()
        await relay.close()
        await origin.close()


@pytest.mark.asyncio
async def test_relay_rejects_unknown_handshake_fields_and_unapproved_ports(settings):
    origin = await start_echo_origin(prefix=b"origin:")
    resolver = StaticResolver({"facebook.test": [("127.0.0.1", origin.port)]})
    relay = await start_name_relay(settings, resolver)
    try:
        reader, writer = await open_with_valid_binding(relay, settings, extra={"unexpected": True})
        try:
            assert await reader.read() == b""
        finally:
            writer.close()
            await writer.wait_closed()

        frame = valid_handshake(settings, port=80)
        handshake = json.loads(frame[4:])
        handshake["port"] = 22
        encoded = json.dumps(handshake, separators=(",", ":")).encode("utf-8")
        reader, writer = await asyncio.open_connection(relay.host, relay.port)
        try:
            writer.write(struct.pack(">I", len(encoded)) + encoded)
            await writer.drain()
            assert await reader.read() == b""
        finally:
            writer.close()
            await writer.wait_closed()
    finally:
        await relay.close()
        await origin.close()


@pytest.mark.asyncio
async def test_relay_rejects_oversized_handshake(settings):
    resolver = StaticResolver({"facebook.test": []})
    relay = await start_name_relay(settings, resolver)
    reader, writer = await asyncio.open_connection(relay.host, relay.port)
    try:
        writer.write(struct.pack(">I", 65537))
        await writer.drain()
        assert await reader.read() == b""
    finally:
        writer.close()
        await writer.wait_closed()
        await relay.close()


@pytest.mark.asyncio
async def test_unresolvable_signed_hostname_closes_without_asyncio_callback_error(settings):
    relay = await start_name_relay(settings, UnresolvableResolver())
    loop = asyncio.get_running_loop()
    errors: list[dict[str, object]] = []
    previous_exception_handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: errors.append(context))
    try:
        reader, writer = await open_with_valid_binding(relay, settings)
        try:
            assert await asyncio.wait_for(reader.read(), timeout=1) == b""
        finally:
            writer.close()
            await writer.wait_closed()
    finally:
        loop.set_exception_handler(previous_exception_handler)
        await relay.close()

    assert errors == []


@pytest.mark.asyncio
async def test_relay_uses_the_first_resolved_endpoint_in_order(settings):
    first_origin = await start_echo_origin(prefix=b"first:")
    later_origin = await start_echo_origin(prefix=b"later:")
    resolver = StaticResolver({"facebook.test": [("127.0.0.1", first_origin.port), ("127.0.0.1", later_origin.port)]})
    relay = await start_name_relay(settings, resolver)
    try:
        assert await connect_with_valid_binding(relay, settings, payload=b"ordered") == b"first:ordered"
    finally:
        await relay.close()
        await later_origin.close()
        await first_origin.close()


@pytest.mark.asyncio
async def test_relay_falls_back_in_endpoint_order_after_failed_connection(settings):
    origin = await start_echo_origin(prefix=b"origin:")
    resolver = StaticResolver({"facebook.test": [("127.0.0.1", unused_loopback_port()), ("127.0.0.1", origin.port)]})
    relay = await start_name_relay(settings, resolver)
    try:
        assert await connect_with_valid_binding(relay, settings, payload=b"fallback") == b"origin:fallback"
    finally:
        await relay.close()
        await origin.close()


@pytest.mark.asyncio
async def test_relay_endpoint_cap_excludes_later_origins(settings):
    settings.name_relay_max_endpoints = 1
    origin = await start_echo_origin(prefix=b"origin:")
    resolver = StaticResolver({"facebook.test": [("127.0.0.1", unused_loopback_port()), ("127.0.0.1", origin.port)]})
    relay = await start_name_relay(settings, resolver)
    try:
        with pytest.raises(RelayRejected):
            await connect_with_valid_binding(relay, settings, payload=b"must-not-reach-origin")
    finally:
        await relay.close()
        await origin.close()
