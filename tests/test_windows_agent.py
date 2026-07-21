from __future__ import annotations

import asyncio
import json
from pathlib import Path

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
    RelayGateway,
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


def test_opt_in_adapter_assigns_and_removes_only_its_own_synthetic_ipv6_address(tmp_path: Path):
    address = "fd00:6e62:7372::1"
    runner = FakeCommandRunner([CommandResult(0), CommandResult(0), CommandResult(0)])
    adapter = OptInWindowsNetworkAdapter(
        interface_alias="NBSR Loopback",
        command_runner=runner,
        enable_synthetic_ipv6=True,
        ownership_journal_path=tmp_path / "owned-state.json",
    )

    assert adapter.ensure_synthetic_ipv6(address) is True
    adapter.restore_owned_state()

    assert runner.calls == [
        ("netsh", "interface", "ipv6", "show", "addresses", "interface=NBSR Loopback"),
        ("netsh", "interface", "ipv6", "add", "address", "interface=NBSR Loopback", address, "store=active"),
        ("netsh", "interface", "ipv6", "delete", "address", "interface=NBSR Loopback", address),
    ]


def test_opt_in_adapter_never_removes_an_existing_or_unavailable_address(tmp_path: Path):
    address = "fd00:6e62:7372::1"
    existing = FakeCommandRunner([CommandResult(0, f"address {address}")])
    adapter = OptInWindowsNetworkAdapter(
        interface_alias="NBSR Loopback",
        command_runner=existing,
        enable_synthetic_ipv6=True,
        ownership_journal_path=tmp_path / "existing-state.json",
    )

    assert adapter.ensure_synthetic_ipv6(address) is True
    adapter.restore_owned_state()
    assert existing.calls == [("netsh", "interface", "ipv6", "show", "addresses", "interface=NBSR Loopback")]

    unavailable = FakeCommandRunner([])
    disabled = OptInWindowsNetworkAdapter(interface_alias="NBSR Loopback", command_runner=unavailable)
    assert disabled.ensure_synthetic_ipv6(address) is False
    assert unavailable.calls == []


def test_opt_in_adapter_does_not_confuse_a_prefix_collision_with_the_owned_address(tmp_path: Path):
    address = "fd00:6e62:7372::1"
    runner = FakeCommandRunner([CommandResult(0, "address fd00:6e62:7372::10"), CommandResult(0)])
    adapter = OptInWindowsNetworkAdapter(
        interface_alias="NBSR Loopback",
        command_runner=runner,
        enable_synthetic_ipv6=True,
        ownership_journal_path=tmp_path / "owned-state.json",
    )

    assert adapter.ensure_synthetic_ipv6(address) is True

    assert runner.calls == [
        ("netsh", "interface", "ipv6", "show", "addresses", "interface=NBSR Loopback"),
        ("netsh", "interface", "ipv6", "add", "address", "interface=NBSR Loopback", address, "store=active"),
    ]


def test_opt_in_adapter_recovers_only_journaled_addresses_after_a_crash(tmp_path: Path):
    address = "fd00:6e62:7372::1"
    journal = tmp_path / "owned-state.json"
    adding = FakeCommandRunner([CommandResult(0), CommandResult(0)])
    first = OptInWindowsNetworkAdapter(
        interface_alias="NBSR Loopback",
        command_runner=adding,
        enable_synthetic_ipv6=True,
        ownership_journal_path=journal,
    )
    assert first.ensure_synthetic_ipv6(address) is True
    assert json.loads(journal.read_text()) == {"synthetic_ipv6": [address]}

    recovering = FakeCommandRunner([CommandResult(0)])
    OptInWindowsNetworkAdapter(
        interface_alias="NBSR Loopback",
        command_runner=recovering,
        enable_synthetic_ipv6=True,
        ownership_journal_path=journal,
    )

    assert recovering.calls == [("netsh", "interface", "ipv6", "delete", "address", "interface=NBSR Loopback", address)]
    assert not journal.exists()


def test_failed_owned_address_restoration_is_journaled_and_retried(tmp_path: Path):
    address = "fd00:6e62:7372::1"
    journal = tmp_path / "owned-state.json"
    journal.write_text(json.dumps({"synthetic_ipv6": [address]}))
    failed = FakeCommandRunner([CommandResult(1)])

    adapter = OptInWindowsNetworkAdapter(
        interface_alias="NBSR Loopback",
        command_runner=failed,
        enable_synthetic_ipv6=True,
        ownership_journal_path=journal,
    )

    assert adapter.restoration_errors == (address,)
    assert json.loads(journal.read_text()) == {"synthetic_ipv6": [address]}

    retry = FakeCommandRunner([CommandResult(0)])
    recovered = OptInWindowsNetworkAdapter(
        interface_alias="NBSR Loopback",
        command_runner=retry,
        enable_synthetic_ipv6=True,
        ownership_journal_path=journal,
    )
    assert recovered.restoration_errors == ()
    assert not journal.exists()


def test_explicit_restoration_surfaces_a_delete_failure(tmp_path: Path):
    address = "fd00:6e62:7372::1"
    journal = tmp_path / "owned-state.json"
    runner = FakeCommandRunner([CommandResult(0), CommandResult(0), CommandResult(1)])
    adapter = OptInWindowsNetworkAdapter(
        interface_alias="NBSR Loopback",
        command_runner=runner,
        enable_synthetic_ipv6=True,
        ownership_journal_path=journal,
    )
    assert adapter.ensure_synthetic_ipv6(address) is True

    with pytest.raises(RuntimeError, match=address):
        adapter.restore_owned_state()

    assert json.loads(journal.read_text()) == {"synthetic_ipv6": [address]}


def test_recovery_never_executes_invalid_or_out_of_range_journal_entries(tmp_path: Path):
    journal = tmp_path / "owned-state.json"
    journal.write_text(json.dumps({"synthetic_ipv6": ["not-an-ip", "2001:db8::1"]}))
    runner = FakeCommandRunner([])

    adapter = OptInWindowsNetworkAdapter(
        interface_alias="NBSR Loopback",
        command_runner=runner,
        enable_synthetic_ipv6=True,
        ownership_journal_path=journal,
    )

    assert runner.calls == []
    assert adapter.restoration_errors == ()
    assert not journal.exists()


def test_mutating_adapter_requires_a_persistent_ownership_journal():
    with pytest.raises(ValueError, match="journal"):
        OptInWindowsNetworkAdapter(
            interface_alias="NBSR Loopback",
            command_runner=FakeCommandRunner([]),
            enable_synthetic_ipv6=True,
        )


def test_unwritable_journal_rolls_back_the_just_added_address(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    address = "fd00:6e62:7372::1"
    journal = tmp_path / "owned-state.json"
    runner = FakeCommandRunner([CommandResult(0), CommandResult(0), CommandResult(0)])
    adapter = OptInWindowsNetworkAdapter(
        interface_alias="NBSR Loopback",
        command_runner=runner,
        enable_synthetic_ipv6=True,
        ownership_journal_path=journal,
    )
    monkeypatch.setattr(Path, "replace", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("read-only journal")))

    with pytest.raises(RuntimeError, match="journal"):
        adapter.ensure_synthetic_ipv6(address)

    assert runner.calls[-1] == (
        "netsh",
        "interface",
        "ipv6",
        "delete",
        "address",
        "interface=NBSR Loopback",
        address,
    )
    assert adapter.restoration_errors == ()


def test_unwritable_journal_surfaces_when_immediate_rollback_also_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    address = "fd00:6e62:7372::1"
    runner = FakeCommandRunner([CommandResult(0), CommandResult(0), CommandResult(1)])
    adapter = OptInWindowsNetworkAdapter(
        interface_alias="NBSR Loopback",
        command_runner=runner,
        enable_synthetic_ipv6=True,
        ownership_journal_path=tmp_path / "owned-state.json",
    )
    monkeypatch.setattr(Path, "replace", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("read-only journal")))

    with pytest.raises(RuntimeError, match="rollback also failed"):
        adapter.ensure_synthetic_ipv6(address)

    assert adapter.restoration_errors == (address,)


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
async def test_reused_listener_refreshes_the_new_hostname_after_address_reassignment():
    route_table = RouteTable()
    first = ClientRoute("first.test", "127.80.0.1", "fd00:6e62:7372::1", "first-binding", 60)
    reassigned = ClientRoute("second.test", "127.80.0.1", "fd00:6e62:7372::1", "second-binding", 60)
    refreshed_hostname: asyncio.Future[str] = asyncio.get_running_loop().create_future()

    async def refresh(hostname: str) -> ClientRoute:
        if not refreshed_hostname.done():
            refreshed_hostname.set_result(hostname)
        return reassigned

    interceptor = LoopbackInterceptor(
        route_table=route_table,
        client_session=ClientSession.generate(),
        relay_host="127.0.0.1",
        relay_port=1,
        gateway_id="edge-local",
        refresh_route=refresh,
    )
    try:
        route_table.put(first)
        await interceptor.start(first, 443)
        route_table.put(reassigned)
        await interceptor.start(reassigned, 443)

        _reader, writer = await asyncio.open_connection(reassigned.synthetic_ipv4, 443)
        try:
            assert await asyncio.wait_for(refreshed_hostname, timeout=1) == "second.test"
        finally:
            writer.close()
            await writer.wait_closed()
    finally:
        await interceptor.close()


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


@pytest.mark.asyncio
async def test_agent_starts_both_http_and_https_listener_paths(settings: Settings):
    service = NameRouteService(pool=SyntheticAddressPool("127.80.0.0/29", "fd00:6e62:7372::/125", ttl_seconds=60), settings=settings)
    agent = WindowsNameAgent(
        name_route_service=service,
        client_session=ClientSession.generate(),
        relay_host="127.0.0.1",
        relay_port=8443,
        gateway_id=settings.name_binding_gateway_id,
    )

    class RecordingInterceptor:
        def __init__(self):
            self.ports = []

        async def start(self, route, local_port, *, intercept_ipv6=False):
            self.ports.append(local_port)

        async def close(self):
            pass

    interceptor = RecordingInterceptor()
    agent.interceptor = interceptor

    await agent.resolve("facebook.test")

    assert interceptor.ports == [80, 443]


@pytest.mark.asyncio
async def test_expired_route_is_refreshed_before_relay_admission():
    origin, origin_port = await start_echo_origin()
    settings = Settings.for_tests(Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate())
    settings.name_binding_ttl_seconds = 1
    relay = NameRelay(settings=settings, resolver=StaticResolver(origin_port))
    relay_server = await asyncio.start_server(relay.handle, "127.0.0.1", 0)

    class CountingService(NameRouteService):
        calls = 0

        def resolve(self, hostname, session_public_key):
            self.calls += 1
            return super().resolve(hostname, session_public_key)

    service = CountingService(
        pool=SyntheticAddressPool("127.80.0.0/29", "fd00:6e62:7372::/125", ttl_seconds=1),
        settings=settings,
    )
    agent = WindowsNameAgent(
        name_route_service=service,
        client_session=ClientSession.generate(),
        relay_host="127.0.0.1",
        relay_port=relay_server.sockets[0].getsockname()[1],
        gateway_id=settings.name_binding_gateway_id,
        listener_ports=(443,),
    )
    try:
        route = await agent.resolve("facebook.test")
        await asyncio.sleep(1.1)

        assert await send_to_synthetic(route.synthetic_ipv4, 443, b"refreshed") == b"origin:refreshed"
        assert service.calls >= 2
    finally:
        await agent.close()
        relay_server.close()
        await relay_server.wait_closed()
        origin.close()
        await origin.wait_closed()


@pytest.mark.asyncio
async def test_interceptor_fails_over_across_ordered_authenticated_gateways():
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
        listener_ports=(443,),
        gateways=(
            RelayGateway("127.0.0.1", 1),
            RelayGateway("127.0.0.1", relay_server.sockets[0].getsockname()[1]),
        ),
    )
    try:
        route = await agent.resolve("facebook.test")
        assert await send_to_synthetic(route.synthetic_ipv4, 443, b"fallback") == b"origin:fallback"
    finally:
        await agent.close()
        relay_server.close()
        await relay_server.wait_closed()
        origin.close()
        await origin.wait_closed()
