from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network, ip_address
from collections.abc import Sequence
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
_CAPABILITY_PORTS = {"http": 80, "tcp:80": 80, "https": 443, "tcp:443": 443}
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


def validate_client_session_public_key(value: object) -> None:
    _session_public_key(value)


def client_session_thumbprint(value: object) -> str:
    public_key = _session_public_key(value)
    raw = public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return _b64encode(hashlib.sha256(raw).digest())


def validate_name_binding_private_key(settings: Settings) -> None:
    try:
        key = serialization.load_pem_private_key(settings.key_bytes("name_binding_private_key"), password=None)
    except (ValueError, TypeError, RuntimeError) as exc:
        raise RuntimeError("Required name binding private key is invalid") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise RuntimeError("Required name binding private key is not Ed25519")


def validate_name_binding_public_key(settings: Settings) -> None:
    try:
        key = serialization.load_pem_public_key(settings.key_bytes("name_binding_public_key"))
    except (ValueError, TypeError, RuntimeError) as exc:
        raise RuntimeError("Required name binding public key is invalid") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise RuntimeError("Required name binding public key is not Ed25519")


def capability_ports(capabilities: Sequence[str]) -> tuple[int, ...]:
    if isinstance(capabilities, (str, bytes)) or not capabilities:
        raise SecurityError("Invalid route capabilities")
    ports: set[int] = set()
    for capability in capabilities:
        if not isinstance(capability, str):
            raise SecurityError("Invalid route capabilities")
        port = _CAPABILITY_PORTS.get(capability.strip().lower())
        if port is None:
            raise SecurityError("Invalid route capabilities")
        ports.add(port)
    return tuple(sorted(ports))


def _binding_ports(value: object) -> tuple[int, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise SecurityError("Invalid route binding")
    if any(type(port) is not int or port not in _ALLOWED_PORTS for port in value):
        raise SecurityError("Invalid route binding")
    ports = tuple(sorted(set(value)))
    if len(ports) != len(value):
        raise SecurityError("Invalid route binding")
    return ports


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
    if not isinstance(route_id, str) or not route_id or not isinstance(nonce, str) or not nonce or type(port) is not int:
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
    ports: Sequence[int] = (80, 443),
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
    bound_ports = _binding_ports(ports)

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
        "ports": list(bound_ports),
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
    try:
        bound_ports = _binding_ports(claims.get("ports"))
    except SecurityError as exc:
        raise SecurityError("Invalid name route binding") from exc
    if (
        claims.get("hostname") != requested_hostname
        or requested_address not in (claims.get("synthetic_ipv4"), claims.get("synthetic_ipv6"))
        or claims.get("gateway_id") != gateway_id
        or gateway_id != settings.name_binding_gateway_id
        or type(port) is not int
        or port not in bound_ports
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
    try:
        bound_ports = _binding_ports(claims.get("ports"))
    except SecurityError as exc:
        raise SecurityError("Invalid relay proof") from exc
    if (
        claims.get("jti") != route_id
        or type(port) is not int
        or port not in bound_ports
        or port not in _ALLOWED_PORTS
    ):
        raise SecurityError("Invalid relay proof")
    try:
        public_key = _session_public_key(claims["cnf"]["ed25519_public_key"])
        public_key.verify(_b64decode(proof), _binding_message(route_id, nonce, port))
    except (KeyError, TypeError, InvalidSignature, SecurityError) as exc:
        raise SecurityError("Invalid relay proof") from exc
