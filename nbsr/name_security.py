from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network, ip_address
from typing import Any
from uuid import uuid4

import jwt
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from nbsr.config import Settings
from nbsr.name_model import normalize_hostname
from nbsr.security import SecurityError


_LOOPBACK_IPV4 = IPv4Network("127.0.0.0/8")
_NBSR_SYNTHETIC_ULA = IPv6Network("fd00:6e62:7372::/48")
_ALLOWED_PORTS = frozenset((80, 443))
_REQUIRED_BINDING_CLAIMS = (
    "iss",
    "aud",
    "iat",
    "nbf",
    "exp",
    "jti",
    "hostname",
    "synthetic_ipv4",
    "synthetic_ipv6",
    "gateway_id",
    "ports",
    "cnf",
)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: object) -> bytes:
    if not isinstance(value, str) or not value:
        raise SecurityError("Invalid client session key")
    try:
        decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except ValueError as exc:
        raise SecurityError("Invalid client session key") from exc
    if _b64encode(decoded) != value:
        raise SecurityError("Invalid client session key")
    return decoded


def _session_public_key(value: object) -> Ed25519PublicKey:
    try:
        return Ed25519PublicKey.from_public_bytes(_b64decode(value))
    except ValueError as exc:
        raise SecurityError("Invalid client session key") from exc


def _synthetic_address(value: str) -> str:
    try:
        parsed = ip_address(value)
    except ValueError as exc:
        raise SecurityError("Invalid synthetic address") from exc
    if isinstance(parsed, IPv4Address) and parsed in _LOOPBACK_IPV4:
        return str(parsed)
    if isinstance(parsed, IPv6Address) and parsed in _NBSR_SYNTHETIC_ULA:
        return str(parsed)
    raise SecurityError("Invalid synthetic address")


def _binding_message(route_id: str, nonce: str, port: int) -> bytes:
    if not isinstance(route_id, str) or not route_id or not isinstance(nonce, str) or not nonce or not isinstance(port, int):
        raise SecurityError("Invalid relay proof")
    return f"{route_id}\n{nonce}\n{port}".encode("utf-8")


@dataclass(frozen=True)
class ClientSession:
    private_key: Ed25519PrivateKey

    @classmethod
    def generate(cls) -> "ClientSession":
        return cls(Ed25519PrivateKey.generate())

    @property
    def public_key_bytes(self) -> bytes:
        return self.private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)

    @property
    def public_key_b64(self) -> str:
        return _b64encode(self.public_key_bytes)


def issue_name_binding(
    *,
    hostname: str,
    synthetic_ipv4: str,
    synthetic_ipv6: str,
    gateway_id: str,
    session_public_key: str,
    settings: Settings,
) -> str:
    try:
        hostname = normalize_hostname(hostname)
    except ValueError as exc:
        raise SecurityError("Invalid route binding") from exc
    if _synthetic_address(synthetic_ipv4) != synthetic_ipv4 or _synthetic_address(synthetic_ipv6) != synthetic_ipv6:
        raise SecurityError("Invalid route binding")
    if not isinstance(ip_address(synthetic_ipv4), IPv4Address) or not isinstance(ip_address(synthetic_ipv6), IPv6Address):
        raise SecurityError("Invalid route binding")
    _session_public_key(session_public_key)
    if gateway_id != settings.name_binding_gateway_id:
        raise SecurityError("Invalid route binding")

    now = datetime.now(UTC)
    claims = {
        "iss": settings.name_binding_issuer,
        "aud": settings.name_binding_audience,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(seconds=settings.name_binding_ttl_seconds),
        "jti": str(uuid4()),
        "hostname": hostname,
        "synthetic_ipv4": synthetic_ipv4,
        "synthetic_ipv6": synthetic_ipv6,
        "gateway_id": gateway_id,
        "ports": sorted(_ALLOWED_PORTS),
        "cnf": {"ed25519_public_key": session_public_key},
    }
    return jwt.encode(claims, settings.key_bytes("name_binding_private_key"), algorithm="EdDSA")


def verify_name_binding(
    token: str,
    hostname: str,
    synthetic_address: str,
    port: int,
    gateway_id: str,
    settings: Settings,
) -> dict[str, Any]:
    try:
        claims = jwt.decode(
            token,
            settings.key_bytes("name_binding_public_key"),
            algorithms=["EdDSA"],
            issuer=settings.name_binding_issuer,
            audience=settings.name_binding_audience,
            options={"require": list(_REQUIRED_BINDING_CLAIMS)},
        )
        requested_hostname = normalize_hostname(hostname)
        requested_address = _synthetic_address(synthetic_address)
    except (jwt.PyJWTError, ValueError, SecurityError) as exc:
        raise SecurityError("Invalid name route binding") from exc
    if (
        claims.get("hostname") != requested_hostname
        or requested_address not in (claims.get("synthetic_ipv4"), claims.get("synthetic_ipv6"))
        or claims.get("gateway_id") != gateway_id
        or gateway_id != settings.name_binding_gateway_id
        or port not in claims.get("ports", [])
        or port not in _ALLOWED_PORTS
    ):
        raise SecurityError("Invalid name route binding")
    try:
        _session_public_key(claims["cnf"]["ed25519_public_key"])
    except (KeyError, TypeError, SecurityError) as exc:
        raise SecurityError("Invalid name route binding") from exc
    return claims


def sign_relay_proof(session: ClientSession, route_id: str, nonce: str, port: int) -> str:
    try:
        return _b64encode(session.private_key.sign(_binding_message(route_id, nonce, port)))
    except (AttributeError, SecurityError) as exc:
        raise SecurityError("Invalid relay proof") from exc


def verify_relay_proof(claims: dict[str, Any], route_id: str, nonce: str, port: int, proof: str) -> None:
    if claims.get("jti") != route_id:
        raise SecurityError("Invalid relay proof")
    try:
        public_key = _session_public_key(claims["cnf"]["ed25519_public_key"])
        public_key.verify(_b64decode(proof), _binding_message(route_id, nonce, port))
    except (KeyError, TypeError, InvalidSignature, SecurityError) as exc:
        raise SecurityError("Invalid relay proof") from exc
