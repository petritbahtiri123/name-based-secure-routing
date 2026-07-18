from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt

from nbsr.config import Settings

SUBJECT_PREFIX = "spiffe://nbsr.local/workload/"
REQUIRED_TICKET_CLAIMS = ("iss", "sub", "aud", "iat", "nbf", "exp", "jti", "service", "methods", "path_prefix", "policy_version")


class SecurityError(ValueError):
    pass


def _valid_subject(subject: object) -> bool:
    return isinstance(subject, str) and subject.startswith(SUBJECT_PREFIX) and len(subject) > len(SUBJECT_PREFIX)


def validate_identity(token: str, settings: Settings) -> str:
    try:
        claims = jwt.decode(
            token,
            settings.key_bytes("identity_public_key"),
            algorithms=["EdDSA"],
            issuer=settings.identity_issuer,
            audience=settings.identity_audience,
            options={"require": ["iss", "sub", "aud", "iat", "exp", "jti"]},
        )
    except jwt.PyJWTError as exc:
        raise SecurityError("Invalid workload identity") from exc
    subject = claims.get("sub")
    if not _valid_subject(subject):
        raise SecurityError("Invalid workload identity")
    return subject


def issue_ticket(subject: str, service: str, method: str, path: str, decision: dict[str, Any], settings: Settings) -> str:
    if not _valid_subject(subject):
        raise SecurityError("Invalid subject")
    now = datetime.now(UTC)
    ttl = min(int(decision.get("ticket_ttl", settings.ticket_ttl_seconds)), settings.ticket_ttl_seconds)
    claims = {
        "iss": settings.ticket_issuer,
        "sub": subject,
        "aud": settings.ticket_audience,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(seconds=ttl),
        "jti": str(uuid4()),
        "service": service,
        "methods": decision["allowed_methods"],
        "path_prefix": decision["allowed_path_prefix"],
        "policy_version": decision["policy_version"],
    }
    return jwt.encode(claims, settings.key_bytes("ticket_private_key"), algorithm="EdDSA")


def verify_ticket(token: str, method: str, path: str, service: str, settings: Settings) -> dict[str, Any]:
    try:
        claims = jwt.decode(
            token,
            settings.key_bytes("ticket_public_key"),
            algorithms=["EdDSA"],
            issuer=settings.ticket_issuer,
            audience=settings.ticket_audience,
            options={"require": list(REQUIRED_TICKET_CLAIMS)},
        )
    except jwt.PyJWTError as exc:
        raise SecurityError("Invalid routing authorization") from exc
    if not _valid_subject(claims.get("sub")):
        raise SecurityError("Invalid routing authorization")
    if claims.get("service") != service or method.upper() not in claims.get("methods", []):
        raise SecurityError("Invalid routing authorization")
    prefix = claims.get("path_prefix")
    if not isinstance(prefix, str) or not path.startswith(prefix):
        raise SecurityError("Invalid routing authorization")
    return claims
