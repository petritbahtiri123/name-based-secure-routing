from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from nbsr.config import Settings
from nbsr.security import issue_ticket
from nbsr.ticket_verifier import app, get_settings


def configured_client():
    settings = Settings.for_tests(Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate())
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app), settings


def test_verifier_accepts_valid_ticket():
    client, settings = configured_client()
    ticket = issue_ticket("spiffe://nbsr.local/workload/client-allowed", "payments.internal", "GET", "/api/payment-status", {"policy_version": "1", "allowed_methods": ["GET"], "allowed_path_prefix": "/api/payment-status", "ticket_ttl": 60}, settings)
    response = client.get("/authorize", headers={"Authorization": f"NBSR {ticket}", "x-nbsr-method": "GET", "x-nbsr-path": "/api/payment-status", "x-nbsr-service": "payments.internal"})
    assert response.status_code == 200


def test_verifier_rejects_missing_ticket():
    client, _ = configured_client()
    assert client.get("/authorize").status_code == 401


def test_verifier_rejects_method_escalation():
    client, settings = configured_client()
    ticket = issue_ticket("spiffe://nbsr.local/workload/client-allowed", "payments.internal", "GET", "/api/payment-status", {"policy_version": "1", "allowed_methods": ["GET"], "allowed_path_prefix": "/api/payment-status", "ticket_ttl": 60}, settings)
    response = client.get("/authorize", headers={"Authorization": f"NBSR {ticket}", "x-nbsr-method": "POST", "x-nbsr-path": "/api/payments"})
    assert response.status_code == 403
