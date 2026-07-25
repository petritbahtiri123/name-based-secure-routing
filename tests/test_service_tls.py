import asyncio
import ssl
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from nbsr.service_tls import ServiceTlsError, create_mtls_client_context


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def tls_material(tmp_path_factory):
    output = tmp_path_factory.mktemp("service-tls")
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "bootstrap.py"), "--output-root", str(output)],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    return output / "secrets"


def server_context(tls_material: Path, service: str, *, certificate_path: Path | None = None) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.load_cert_chain(
        certificate_path or tls_material / f"enterprise-{service}-cert.pem",
        tls_material / f"enterprise-{service}-key.pem",
    )
    context.load_verify_locations(tls_material / "demo-ca.pem")
    context.verify_mode = ssl.CERT_REQUIRED
    return context


def gateway_context(tls_material: Path, *, ca_name: str = "demo-ca.pem") -> ssl.SSLContext:
    return create_mtls_client_context(
        url="https://payments-service:7000",
        ca_path=tls_material / ca_name,
        certificate_path=tls_material / "enterprise-gateway-client-cert.pem",
        private_key_path=tls_material / "enterprise-gateway-client-key.pem",
    )


async def start_server(context: ssl.SSLContext | None):
    async def respond(_reader, writer):
        writer.write(b"ok")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    return await asyncio.start_server(respond, "127.0.0.1", 0, ssl=context)


async def connection_is_rejected(
    context: ssl.SSLContext,
    port: int,
    *,
    server_hostname: str = "payments-service",
) -> bool:
    writer = None
    try:
        reader, writer = await asyncio.open_connection(
            "127.0.0.1",
            port,
            ssl=context,
            server_hostname=server_hostname,
        )
        writer.write(b"probe")
        await writer.drain()
        return await asyncio.wait_for(reader.read(), timeout=1) != b"ok"
    except (ConnectionError, OSError, ssl.SSLError, TimeoutError):
        return True
    finally:
        if writer is not None:
            writer.close()
            await writer.wait_closed()


@pytest.mark.asyncio
async def test_valid_service_mtls_succeeds(tls_material):
    server = await start_server(server_context(tls_material, "payments-service"))
    try:
        reader, writer = await asyncio.open_connection(
            "127.0.0.1",
            server.sockets[0].getsockname()[1],
            ssl=gateway_context(tls_material),
            server_hostname="payments-service",
        )
        assert await reader.readexactly(2) == b"ok"
        writer.close()
        await writer.wait_closed()
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "server_hostname"),
    [
        ("untrusted_ca", "payments-service"),
        ("wrong_service", "ticket-verifier"),
        ("missing_client_certificate", "payments-service"),
    ],
)
async def test_service_mtls_rejects_invalid_trust_or_identity(tls_material, failure, server_hostname):
    server = await start_server(server_context(tls_material, "payments-service"))
    if failure == "untrusted_ca":
        context = gateway_context(tls_material, ca_name="isp-ca.pem")
    elif failure == "missing_client_certificate":
        context = ssl.create_default_context(cafile=str(tls_material / "demo-ca.pem"))
        context.minimum_version = ssl.TLSVersion.TLSv1_3
    else:
        context = gateway_context(tls_material)
    try:
        assert await connection_is_rejected(
            context,
            server.sockets[0].getsockname()[1],
            server_hostname=server_hostname,
        )
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_service_mtls_rejects_expired_certificate(tls_material, tmp_path):
    now = datetime.now(UTC)
    ca_key = serialization.load_pem_private_key((tls_material / "demo-ca-private.pem").read_bytes(), password=None)
    ca_cert = x509.load_pem_x509_certificate((tls_material / "demo-ca.pem").read_bytes())
    service_key = serialization.load_pem_private_key(
        (tls_material / "enterprise-payments-service-key.pem").read_bytes(),
        password=None,
    )
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "payments-service")])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(ca_cert.subject)
        .public_key(service_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=2))
        .not_valid_after(now - timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("payments-service")]), critical=False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=True)
        .sign(ca_key, algorithm=None)
    )
    expired_path = tmp_path / "expired-cert.pem"
    expired_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    server = await start_server(server_context(tls_material, "payments-service", certificate_path=expired_path))
    try:
        assert await connection_is_rejected(
            gateway_context(tls_material),
            server.sockets[0].getsockname()[1],
        )
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_service_mtls_never_downgrades_to_a_plaintext_endpoint(tls_material):
    server = await start_server(None)
    try:
        assert await connection_is_rejected(
            gateway_context(tls_material),
            server.sockets[0].getsockname()[1],
        )
    finally:
        server.close()
        await server.wait_closed()


def test_service_mtls_rejects_missing_ca_and_plaintext_configuration(tls_material):
    with pytest.raises(ServiceTlsError, match="unavailable"):
        create_mtls_client_context(
            url="https://opa:8181",
            ca_path=tls_material / "missing-ca.pem",
            certificate_path=tls_material / "enterprise-control-plane-client-cert.pem",
            private_key_path=tls_material / "enterprise-control-plane-client-key.pem",
        )
    with pytest.raises(ServiceTlsError, match="HTTPS"):
        create_mtls_client_context(
            url="http://opa:8181",
            ca_path=tls_material / "demo-ca.pem",
            certificate_path=tls_material / "enterprise-control-plane-client-cert.pem",
            private_key_path=tls_material / "enterprise-control-plane-client-key.pem",
        )
