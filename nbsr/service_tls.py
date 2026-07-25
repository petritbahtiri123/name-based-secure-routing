from __future__ import annotations

import ssl
from pathlib import Path
from urllib.parse import urlparse


class ServiceTlsError(RuntimeError):
    """Required service-to-service TLS identity is missing or invalid."""


def create_mtls_client_context(
    *,
    url: str,
    ca_path: Path | str,
    certificate_path: Path | str,
    private_key_path: Path | str,
) -> ssl.SSLContext:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ServiceTlsError("service endpoint must use HTTPS with a hostname")
    try:
        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(ca_path))
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_cert_chain(str(certificate_path), str(private_key_path))
    except (OSError, ssl.SSLError) as exc:
        raise ServiceTlsError("required service TLS identity is unavailable or invalid") from exc
    return context
