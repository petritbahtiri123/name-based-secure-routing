from __future__ import annotations

import asyncio
import json
import secrets
import ssl
import struct
import subprocess
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network, ip_address
from pathlib import Path
from typing import Awaitable, Callable, Protocol, Sequence

import jwt

from nbsr.dns_stub import ClientRoute, DnsStub, RouteTable
from nbsr.name_security import ClientSession, sign_relay_proof
from nbsr.name_service import NameRouteResponse, NameRouteService


_ALLOWED_PORTS = frozenset((80, 443))
_SYNTHETIC_LOOPBACK_NETWORK = IPv4Network("127.80.0.0/16")
_SYNTHETIC_IPV6_NETWORK = IPv6Network("fd00:6e62:7372::/48")
_MAX_HANDSHAKE_BYTES = 64 * 1024


@dataclass(frozen=True)
class BoundListener:
    host: str
    port: int
    server: asyncio.AbstractServer


@dataclass(frozen=True)
class RelayGateway:
    host: str
    port: int
    tls_ca_path: Path | str | None = None
    server_name: str = "name-relay"


class WindowsNetworkAdapter(Protocol):
    """Boundary for Windows DNS/proxy settings; implementations own their changes."""

    def configure_dns_stub(self, host: str, port: int) -> None: ...

    def ensure_synthetic_ipv6(self, address: str) -> bool: ...

    def restore_owned_state(self) -> None: ...


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""


class CommandRunner(Protocol):
    def run(self, arguments: Sequence[str]) -> CommandResult: ...


class SubprocessCommandRunner:
    """Runs argument vectors only; callers must opt in before it is used."""

    def run(self, arguments: Sequence[str]) -> CommandResult:
        completed = subprocess.run(arguments, capture_output=True, check=False, text=True, shell=False)
        return CommandResult(completed.returncode, completed.stdout)


class RecordingWindowsNetworkAdapter:
    """Safe default that records intended state without changing Windows settings."""

    def __init__(self) -> None:
        self.owned_dns_stub: tuple[str, int] | None = None

    def configure_dns_stub(self, host: str, port: int) -> None:
        self.owned_dns_stub = (host, port)

    def ensure_synthetic_ipv6(self, address: str) -> bool:
        return False

    def restore_owned_state(self) -> None:
        self.owned_dns_stub = None


class OptInWindowsNetworkAdapter:
    """Owns only IPv6 ULA addresses it adds through an injected command runner."""

    def __init__(
        self,
        *,
        interface_alias: str,
        command_runner: CommandRunner,
        enable_synthetic_ipv6: bool = False,
        ownership_journal_path: Path | str | None = None,
    ) -> None:
        self._interface_alias = interface_alias
        self._command_runner = command_runner
        self._enabled = enable_synthetic_ipv6
        if self._enabled and ownership_journal_path is None:
            raise ValueError("A persistent ownership journal is required when synthetic IPv6 mutation is enabled")
        self._owned_ipv6_addresses: set[str] = set()
        self._journal_path = Path(ownership_journal_path) if ownership_journal_path else None
        self.restoration_errors: tuple[str, ...] = ()
        self.owned_dns_stub: tuple[str, int] | None = None
        self._recover_owned_state()

    def configure_dns_stub(self, host: str, port: int) -> None:
        self.owned_dns_stub = (host, port)

    def ensure_synthetic_ipv6(self, address: str) -> bool:
        if not self._enabled or not self._is_synthetic_ipv6(address):
            return False
        if address in self._owned_ipv6_addresses:
            return True
        existing = self._command_runner.run(self._show_addresses_command())
        if existing.returncode != 0:
            return False
        if self._address_is_present(existing.stdout, address):
            return True
        added = self._command_runner.run(self._add_address_command(address))
        if added.returncode != 0:
            return False
        self._owned_ipv6_addresses.add(address)
        try:
            self._write_journal()
        except OSError as exc:
            removed = self._command_runner.run(self._delete_address_command(address))
            if removed.returncode == 0:
                self._owned_ipv6_addresses.remove(address)
            self.restoration_errors = tuple(sorted(self._owned_ipv6_addresses))
            self._remove_temporary_journal()
            outcome = "the new address was rolled back" if removed.returncode == 0 else "the immediate rollback also failed"
            raise RuntimeError(f"Failed to persist ownership journal; {outcome}") from exc
        return True

    def restore_owned_state(self) -> None:
        self._restore_owned_state(raise_on_failure=True)

    def _restore_owned_state(self, *, raise_on_failure: bool) -> None:
        try:
            for address in tuple(self._owned_ipv6_addresses):
                removed = self._command_runner.run(self._delete_address_command(address))
                if removed.returncode == 0:
                    self._owned_ipv6_addresses.remove(address)
            self.restoration_errors = tuple(sorted(self._owned_ipv6_addresses))
            self._write_journal()
        finally:
            self.owned_dns_stub = None
        if raise_on_failure and self.restoration_errors:
            raise RuntimeError(f"Failed to restore owned synthetic IPv6 addresses: {', '.join(self.restoration_errors)}")

    def _recover_owned_state(self) -> None:
        if self._journal_path is None or not self._journal_path.exists():
            return
        try:
            state = json.loads(self._journal_path.read_text(encoding="utf-8"))
            addresses = state.get("synthetic_ipv6", []) if isinstance(state, dict) else []
        except (OSError, json.JSONDecodeError):
            self.restoration_errors = ("ownership journal unreadable",)
            return
        self._owned_ipv6_addresses = {address for address in addresses if isinstance(address, str) and self._is_synthetic_ipv6(address)}
        self._restore_owned_state(raise_on_failure=False)

    def _write_journal(self) -> None:
        if self._journal_path is None:
            return
        if not self._owned_ipv6_addresses:
            self._journal_path.unlink(missing_ok=True)
            return
        self._journal_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._journal_path.with_suffix(f"{self._journal_path.suffix}.tmp")
        temporary.write_text(
            json.dumps({"synthetic_ipv6": sorted(self._owned_ipv6_addresses)}, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.replace(self._journal_path)

    def _remove_temporary_journal(self) -> None:
        if self._journal_path is not None:
            self._journal_path.with_suffix(f"{self._journal_path.suffix}.tmp").unlink(missing_ok=True)

    def _show_addresses_command(self) -> tuple[str, ...]:
        return ("netsh", "interface", "ipv6", "show", "addresses", f"interface={self._interface_alias}")

    def _add_address_command(self, address: str) -> tuple[str, ...]:
        return ("netsh", "interface", "ipv6", "add", "address", f"interface={self._interface_alias}", address, "store=active")

    def _delete_address_command(self, address: str) -> tuple[str, ...]:
        return ("netsh", "interface", "ipv6", "delete", "address", f"interface={self._interface_alias}", address)

    @staticmethod
    def _is_synthetic_ipv6(address: str) -> bool:
        try:
            parsed = ip_address(address)
        except ValueError:
            return False
        return isinstance(parsed, IPv6Address) and str(parsed) == address and parsed in _SYNTHETIC_IPV6_NETWORK

    @staticmethod
    def _address_is_present(output: str, address: str) -> bool:
        for token in output.split():
            try:
                if str(ip_address(token.strip("[](),;"))) == address:
                    return True
            except ValueError:
                continue
        return False


class LoopbackInterceptor:
    def __init__(
        self,
        *,
        route_table: RouteTable,
        client_session: ClientSession,
        relay_host: str,
        relay_port: int,
        gateway_id: str,
        relay_tls_ca_path: Path | str | None = None,
        relay_server_name: str = "name-relay",
        handshake_timeout_seconds: float = 2.0,
        gateways: Sequence[RelayGateway] | None = None,
        refresh_route: Callable[[str], Awaitable[ClientRoute]] | None = None,
    ) -> None:
        if handshake_timeout_seconds <= 0:
            raise ValueError("handshake timeout must be positive")
        self._route_table = route_table
        self._client_session = client_session
        self._gateway_id = gateway_id
        configured_gateways = gateways or (RelayGateway(relay_host, relay_port, relay_tls_ca_path, relay_server_name),)
        if not configured_gateways:
            raise ValueError("at least one relay gateway is required")
        self._gateways = tuple(configured_gateways)
        self._gateway_tls = tuple(
            self._create_gateway_tls_context(gateway) for gateway in self._gateways
        )
        self._refresh_route = refresh_route
        self._handshake_timeout_seconds = handshake_timeout_seconds
        self._listeners: dict[tuple[str, int], BoundListener] = {}
        self._hostnames_by_address: dict[str, str] = {}

    async def start(self, route: ClientRoute, local_port: int, *, intercept_ipv6: bool = False) -> BoundListener:
        if type(local_port) is not int or local_port not in _ALLOWED_PORTS:
            raise ValueError("loopback interception only supports ports 80 and 443")
        if not self._is_synthetic_loopback(route.synthetic_ipv4):
            raise ValueError("interceptor only binds configured loopback synthetic addresses")
        if self._route_table.lookup(route.synthetic_ipv4) != route or self._route_table.lookup(route.synthetic_ipv6) != route:
            raise ValueError("interceptor only binds configured synthetic routes")
        key = (route.synthetic_ipv4, local_port)
        self._hostnames_by_address[route.synthetic_ipv4] = route.hostname
        self._hostnames_by_address[route.synthetic_ipv6] = route.hostname
        existing = self._listeners.get(key)
        if existing is not None:
            return existing
        server = await asyncio.start_server(self._handle_connection, route.synthetic_ipv4, local_port)
        listener = BoundListener(route.synthetic_ipv4, local_port, server)
        self._listeners[key] = listener
        if intercept_ipv6:
            try:
                ipv6_server = await asyncio.start_server(self._handle_connection, route.synthetic_ipv6, local_port)
            except OSError:
                server.close()
                await server.wait_closed()
                self._listeners.pop(key, None)
                raise
            self._listeners[(route.synthetic_ipv6, local_port)] = BoundListener(route.synthetic_ipv6, local_port, ipv6_server)
        return listener

    async def close(self) -> None:
        listeners = tuple(self._listeners.values())
        self._listeners.clear()
        self._hostnames_by_address.clear()
        for listener in listeners:
            listener.server.close()
        await asyncio.gather(*(listener.server.wait_closed() for listener in listeners))

    async def _handle_connection(self, client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter) -> None:
        relay_writer: asyncio.StreamWriter | None = None
        try:
            socket_name = client_writer.get_extra_info("sockname")
            if not socket_name:
                return
            synthetic_address = socket_name[0]
            hostname = self._hostnames_by_address.get(synthetic_address)
            route = self._route_table.lookup(synthetic_address)
            if hostname is not None and self._refresh_route is not None:
                route = await self._refresh_route(hostname)
            if route is None:
                return
            if synthetic_address not in (route.synthetic_ipv4, route.synthetic_ipv6):
                return
            local_port = socket_name[1]
            relay_reader, relay_writer = await self._open_admitted_gateway(route, synthetic_address, local_port)
            await asyncio.gather(self._copy(client_reader, relay_writer), self._copy(relay_reader, client_writer))
        except (OSError, TimeoutError, ValueError, jwt.PyJWTError, asyncio.IncompleteReadError):
            pass
        finally:
            if relay_writer is not None:
                relay_writer.close()
                await relay_writer.wait_closed()
            client_writer.close()
            await client_writer.wait_closed()

    async def _open_admitted_gateway(
        self,
        route: ClientRoute,
        synthetic_address: str,
        local_port: int,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        for gateway, tls_context in zip(self._gateways, self._gateway_tls, strict=True):
            relay_writer: asyncio.StreamWriter | None = None
            try:
                relay_reader, relay_writer = await asyncio.wait_for(
                    asyncio.open_connection(
                        gateway.host,
                        gateway.port,
                        ssl=tls_context,
                        server_hostname=gateway.server_name,
                    ),
                    timeout=self._handshake_timeout_seconds,
                )
                await asyncio.wait_for(
                    self._send_handshake(relay_writer, route, synthetic_address, local_port),
                    self._handshake_timeout_seconds,
                )
                admission = await asyncio.wait_for(
                    relay_reader.readexactly(1),
                    timeout=self._handshake_timeout_seconds,
                )
                if admission == b"\x01":
                    return relay_reader, relay_writer
            except (OSError, TimeoutError, asyncio.IncompleteReadError):
                pass
            if relay_writer is not None:
                relay_writer.close()
                await relay_writer.wait_closed()
        raise OSError("all configured NBSR gateways rejected or failed admission")

    @staticmethod
    def _create_gateway_tls_context(gateway: RelayGateway) -> ssl.SSLContext:
        context = ssl.create_default_context(cafile=str(gateway.tls_ca_path) if gateway.tls_ca_path else None)
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        return context

    async def _send_handshake(
        self, relay_writer: asyncio.StreamWriter, route: ClientRoute, synthetic_address: str, local_port: int
    ) -> None:
        claims = jwt.decode(route.route_binding, options={"verify_signature": False, "verify_exp": False})
        route_id = claims.get("jti")
        if not isinstance(route_id, str) or not route_id:
            raise ValueError("route binding is missing its route ID")
        nonce = secrets.token_urlsafe(32)
        handshake = {
            "hostname": route.hostname,
            "synthetic_address": synthetic_address,
            "port": local_port,
            "gateway_id": self._gateway_id,
            "binding": route.route_binding,
            "route_id": route_id,
            "nonce": nonce,
            "proof": sign_relay_proof(self._client_session, route_id, nonce, local_port),
        }
        encoded = json.dumps(handshake, separators=(",", ":")).encode("utf-8")
        if len(encoded) > _MAX_HANDSHAKE_BYTES:
            raise ValueError("relay handshake is too large")
        relay_writer.write(struct.pack(">I", len(encoded)) + encoded)
        await relay_writer.drain()

    @staticmethod
    async def _copy(source: asyncio.StreamReader, destination: asyncio.StreamWriter) -> None:
        while chunk := await source.read(65536):
            destination.write(chunk)
            await destination.drain()
        try:
            destination.write_eof()
            await destination.drain()
        except (AttributeError, OSError, RuntimeError):
            destination.close()

    @staticmethod
    def _is_synthetic_loopback(address: str) -> bool:
        parsed = ip_address(address)
        return isinstance(parsed, IPv4Address) and parsed in _SYNTHETIC_LOOPBACK_NETWORK


class WindowsNameAgent:
    def __init__(
        self,
        *,
        name_route_service: NameRouteService,
        client_session: ClientSession,
        relay_host: str,
        relay_port: int,
        gateway_id: str,
        test_https_port: int | None = None,
        listener_ports: Sequence[int] = (80, 443),
        relay_tls_ca_path: Path | str | None = None,
        relay_server_name: str = "name-relay",
        gateways: Sequence[RelayGateway] | None = None,
        network_adapter: WindowsNetworkAdapter | None = None,
    ) -> None:
        self._name_route_service = name_route_service
        self._client_session = client_session
        if test_https_port is not None:
            listener_ports = (test_https_port,)
        if not listener_ports or any(type(port) is not int or port not in _ALLOWED_PORTS for port in listener_ports):
            raise ValueError("listener ports must contain HTTP 80 and/or HTTPS 443")
        self.listener_ports = tuple(dict.fromkeys(listener_ports))
        self.test_https_port = 443 if 443 in self.listener_ports else self.listener_ports[0]
        self.route_table = RouteTable()
        self.network_adapter = network_adapter or RecordingWindowsNetworkAdapter()
        self.ipv6_interception_available = False
        self.ipv6_interception_status = "disabled until an opt-in Windows synthetic IPv6 assignment succeeds"
        self.interceptor = LoopbackInterceptor(
            route_table=self.route_table,
            client_session=client_session,
            relay_host=relay_host,
            relay_port=relay_port,
            gateway_id=gateway_id,
            relay_tls_ca_path=relay_tls_ca_path,
            relay_server_name=relay_server_name,
            gateways=gateways,
            refresh_route=self._refresh_route,
        )

    async def resolve(self, hostname: str) -> ClientRoute:
        route = await self._refresh_route(hostname)
        for local_port in self.listener_ports:
            await self.interceptor.start(route, local_port, intercept_ipv6=self.ipv6_interception_available)
        return route

    async def _refresh_route(self, hostname: str) -> ClientRoute:
        capabilities = tuple(f"tcp:{port}" for port in self.listener_ports)
        response = self._name_route_service.resolve(hostname, self._client_session.public_key_b64, capabilities)
        route = self._from_response(response)
        self.route_table.put(route)
        self.ipv6_interception_available = self.network_adapter.ensure_synthetic_ipv6(route.synthetic_ipv6)
        self.ipv6_interception_status = (
            "available" if self.ipv6_interception_available else "unavailable: synthetic IPv6 assignment is disabled or failed"
        )
        return route

    def configure_dns_stub(self, host: str, port: int) -> None:
        self.network_adapter.configure_dns_stub(host, port)

    def create_dns_stub(self, resolve_route: Callable[[str], ClientRoute], *, ttl_seconds: int = 60) -> DnsStub:
        """Build a DNS stub that withholds AAAA answers until this agent can intercept them."""
        return DnsStub(resolve_route, self.route_table, ttl_seconds=ttl_seconds, ipv6_available=lambda: self.ipv6_interception_available)

    async def close(self) -> None:
        try:
            await self.interceptor.close()
        finally:
            self.network_adapter.restore_owned_state()

    @staticmethod
    def _from_response(response: NameRouteResponse) -> ClientRoute:
        return ClientRoute(
            hostname=response.hostname,
            synthetic_ipv4=response.synthetic_ipv4,
            synthetic_ipv6=response.synthetic_ipv6,
            route_binding=response.route_binding,
            expires_in=response.expires_in,
        )
