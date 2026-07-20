import base64

import jwt
import pytest

from nbsr.config import Settings
from nbsr.name_security import (
    ClientSession,
    issue_name_binding,
    sign_relay_proof,
    verify_name_binding,
    verify_relay_proof,
)
from nbsr.security import SecurityError


@pytest.fixture()
def settings():
    return Settings.for_tests(
        ClientSession.generate().private_key,
        ClientSession.generate().private_key,
        ClientSession.generate().private_key,
    )


def issue_binding(settings: Settings, session: ClientSession | None = None) -> tuple[str, ClientSession]:
    session = session or ClientSession.generate()
    return (
        issue_name_binding(
            hostname="facebook.test",
            synthetic_ipv4="127.80.0.1",
            synthetic_ipv6="fd00:6e62:7372::1",
            gateway_id="edge-local",
            session_public_key=session.public_key_b64,
            settings=settings,
        ),
        session,
    )


def test_binding_round_trip_requires_client_proof(settings):
    token, session = issue_binding(settings)

    claims = verify_name_binding(token, "facebook.test", "127.80.0.1", 443, "edge-local", settings)
    nonce = "relay-nonce"
    proof = sign_relay_proof(session, claims["jti"], nonce, 443)

    verify_relay_proof(claims, claims["jti"], nonce, 443, proof)


@pytest.mark.parametrize("port", [22, 53, 853, 8443])
def test_binding_rejects_unapproved_port(settings, port):
    token, _ = issue_binding(settings)

    with pytest.raises(SecurityError):
        verify_name_binding(token, "facebook.test", "127.80.0.1", port, "edge-local", settings)


def test_binding_rejects_tampering(settings):
    token, _ = issue_binding(settings)
    header, payload, signature = token.split(".")
    signature = ("A" if signature[0] != "A" else "B") + signature[1:]

    with pytest.raises(SecurityError):
        verify_name_binding(".".join((header, payload, signature)), "facebook.test", "127.80.0.1", 443, "edge-local", settings)


def test_binding_rejects_expiry(settings):
    settings.name_binding_ttl_seconds = -1
    token, _ = issue_binding(settings)

    with pytest.raises(SecurityError):
        verify_name_binding(token, "facebook.test", "127.80.0.1", 443, "edge-local", settings)


@pytest.mark.parametrize(
    ("hostname", "synthetic_address", "gateway_id"),
    [
        ("other.test", "127.80.0.1", "edge-local"),
        ("facebook.test", "127.80.0.2", "edge-local"),
        ("facebook.test", "127.80.0.1", "other-gateway"),
    ],
)
def test_binding_rejects_wrong_route_scope(settings, hostname, synthetic_address, gateway_id):
    token, _ = issue_binding(settings)

    with pytest.raises(SecurityError):
        verify_name_binding(token, hostname, synthetic_address, 443, gateway_id, settings)


def test_binding_uses_urlsafe_raw_session_key_in_confirmation_claim(settings):
    token, session = issue_binding(settings)
    claims = jwt.decode(token, options={"verify_signature": False})

    assert claims["cnf"]["ed25519_public_key"] == session.public_key_b64
    assert base64.urlsafe_b64decode(session.public_key_b64 + "==") == session.public_key_bytes


def test_relay_proof_rejects_wrong_session_key(settings):
    token, _ = issue_binding(settings)
    claims = verify_name_binding(token, "facebook.test", "127.80.0.1", 443, "edge-local", settings)
    proof = sign_relay_proof(ClientSession.generate(), claims["jti"], "relay-nonce", 443)

    with pytest.raises(SecurityError):
        verify_relay_proof(claims, claims["jti"], "relay-nonce", 443, proof)


def test_relay_proof_rejects_modified_nonce(settings):
    token, session = issue_binding(settings)
    claims = verify_name_binding(token, "facebook.test", "127.80.0.1", 443, "edge-local", settings)
    proof = sign_relay_proof(session, claims["jti"], "relay-nonce", 443)

    with pytest.raises(SecurityError):
        verify_relay_proof(claims, claims["jti"], "modified-nonce", 443, proof)
