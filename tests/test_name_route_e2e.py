from __future__ import annotations

import asyncio
import importlib.util
import json
import socket
import ssl
import subprocess
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from pathlib import Path
from types import ModuleType, SimpleNamespace

import httpx
import pytest
import pytest_asyncio
import uvicorn
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from nbsr.config import Settings
from nbsr.dns_stub import ClientRoute
from nbsr.name_control import app, get_name_route_service, get_settings
from nbsr.name_relay import NameRelay, ResolvedEndpoint
from nbsr.name_security import ClientSession
from nbsr.name_service import NameRouteResponse, NameRouteService
from nbsr.synthetic import SyntheticAddressPool
from nbsr.windows_agent import RecordingWindowsNetworkAdapter, WindowsNameAgent


@dataclass(frozen=True)
class TlsMaterial:
    ca: Path
    wrong_ca: Path
    control_cert: Path
    control_key: Path
    relay_cert: Path
    relay_key: Path


def write_tls_material(directory: Path) -> TlsMaterial:
    now = datetime.now(UTC)

    def create_ca(common_name: str) -> tuple[Ed25519PrivateKey, x509.Certificate]:
        key = Ed25519PrivateKey.generate()
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=True,
                    crl_sign=True,
                    encipher_only=None,
                    decipher_only=None,
                ),
                critical=True,
            )
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .sign(key, algorithm=None)
        )
        return key, cert

    ca_key, ca_cert = create_ca("NBSR ISP test CA")
    _, wrong_ca_cert = create_ca("Untrusted test CA")

    def create_server(name: str) -> tuple[bytes, bytes]:
        key = Ed25519PrivateKey.generate()
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(ca_cert.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(
                x509.SubjectAlternativeName([x509.DNSName(name), x509.DNSName("localhost"), x509.IPAddress(ip_address("127.0.0.1"))]),
                critical=False,
            )
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=None,
                    decipher_only=None,
                ),
                critical=True,
            )
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .sign(ca_key, algorithm=None)
        )
        return (
            cert.public_bytes(serialization.Encoding.PEM),
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ),
        )

    control_cert, control_key = create_server("name-control")
    relay_cert, relay_key = create_server("name-relay")
    paths = TlsMaterial(
        ca=directory / "isp-ca.pem",
        wrong_ca=directory / "wrong-ca.pem",
        control_cert=directory / "control-cert.pem",
        control_key=directory / "control-key.pem",
        relay_cert=directory / "relay-cert.pem",
        relay_key=directory / "relay-key.pem",
    )
    paths.ca.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    paths.wrong_ca.write_bytes(wrong_ca_cert.public_bytes(serialization.Encoding.PEM))
    paths.control_cert.write_bytes(control_cert)
    paths.control_key.write_bytes(control_key)
    paths.relay_cert.write_bytes(relay_cert)
    paths.relay_key.write_bytes(relay_key)
    return paths


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
    def __init__(self, api_address: str, relay: LoopbackService, settings: Settings, tls: TlsMaterial):
        self._api_address = api_address
        self._control_tls = ssl.create_default_context(cafile=str(tls.ca))
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
            relay_tls_ca_path=tls.ca,
            relay_server_name="name-relay",
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
        async with httpx.AsyncClient(verify=self._control_tls) as client:
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
    tls: TlsMaterial
    cleanup: AsyncExitStack

    async def close(self) -> None:
        await self.cleanup.aclose()


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


def test_kubernetes_relay_supports_http_and_is_host_reachable_in_kind():
    root = Path(__file__).parents[1]
    manifest = (root / "deploy" / "kind" / "nbsr.yaml").read_text(encoding="utf-8")
    cluster = (root / "deploy" / "kind" / "cluster.yaml").read_text(encoding="utf-8")
    assert "- {port: 80, protocol: TCP}" in manifest
    assert "containerPort: 30443" in cluster
    assert "hostPort: 8443" in cluster


def test_legacy_demo_waits_for_compose_readiness():
    root = Path(__file__).parents[1]
    for script in (root / "scripts" / "demo.ps1", root / "scripts" / "demo.sh"):
        assert "docker compose up -d --build --wait" in script.read_text(encoding="utf-8")


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


def test_origin_peer_assertion_matches_relay_container_network_identity(monkeypatch: pytest.MonkeyPatch):
    entrypoint = load_name_relay_entrypoint()
    responses = iter(
        [
            SimpleNamespace(returncode=0, stdout="relay-container-id\n"),
            SimpleNamespace(returncode=0, stdout="172.30.0.8\n172.31.0.9\n"),
            SimpleNamespace(returncode=0, stdout="name-origin | ORIGIN_OBSERVED_PEER=172.31.0.9\n"),
        ]
    )
    monkeypatch.setattr(entrypoint.subprocess, "run", lambda *_args, **_kwargs: next(responses))
    assert entrypoint.assert_origin_observed_relay() is None


def test_bootstrap_creates_distinct_trusted_isp_server_certificates(tmp_path: Path):
    root = Path(__file__).parents[1]
    completed = subprocess.run(
        [sys.executable, str(root / "scripts" / "bootstrap.py"), "--output-root", str(tmp_path)],
        cwd=root,
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    isp_ca = x509.load_pem_x509_certificate((tmp_path / "secrets" / "isp-ca.pem").read_bytes())
    enterprise_ca = x509.load_pem_x509_certificate((tmp_path / "secrets" / "demo-ca.pem").read_bytes())
    assert isp_ca.fingerprint(hashes.SHA256()) != enterprise_ca.fingerprint(hashes.SHA256())
    for prefix, dns_name in (("control", "name-control"), ("relay", "name-relay")):
        certificate = x509.load_pem_x509_certificate((tmp_path / "secrets" / f"isp-{prefix}-cert.pem").read_bytes())
        san = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        assert certificate.issuer == isp_ca.subject
        assert dns_name in san.get_values_for_type(x509.DNSName)
        assert "localhost" in san.get_values_for_type(x509.DNSName)
        assert ip_address("127.0.0.1") in san.get_values_for_type(x509.IPAddress)
        isp_ca.public_key().verify(certificate.signature, certificate.tbs_certificate_bytes)


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


async def start_name_route_api(settings: Settings, service: NameRouteService, tls: TlsMaterial) -> LiveNameRouteApi:
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_name_route_service] = lambda: service
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    host, port = sock.getsockname()[:2]
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            log_level="error",
            lifespan="off",
            ssl_certfile=str(tls.control_cert),
            ssl_keyfile=str(tls.control_key),
        )
    )
    task = asyncio.create_task(server.serve(sockets=[sock]))
    while not server.started:
        if task.done():
            await task
        await asyncio.sleep(0)
    return LiveNameRouteApi(server=server, task=task, address=f"https://{host}:{port}")


@pytest_asyncio.fixture()
async def stack(tmp_path: Path) -> E2EStack:
    entrypoint = load_name_relay_entrypoint()
    assert callable(entrypoint.main)
    tls = write_tls_material(tmp_path)
    settings = Settings.for_tests(
        Ed25519PrivateKey.generate(),
        Ed25519PrivateKey.generate(),
        Ed25519PrivateKey.generate(),
    )
    async with AsyncExitStack() as cleanup:
        origin = await start_hidden_origin()
        cleanup.push_async_callback(origin.close)
        relay_impl = NameRelay(settings=settings, resolver=StaticResolver(origin))
        relay_tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        relay_tls.load_cert_chain(tls.relay_cert, tls.relay_key)
        relay_server = await asyncio.start_server(relay_impl.handle, "127.0.0.1", 0, ssl=relay_tls)
        relay_host, relay_port = relay_server.sockets[0].getsockname()[:2]
        relay = LoopbackService(relay_server, relay_host, relay_port)
        cleanup.push_async_callback(relay.close)
        service = NameRouteService(
            pool=SyntheticAddressPool("127.80.0.0/29", "fd00:6e62:7372::/125", ttl_seconds=60),
            settings=settings,
        )
        api = await start_name_route_api(settings, service, tls)
        cleanup.push_async_callback(api.close)
        agent = E2EAgent(api.address, relay, settings, tls)
        cleanup.push_async_callback(agent.close)
        yield E2EStack(origin=origin, relay=relay, api=api, agent=agent, tls=tls, cleanup=cleanup)


@pytest.mark.asyncio
async def test_name_route_end_to_end_hides_origin_address(stack: E2EStack):
    route = await stack.agent.resolve("facebook.test")
    response = await stack.agent.request(route, port=443, payload=b"client-hello")
    assert response == b"hidden-origin:client-hello"
    assert stack.origin.address not in route.model_dump_json()
    assert stack.origin.address not in stack.agent.export_client_state()
    assert stack.origin.observed_peer is not None


@pytest.mark.asyncio
async def test_untrusted_name_control_and_relay_certificates_fail_closed(stack: E2EStack):
    wrong_control_tls = ssl.create_default_context(cafile=str(stack.tls.wrong_ca))
    async with httpx.AsyncClient(verify=wrong_control_tls) as client:
        with pytest.raises(httpx.ConnectError):
            await client.post(f"{stack.api.address}/v1/name-routes/resolve", json={})

    wrong_relay_tls = ssl.create_default_context(cafile=str(stack.tls.wrong_ca))
    with pytest.raises(ssl.SSLCertVerificationError):
        await asyncio.open_connection(
            stack.relay.address,
            stack.relay.port,
            ssl=wrong_relay_tls,
            server_hostname="name-relay",
        )
    assert stack.origin.observed_peer is None
