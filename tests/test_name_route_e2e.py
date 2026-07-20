from __future__ import annotations

import asyncio
import importlib.util
import json
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace

import httpx
import pytest
import pytest_asyncio
import uvicorn
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nbsr.config import Settings
from nbsr.control_plane import app, get_name_route_service, get_settings
from nbsr.dns_stub import ClientRoute
from nbsr.name_relay import NameRelay, ResolvedEndpoint
from nbsr.name_security import ClientSession
from nbsr.name_service import NameRouteResponse, NameRouteService
from nbsr.synthetic import SyntheticAddressPool
from nbsr.windows_agent import RecordingWindowsNetworkAdapter, WindowsNameAgent


@dataclass
class LoopbackService:
    server: asyncio.AbstractServer
    address: str
    port: int

    async def close(self) -> None:
        self.server.close()
        await self.server.wait_closed()


class HiddenOrigin(LoopbackService):
    observed_peer: str | None = None


class StaticResolver:
    def __init__(self, origin: HiddenOrigin):
        self._origin = origin

    async def resolve(self, hostname: str, port: int) -> list[ResolvedEndpoint]:
        assert (hostname, port) == ("facebook.test", 443)
        return [ResolvedEndpoint(self._origin.address, self._origin.port)]


@dataclass
class LiveNameRouteApi:
    server: uvicorn.Server
    task: asyncio.Task[None]
    address: str

    async def close(self) -> None:
        self.server.should_exit = True
        await self.task
        app.dependency_overrides.clear()


class E2EAgent:
    def __init__(self, api_address: str, relay: LoopbackService, settings: Settings):
        self._api_address = api_address
        self._session = ClientSession.generate()
        self._routes: list[NameRouteResponse] = []
        unused_service = NameRouteService(
            pool=SyntheticAddressPool("127.80.0.0/29", "fd00:6e62:7372::/125", ttl_seconds=60),
            settings=settings,
        )
        self._agent = WindowsNameAgent(
            name_route_service=unused_service,
            client_session=self._session,
            relay_host=relay.address,
            relay_port=relay.port,
            gateway_id=settings.name_binding_gateway_id,
            network_adapter=RecordingWindowsNetworkAdapter(),
        )

    async def resolve(self, hostname: str) -> NameRouteResponse:
        request = {
            "protocol_version": 1,
            "request_id": "deterministic-e2e",
            "hostname": hostname,
            "transport": "tcp",
            "client_nonce": "deterministic-client-nonce",
            "client_public_key": self._session.public_key_b64,
            "capabilities": ["tcp:443"],
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{self._api_address}/v1/name-routes/resolve", json=request)
            response.raise_for_status()
        route = NameRouteResponse.model_validate(response.json())
        client_route = ClientRoute(
            hostname=route.hostname,
            synthetic_ipv4=route.synthetic_ipv4,
            synthetic_ipv6=route.synthetic_ipv6,
            route_binding=route.route_binding,
            expires_in=route.expires_in,
        )
        self._agent.route_table.put(client_route)
        await self._agent.interceptor.start(client_route, 443)
        self._routes.append(route)
        return route

    async def request(self, route: NameRouteResponse, *, port: int, payload: bytes) -> bytes:
        reader, writer = await asyncio.open_connection(route.synthetic_ipv4, port)
        try:
            writer.write(payload)
            await writer.drain()
            return await reader.readexactly(len(b"hidden-origin:") + len(payload))
        finally:
            writer.close()
            await writer.wait_closed()

    def export_client_state(self) -> str:
        return json.dumps([route.model_dump(mode="json") for route in self._routes], sort_keys=True)

    async def close(self) -> None:
        await self._agent.close()


@dataclass
class E2EStack:
    origin: HiddenOrigin
    relay: LoopbackService
    api: LiveNameRouteApi
    agent: E2EAgent

    async def close(self) -> None:
        await self.agent.close()
        await self.api.close()
        await self.relay.close()
        await self.origin.close()


def load_name_relay_entrypoint() -> ModuleType:
    path = Path(__file__).parents[1] / "services" / "name-relay" / "app.py"
    spec = importlib.util.spec_from_file_location("nbsr_name_relay_entrypoint", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("name-relay entrypoint is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_name_relay_entrypoint_runs_outside_repository(tmp_path: Path):
    path = Path(__file__).parents[1] / "services" / "name-relay" / "app.py"
    completed = subprocess.run(
        [sys.executable, str(path), "--help"],
        cwd=tmp_path,
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_kubernetes_key_mounts_do_not_mask_service_account_secrets():
    manifest = (Path(__file__).parents[1] / "deploy" / "kind" / "nbsr.yaml").read_text(encoding="utf-8")
    assert "mountPath: /run/secrets" not in manifest


def test_kubernetes_opa_loads_the_policy_file_not_configmap_symlinks():
    manifest = (Path(__file__).parents[1] / "deploy" / "kind" / "nbsr.yaml").read_text(encoding="utf-8")
    assert 'args: ["run", "--server", "--addr=0.0.0.0:8181", "/policy/nbsr.rego"]' in manifest


def test_origin_leak_assertion_runs_inside_gateway(monkeypatch: pytest.MonkeyPatch):
    entrypoint = load_name_relay_entrypoint()
    observed: dict[str, object] = {}

    def run(arguments, **kwargs):
        observed["arguments"] = arguments
        observed.update(kwargs)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(entrypoint.subprocess, "run", run)
    result = entrypoint.assert_origin_hidden('{"synthetic_ipv4":"127.80.0.1"}')

    assert result is None
    assert observed["input"] == '{"synthetic_ipv4":"127.80.0.1"}'
    assert "socket.gethostbyname('facebook.test')" in observed["arguments"][-1]


async def start_hidden_origin() -> HiddenOrigin:
    origin: HiddenOrigin

    async def echo(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        origin.observed_peer = peer[0]
        try:
            while payload := await reader.read(65536):
                writer.write(b"hidden-origin:" + payload)
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(echo, "127.0.0.1", 0)
    host, port = server.sockets[0].getsockname()[:2]
    origin = HiddenOrigin(server=server, address=host, port=port)
    return origin


async def start_name_route_api(settings: Settings, service: NameRouteService) -> LiveNameRouteApi:
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_name_route_service] = lambda: service
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    host, port = sock.getsockname()[:2]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="off"))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    while not server.started:
        if task.done():
            await task
        await asyncio.sleep(0)
    return LiveNameRouteApi(server=server, task=task, address=f"http://{host}:{port}")


@pytest_asyncio.fixture()
async def stack() -> E2EStack:
    entrypoint = load_name_relay_entrypoint()
    assert callable(entrypoint.main)
    settings = Settings.for_tests(
        Ed25519PrivateKey.generate(),
        Ed25519PrivateKey.generate(),
        Ed25519PrivateKey.generate(),
    )
    origin = await start_hidden_origin()
    relay_impl = NameRelay(settings=settings, resolver=StaticResolver(origin))
    relay_server = await asyncio.start_server(relay_impl.handle, "127.0.0.1", 0)
    relay_host, relay_port = relay_server.sockets[0].getsockname()[:2]
    relay = LoopbackService(relay_server, relay_host, relay_port)
    service = NameRouteService(
        pool=SyntheticAddressPool("127.80.0.0/29", "fd00:6e62:7372::/125", ttl_seconds=60),
        settings=settings,
    )
    api = await start_name_route_api(settings, service)
    e2e_stack = E2EStack(origin=origin, relay=relay, api=api, agent=E2EAgent(api.address, relay, settings))
    try:
        yield e2e_stack
    finally:
        await e2e_stack.close()


@pytest.mark.asyncio
async def test_name_route_end_to_end_hides_origin_address(stack: E2EStack):
    route = await stack.agent.resolve("facebook.test")
    response = await stack.agent.request(route, port=443, payload=b"client-hello")
    assert response == b"hidden-origin:client-hello"
    assert stack.origin.address not in route.model_dump_json()
    assert stack.origin.address not in stack.agent.export_client_state()
    assert stack.origin.observed_peer == stack.relay.address
