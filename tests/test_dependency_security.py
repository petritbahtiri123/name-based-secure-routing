"""Advisory pin coverage and Host-independent authorization regressions.

These checks do not reproduce Envoy's crash or certify a deployed runtime.
"""
from pathlib import Path
import re

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from nbsr import ticket_verifier
from nbsr.security import SecurityError

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("manifest", ["compose.yaml", "deploy/kind/nbsr.yaml"])
def test_envoy_deployment_uses_reviewed_security_release(manifest):
    # GHSA-87ph-jqwm-pg6r; 1.37 is supported as of 2026-10-23.
    images = re.findall(r"image:\s*(envoyproxy/envoy:\S+)", (ROOT / manifest).read_text())
    assert images == ["envoyproxy/envoy:v1.37.9"]


@pytest.mark.parametrize("host", ["example.com", "example.com/api/allowed?x=", "example.com#", "example.com?"])
@pytest.mark.parametrize("path,status", [("/api/allowed", 200), ("/api/forbidden", 403)])
def test_host_cannot_replace_authorized_route_path(monkeypatch, host, path, status):
    observed = []

    def verify(token, method, actual_path, service, settings):
        observed.append((token, method, actual_path, service))
        if actual_path != "/api/allowed":
            raise SecurityError("denied")
        return {"sub": "test-subject"}

    # No signing keys or credentials: isolate the verifier's routing boundary.
    monkeypatch.setattr(ticket_verifier, "verify_ticket", verify)
    monkeypatch.setattr(ticket_verifier.app, "dependency_overrides", {
        ticket_verifier.get_settings: lambda: object(),
    })
    with TestClient(ticket_verifier.app) as client:
        response = client.get("/authorize" + path, headers={
            "host": host, "authorization": "NBSR test-placeholder",
            "x-nbsr-service": "payments.internal",
        })
    assert response.status_code == status
    assert observed == [("test-placeholder", "GET", path, "payments.internal")]

@pytest.mark.parametrize("host", [
    "example.com/api/allowed?x=", "example.com#", "example.com?", "user@example.com",
])
@pytest.mark.parametrize("server", [("127.0.0.1", 8000), None])
def test_starlette_url_preserves_scope_path_for_malformed_host(host, server):
    # Exercise the patched dependency itself, independently of NBSR routing.
    request = Request({
        "type": "http", "scheme": "http", "method": "GET",
        "path": "/api/forbidden", "query_string": b"actual=1",
        "headers": [(b"host", host.encode("ascii"))], "server": server,
    })
    assert request.url.path == "/api/forbidden"
    assert request.url.query == "actual=1"
    assert request.url.fragment == ""
    assert request.url.username is None


@pytest.mark.parametrize("host", ["example.com", "example.com:8443", "[::1]:8443"])
def test_starlette_url_preserves_valid_host_and_path(host):
    request = Request({
        "type": "http", "scheme": "https", "method": "GET",
        "path": "/api/allowed", "query_string": b"actual=1",
        "headers": [(b"host", host.encode("ascii"))], "server": ("127.0.0.1", 8000),
    })
    assert request.url.netloc == host
    assert request.url.path == "/api/allowed"
    assert request.url.query == "actual=1"

@pytest.mark.parametrize("host", ["example.com", "example.com/api/allowed?x=", "example.com#"])
@pytest.mark.parametrize("path,status", [("/api/allowed", 200), ("/api/forbidden", 403)])
def test_signed_ticket_scope_is_host_independent(monkeypatch, host, path, status):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from nbsr.config import Settings
    from nbsr.security import issue_ticket

    # Ephemeral in-memory test keys; exercise real signing and verification.
    settings = Settings.for_tests(Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate())
    token = issue_ticket(
        "spiffe://nbsr.local/workload/test", "payments.internal", "GET", "/api/allowed",
        {"policy_version": "1", "allowed_methods": ["GET"], "allowed_path_prefix": "/api/allowed", "ticket_ttl": 60},
        settings,
    )
    monkeypatch.setattr(ticket_verifier.app, "dependency_overrides", {
        ticket_verifier.get_settings: lambda: settings,
    })
    with TestClient(ticket_verifier.app) as client:
        response = client.get("/authorize" + path, headers={
            "host": host, "authorization": "NBSR " + token, "x-nbsr-service": "payments.internal",
        })
    assert response.status_code == status
