from pathlib import Path

import pytest

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
    ticket = issue_ticket(
        "spiffe://nbsr.local/workload/client-allowed",
        "payments.internal",
        "GET",
        "/api/payment-status",
        {"policy_version": "1", "allowed_methods": ["GET"], "allowed_path_prefix": "/api/payment-status", "ticket_ttl": 60},
        settings,
    )
    response = client.get(
        "/authorize/api/payment-status",
        headers={"Authorization": f"NBSR {ticket}", "x-nbsr-service": "payments.internal"},
    )
    assert response.status_code == 200


def test_verifier_rejects_missing_ticket():
    client, _ = configured_client()
    assert client.get("/authorize").status_code == 401


def test_verifier_uses_actual_method_and_path_instead_of_spoofable_headers():
    client, settings = configured_client()
    ticket = issue_ticket(
        "spiffe://nbsr.local/workload/client-allowed",
        "payments.internal",
        "GET",
        "/api/payment-status",
        {"policy_version": "1", "allowed_methods": ["GET"], "allowed_path_prefix": "/api/payment-status", "ticket_ttl": 60},
        settings,
    )
    response = client.post(
        "/authorize/api/payments",
        headers={
            "Authorization": f"NBSR {ticket}",
            "x-nbsr-method": "GET",
            "x-nbsr-path": "/api/payment-status",
            "x-nbsr-service": "payments.internal",
        },
    )
    assert response.status_code == 403


def test_verifier_rejects_missing_trusted_service_metadata():
    client, settings = configured_client()
    ticket = issue_ticket(
        "spiffe://nbsr.local/workload/client-allowed",
        "payments.internal",
        "GET",
        "/api/payment-status",
        {
            "policy_version": "1",
            "allowed_methods": ["GET"],
            "allowed_path_prefix": "/api/payment-status",
            "ticket_ttl": 60,
        },
        settings,
    )

    response = client.get("/authorize/api/payment-status", headers={"Authorization": f"NBSR {ticket}"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Trusted routing metadata required"


def test_verifier_rejects_duplicate_trusted_service_metadata():
    client, settings = configured_client()
    ticket = issue_ticket(
        "spiffe://nbsr.local/workload/client-allowed",
        "payments.internal",
        "GET",
        "/api/payment-status",
        {
            "policy_version": "1",
            "allowed_methods": ["GET"],
            "allowed_path_prefix": "/api/payment-status",
            "ticket_ttl": 60,
        },
        settings,
    )
    headers = [
        ("Authorization", f"NBSR {ticket}"),
        ("x-nbsr-service", "payments.internal"),
        ("x-nbsr-service", "admin.internal"),
    ]

    response = client.get("/authorize/api/payment-status", headers=headers)

    assert response.status_code == 400
    assert response.json()["detail"] == "Trusted routing metadata required"


def test_envoy_derives_service_only_inside_ext_authz_request():
    config = (Path(__file__).parents[1] / "gateway" / "envoy.yaml").read_text(encoding="utf-8")

    assert "request_headers_to_add:" not in config
    assert "headers_to_add:" in config
    assert "key: x-nbsr-service" in config
    assert "key: x-nbsr-method" not in config
    assert "key: x-nbsr-path" not in config


@pytest.mark.parametrize("methods", ["GET", "TARGET", {"GET": True}, 7, True, ["GET", 7]])
def test_verifier_rejects_malformed_methods_with_403(methods):
    client, settings = configured_client()
    try:
        ticket = issue_ticket(
            "spiffe://nbsr.local/workload/client-allowed", "payments.internal", "GET", "/api",
            {"policy_version": "1", "allowed_methods": methods, "allowed_path_prefix": "/api", "ticket_ttl": 60},
            settings,
        )
        response = client.get(
            "/authorize/api",
            headers={"Authorization": f"NBSR {ticket}", "x-nbsr-service": "payments.internal"},
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Invalid routing authorization"
    finally:
        app.dependency_overrides.pop(get_settings, None)
        client.close()
