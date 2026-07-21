from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from nbsr.config import Settings
from nbsr.control_plane import app, get_settings
from nbsr.name_control import app as name_app
from nbsr.name_control import get_name_route_service, get_settings as get_name_settings
from nbsr.name_security import ClientSession
from nbsr.name_service import NameRouteService
from nbsr.synthetic import SyntheticAddressPool


class FakeResponse:
    def __init__(self, allow: bool):
        self.allow = allow

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "result": {
                "allow": self.allow,
                "reason": "test",
                "policy_version": "1",
                "allowed_methods": ["GET"],
                "allowed_path_prefix": "/api/payment-status",
                "ticket_ttl": 60,
            }
        }


class FakeAsyncClient:
    allow = True

    def __init__(self, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, *_args, **_kwargs):
        return FakeResponse(self.allow)


def setup(monkeypatch, allow=True):
    identity = Ed25519PrivateKey.generate()
    settings = Settings.for_tests(identity, Ed25519PrivateKey.generate())
    app.dependency_overrides[get_settings] = lambda: settings
    FakeAsyncClient.allow = allow
    monkeypatch.setattr("nbsr.control_plane.httpx.AsyncClient", FakeAsyncClient)
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "iss": settings.identity_issuer,
            "sub": "spiffe://nbsr.local/workload/client-allowed",
            "aud": settings.identity_audience,
            "iat": now,
            "exp": now + timedelta(seconds=60),
            "jti": "test",
        },
        identity,
        algorithm="EdDSA",
    )
    return TestClient(app), token


def setup_name_control():
    settings = Settings.for_tests(
        ClientSession.generate().private_key,
        ClientSession.generate().private_key,
        ClientSession.generate().private_key,
    )
    name_app.dependency_overrides[get_name_settings] = lambda: settings
    return TestClient(name_app)


def test_authorized_resolution_does_not_disclose_backend(monkeypatch):
    client, token = setup(monkeypatch)
    response = client.post(
        "/v1/routes/resolve",
        headers={"Authorization": f"Bearer {token}"},
        json={"service": "payments.internal", "method": "GET", "path": "/api/payment-status"},
    )
    assert response.status_code == 200
    assert set(response.json()) == {"service", "gateway_url", "routing_ticket", "expires_in"}


def test_policy_denial_returns_403(monkeypatch):
    client, token = setup(monkeypatch, allow=False)
    response = client.post(
        "/v1/routes/resolve",
        headers={"Authorization": f"Bearer {token}"},
        json={"service": "payments.internal", "method": "GET", "path": "/api/payment-status"},
    )
    assert response.status_code == 403


def test_isp_route_does_not_require_authorization_header(monkeypatch):
    client = setup_name_control()

    response = client.post(
        "/v1/name-routes/resolve",
        json={
            "protocol_version": 1,
            "request_id": "request-1",
            "hostname": "facebook.test",
            "transport": "tcp",
            "client_nonce": "client-nonce",
            "client_public_key": ClientSession.generate().public_key_b64,
            "capabilities": ["http", "https"],
        },
    )

    assert response.status_code == 200
    assert set(response.json()) == {
        "protocol_version",
        "request_id",
        "hostname",
        "synthetic_ipv4",
        "synthetic_ipv6",
        "gateway_id",
        "route_binding",
        "expires_in",
    }


def test_name_control_health_fails_when_binding_signing_key_is_invalid(monkeypatch):
    settings = Settings.for_tests(
        ClientSession.generate().private_key,
        ClientSession.generate().private_key,
        ClientSession.generate().private_key,
    )
    settings.name_binding_private_key_pem = b"invalid"
    monkeypatch.setitem(name_app.dependency_overrides, get_name_settings, lambda: settings)
    client = TestClient(name_app, raise_server_exceptions=False)

    assert client.get("/health").status_code == 500


def test_legacy_cleartext_control_plane_does_not_expose_isp_name_routes(monkeypatch):
    client, _ = setup(monkeypatch)
    response = client.post(
        "/v1/name-routes/resolve",
        json={
            "protocol_version": 1,
            "request_id": "request-1",
            "hostname": "facebook.test",
            "transport": "tcp",
            "client_nonce": "client-nonce",
            "client_public_key": ClientSession.generate().public_key_b64,
            "capabilities": ["http", "https"],
        },
    )
    assert response.status_code == 404


@pytest.mark.parametrize(
    "field,value",
    [
        ("protocol_version", 2),
        ("protocol_version", True),
        ("transport", "udp"),
        ("request_id", ""),
        ("client_nonce", ""),
        ("client_public_key", "invalid"),
        ("capabilities", ["http", ""]),
    ],
)
def test_name_route_rejects_invalid_requests(monkeypatch, field, value):
    client = setup_name_control()
    payload = {
        "protocol_version": 1,
        "request_id": "request-1",
        "hostname": "facebook.test",
        "transport": "tcp",
        "client_nonce": "client-nonce",
        "client_public_key": ClientSession.generate().public_key_b64,
        "capabilities": ["http", "https"],
    }
    payload[field] = value

    response = client.post("/v1/name-routes/resolve", json=payload)

    assert response.status_code == 422


def test_name_route_pool_exhaustion_returns_retryable_503(monkeypatch):
    settings = Settings.for_tests(
        ClientSession.generate().private_key,
        ClientSession.generate().private_key,
        ClientSession.generate().private_key,
    )
    service = NameRouteService(
        pool=SyntheticAddressPool("127.80.0.0/30", "fd00:6e62:7372::/126", ttl_seconds=60),
        settings=settings,
    )
    monkeypatch.setitem(name_app.dependency_overrides, get_name_route_service, lambda: service)
    client = TestClient(name_app, raise_server_exceptions=False)
    payload = {
        "protocol_version": 1,
        "request_id": "request-1",
        "transport": "tcp",
        "client_nonce": "client-nonce",
        "client_public_key": ClientSession.generate().public_key_b64,
        "capabilities": ["http", "https"],
    }

    for hostname in ("one.test", "two.test"):
        response = client.post("/v1/name-routes/resolve", json={**payload, "hostname": hostname})
        assert response.status_code == 200

    response = client.post("/v1/name-routes/resolve", json={**payload, "hostname": "three.test"})

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "60"
