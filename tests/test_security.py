from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from nbsr.config import Settings
from nbsr.security import SecurityError, issue_ticket, validate_identity, verify_ticket


@pytest.fixture()
def keys(tmp_path):
    identity = Ed25519PrivateKey.generate()
    ticket = Ed25519PrivateKey.generate()
    return identity, ticket


@pytest.fixture()
def settings(keys):
    identity, ticket = keys
    return Settings.for_tests(identity, ticket)


def identity_token(key, *, iss="https://identity.nbsr.local", aud="nbsr-control-plane", exp_delta=60, alg="EdDSA"):
    now = datetime.now(UTC)
    claims = {
        "iss": iss,
        "sub": "spiffe://nbsr.local/workload/client-allowed",
        "aud": aud,
        "iat": now,
        "exp": now + timedelta(seconds=exp_delta),
        "jti": "identity-1",
    }
    return jwt.encode(claims, key, algorithm=alg)


def test_identity_validation_success(settings, keys):
    assert validate_identity(identity_token(keys[0]), settings).endswith("client-allowed")


@pytest.mark.parametrize("changes", [{"iss": "wrong"}, {"aud": "wrong"}, {"exp_delta": -1}])
def test_identity_rejects_invalid_standard_claims(settings, keys, changes):
    with pytest.raises(SecurityError):
        validate_identity(identity_token(keys[0], **changes), settings)


def test_identity_rejects_unexpected_algorithm(settings):
    token = jwt.encode({"sub": "x"}, "not-the-ed25519-key-material-12345", algorithm="HS256")
    with pytest.raises(SecurityError):
        validate_identity(token, settings)


def test_identity_rejects_unsigned_token(settings):
    token = jwt.encode({"sub": "spiffe://nbsr.local/workload/client-allowed"}, key="", algorithm="none")
    with pytest.raises(SecurityError):
        validate_identity(token, settings)


def test_ticket_round_trip_and_scope(settings):
    token = issue_ticket(
        "spiffe://nbsr.local/workload/client-allowed",
        "payments.internal", "GET", "/api/payment-status",
        {"policy_version": "1", "allowed_methods": ["GET"], "allowed_path_prefix": "/api/payment-status", "ticket_ttl": 60},
        settings,
    )
    claims = verify_ticket(token, "GET", "/api/payment-status", "payments.internal", settings)
    assert claims["sub"].endswith("client-allowed")


@pytest.mark.parametrize(
    ("method", "path", "service"),
    [("POST", "/api/payment-status", "payments.internal"), ("GET", "/api/payments", "payments.internal"), ("GET", "/api/payment-status", "admin.internal")],
)
def test_ticket_rejects_scope_escalation(settings, method, path, service):
    token = issue_ticket("spiffe://nbsr.local/workload/client-allowed", "payments.internal", "GET", "/api/payment-status", {"policy_version": "1", "allowed_methods": ["GET"], "allowed_path_prefix": "/api/payment-status", "ticket_ttl": 60}, settings)
    with pytest.raises(SecurityError):
        verify_ticket(token, method, path, service, settings)


def test_ticket_rejects_tampering(settings):
    token = issue_ticket("spiffe://nbsr.local/workload/client-allowed", "payments.internal", "GET", "/api/payment-status", {"policy_version": "1", "allowed_methods": ["GET"], "allowed_path_prefix": "/api/payment-status", "ticket_ttl": 60}, settings)
    head, payload, signature = token.split(".")
    signature = ("A" if signature[0] != "A" else "B") + signature[1:]
    tampered = ".".join((head, payload, signature))
    with pytest.raises(SecurityError):
        verify_ticket(tampered, "GET", "/api/payment-status", "payments.internal", settings)


def test_ticket_rejects_expired(settings):
    settings.ticket_ttl_seconds = -1
    token = issue_ticket("spiffe://nbsr.local/workload/client-allowed", "payments.internal", "GET", "/api/payment-status", {"policy_version": "1", "allowed_methods": ["GET"], "allowed_path_prefix": "/api/payment-status", "ticket_ttl": -1}, settings)
    with pytest.raises(SecurityError):
        verify_ticket(token, "GET", "/api/payment-status", "payments.internal", settings)


def test_ticket_rejects_wrong_audience(settings):
    token = issue_ticket("spiffe://nbsr.local/workload/client-allowed", "payments.internal", "GET", "/api/payment-status", {"policy_version": "1", "allowed_methods": ["GET"], "allowed_path_prefix": "/api/payment-status", "ticket_ttl": 60}, settings)
    settings.ticket_audience = "another-gateway"
    with pytest.raises(SecurityError):
        verify_ticket(token, "GET", "/api/payment-status", "payments.internal", settings)
