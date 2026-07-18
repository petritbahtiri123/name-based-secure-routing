from datetime import UTC, datetime, timedelta

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from nbsr.config import Settings
from nbsr.control_plane import app, get_settings


class FakeResponse:
    def __init__(self, allow: bool):
        self.allow = allow

    def raise_for_status(self):
        return None

    def json(self):
        return {"result": {"allow": self.allow, "reason": "test", "policy_version": "1", "allowed_methods": ["GET"], "allowed_path_prefix": "/api/payment-status", "ticket_ttl": 60}}


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
    token = jwt.encode({"iss": settings.identity_issuer, "sub": "spiffe://nbsr.local/workload/client-allowed", "aud": settings.identity_audience, "iat": now, "exp": now + timedelta(seconds=60), "jti": "test"}, identity, algorithm="EdDSA")
    return TestClient(app), token


def test_authorized_resolution_does_not_disclose_backend(monkeypatch):
    client, token = setup(monkeypatch)
    response = client.post("/v1/routes/resolve", headers={"Authorization": f"Bearer {token}"}, json={"service": "payments.internal", "method": "GET", "path": "/api/payment-status"})
    assert response.status_code == 200
    assert set(response.json()) == {"service", "gateway_url", "routing_ticket", "expires_in"}


def test_policy_denial_returns_403(monkeypatch):
    client, token = setup(monkeypatch, allow=False)
    response = client.post("/v1/routes/resolve", headers={"Authorization": f"Bearer {token}"}, json={"service": "payments.internal", "method": "GET", "path": "/api/payment-status"})
    assert response.status_code == 403
