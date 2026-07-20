from __future__ import annotations

import asyncio

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nbsr.config import Settings
from nbsr.dns_stub import ClientRoute, RouteTable
from nbsr.name_relay import NameRelay, ResolvedEndpoint
from nbsr.name_security import ClientSession
from nbsr.name_service import NameRouteService
from nbsr.synthetic import SyntheticAddressPool
from nbsr.windows_agent import (
    CommandResult,
    LoopbackInterceptor,
    OptInWindowsNetworkAdapter,
    RecordingWindowsNetworkAdapter,
    WindowsNameAgent,
)


class StaticResolver:
    def __init__(self, origin_port: int):
        self._origin_port = origin_port

    async def resolve(self, hostname: str, port: int) -> list[ResolvedEndpoint]:
        assert (hostname, port) == ("facebook.test", 443)
        return [ResolvedEndpoint("127.0.0.1", self._origin_port)]


class FakeCommandRunner:
    def __init__(self, results: list[CommandResult]):
        self._results = results
        self.calls: list[tuple[str, ...]] = []

    def run(self, arguments: tuple[str, ...]) -> CommandResult:
        self.calls.append(arguments)
        return self._results.pop(0)


@pytest.fixture()
def settings() -> Settings:
    return Settings.for_tests(Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate())


async def start_echo_origin() -> tuple[asyncio.AbstractServer, int]:
    async def echo(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while payload := await reader.read(65536):
                writer.write(b"origin:" + payload)
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(echo, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


async def send_to_synthetic(host: str, port: int, payload: bytes) -> bytes:
    reader, writer = await asyncio.open_connection(host, port)
    try:
        writer.write(payload)
        await writer.drain()
        return await reader.readexactly(len(b"origin:") + len(payload))
    finally:
        writer.close()
        await writer.wait_closed()


@pytest.mark.asyncio
async def test_loopback_interceptor_uses_route_binding():
    origin, origin_port = await start_echo_origin()
    settings = Settings.for_tests(Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate())
    relay = NameRelay(settings=settings, resolver=StaticResolver(origin_port))
    relay_server = await asyncio.start_server(relay.handle, "127.0.0.1", 0)
    service = NameRouteService(pool=SyntheticAddressPool("127.80.0.0/29", "fd00:6e62:7372::/125", ttl_seconds=60), settings=settings)
    agent = WindowsNameAgent(
        name_route_service=service,
        client_session=ClientSession.generate(),
        relay_host="127.0.0.1",
        relay_port=relay_server.sockets[0].getsockname()[1],
        gateway_id=settings.name_binding_gateway_id,
        test_https_port=443,
    )
    try:
        route = await agent.resolve("facebook.test")

        response = await send_to_synthetic(route.synthetic_ipv4, agent.test_https_port, b"opaque")

        assert response == b"origin:opaque"
        assert agent.route_table.lookup(route.synthetic_ipv4).hostname == "facebook.test"
        assert agent.ipv6_interception_available is False
        assert "unavailable" in agent.ipv6_interception_status
    finally:
        await agent.close()
        relay_server.close()
        await relay_server.wait_closed()
        origin.close()
        await origin.wait_closed()


@pytest.mark.asyncio
async def test_loopback_interceptor_uses_a_fresh_nonce_per_connection():
    origin, origin_port = await start_echo_origin()
    settings = Settings.for_tests(Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate())
    relay = NameRelay(settings=settings, resolver=StaticResolver(origin_port))
    relay_server = await asyncio.start_server(relay.handle, "127.0.0.1", 0)
    service = NameRouteService(pool=SyntheticAddressPool("127.80.0.0/29", "fd00:6e62:7372::/125", ttl_seconds=60), settings=settings)
    agent = WindowsNameAgent(
        name_route_service=service,
        client_session=ClientSession.generate(),
        relay_host="127.0.0.1",
        relay_port=relay_server.sockets[0].getsockname()[1],
        gateway_id=settings.name_binding_gateway_id,
        test_https_port=443,
    )
    try:
        route = await agent.resolve("facebook.test")

        assert await send_to_synthetic(route.synthetic_ipv4, 443, b"one") == b"origin:one"
        assert await send_to_synthetic(route.synthetic_ipv4, 443, b"two") == b"origin:two"
    finally:
        await agent.close()
        relay_server.close()
        await relay_server.wait_closed()
        origin.close()
        await origin.wait_closed()


@pytest.mark.asyncio
async def test_agent_restores_only_recorded_windows_state_on_close(settings: Settings):
    service = NameRouteService(pool=SyntheticAddressPool("127.80.0.0/29", "fd00:6e62:7372::/125", ttl_seconds=60), settings=settings)
    adapter = RecordingWindowsNetworkAdapter()
    agent = WindowsNameAgent(
        name_route_service=service,
        client_session=ClientSession.generate(),
        relay_host="127.0.0.1",
        relay_port=443,
        gateway_id=settings.name_binding_gateway_id,
        network_adapter=adapter,
    )
    agent.configure_dns_stub("127.0.0.1", 53)

    await agent.close()

    assert adapter.owned_dns_stub is None


def test_opt_in_adapter_assigns_and_removes_only_its_own_synthetic_ipv6_address():
    address = "fd00:6e62:7372::1"
    runner = FakeCommandRunner([CommandResult(0), CommandResult(0), CommandResult(0)])
    adapter = OptInWindowsNetworkAdapter(interface_alias="NBSR Loopback", command_runner=runner, enable_synthetic_ipv6=True)

    assert adapter.ensure_synthetic_ipv6(address) is True
    adapter.restore_owned_state()

    assert runner.calls == [
        ("netsh", "interface", "ipv6", "show", "addresses", "interface=NBSR Loopback"),
        ("netsh", "interface", "ipv6", "add", "address", "interface=NBSR Loopback", address, "store=active"),
        ("netsh", "interface", "ipv6", "delete", "address", "interface=NBSR Loopback", address),
    ]


def test_opt_in_adapter_never_removes_an_existing_or_unavailable_address():
    address = "fd00:6e62:7372::1"
    existing = FakeCommandRunner([CommandResult(0, f"address {address}")])
    adapter = OptInWindowsNetworkAdapter(interface_alias="NBSR Loopback", command_runner=existing, enable_synthetic_ipv6=True)

    assert adapter.ensure_synthetic_ipv6(address) is True
    adapter.restore_owned_state()
    assert existing.calls == [("netsh", "interface", "ipv6", "show", "addresses", "interface=NBSR Loopback")]

    unavailable = FakeCommandRunner([])
    disabled = OptInWindowsNetworkAdapter(interface_alias="NBSR Loopback", command_runner=unavailable)
    assert disabled.ensure_synthetic_ipv6(address) is False
    assert unavailable.calls == []


def test_opt_in_adapter_does_not_confuse_a_prefix_collision_with_the_owned_address():
    address = "fd00:6e62:7372::1"
    runner = FakeCommandRunner([CommandResult(0, "address fd00:6e62:7372::10"), CommandResult(0)])
    adapter = OptInWindowsNetworkAdapter(interface_alias="NBSR Loopback", command_runner=runner, enable_synthetic_ipv6=True)

    assert adapter.ensure_synthetic_ipv6(address) is True

    assert runner.calls == [
        ("netsh", "interface", "ipv6", "show", "addresses", "interface=NBSR Loopback"),
        ("netsh", "interface", "ipv6", "add", "address", "interface=NBSR Loopback", address, "store=active"),
    ]


@pytest.mark.asyncio
async def test_interceptor_rejects_non_loopback_or_unapproved_listener_ports():
    interceptor = LoopbackInterceptor(
        route_table=RouteTable(),
        client_session=ClientSession.generate(),
        relay_host="127.0.0.1",
        relay_port=443,
        gateway_id="edge-local",
    )
    route = ClientRoute(
        hostname="facebook.test",
        synthetic_ipv4="192.0.2.1",
        synthetic_ipv6="fd00:6e62:7372::1",
        route_binding="binding",
        expires_in=30,
    )

    with pytest.raises(ValueError, match="loopback"):
        await interceptor.start(route, 443)


@pytest.mark.asyncio
async def test_interceptor_requires_a_pre_registered_synthetic_route():
    interceptor = LoopbackInterceptor(
        route_table=RouteTable(),
        client_session=ClientSession.generate(),
        relay_host="127.0.0.1",
        relay_port=443,
        gateway_id="edge-local",
    )
    route = ClientRoute("facebook.test", "127.80.0.1", "fd00:6e62:7372::1", "binding", 30)

    with pytest.raises(ValueError, match="configured"):
        await interceptor.start(route, 443)


@pytest.mark.asyncio
async def test_agent_restores_owned_state_even_when_listener_cleanup_fails(settings: Settings):
    service = NameRouteService(pool=SyntheticAddressPool("127.80.0.0/29", "fd00:6e62:7372::/125", ttl_seconds=60), settings=settings)
    adapter = RecordingWindowsNetworkAdapter()
    agent = WindowsNameAgent(
        name_route_service=service,
        client_session=ClientSession.generate(),
        relay_host="127.0.0.1",
        relay_port=443,
        gateway_id=settings.name_binding_gateway_id,
        network_adapter=adapter,
    )

    class FailingInterceptor:
        async def close(self) -> None:
            raise RuntimeError("listener close failed")

    agent.configure_dns_stub("127.0.0.1", 53)
    agent.interceptor = FailingInterceptor()

    with pytest.raises(RuntimeError, match="listener close failed"):
        await agent.close()

    assert adapter.owned_dns_stub is None
