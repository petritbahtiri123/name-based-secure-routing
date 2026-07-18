from __future__ import annotations

from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NBSR_", extra="ignore")

    identity_issuer: str = "https://identity.nbsr.local"
    identity_audience: str = "nbsr-control-plane"
    ticket_issuer: str = "https://control.nbsr.local"
    ticket_audience: str = "nbsr-gateway"
    gateway_url: str = "http://localhost:8080"
    opa_url: str = "http://opa:8181/v1/data/nbsr/route/decision"
    ticket_ttl_seconds: int = Field(60, ge=-1, le=300)
    identity_public_key_path: Path = Path("/run/secrets/identity-public.pem")
    ticket_private_key_path: Path = Path("/run/secrets/ticket-private.pem")
    ticket_public_key_path: Path = Path("/run/secrets/ticket-public.pem")
    identity_public_key_pem: bytes | None = None
    ticket_private_key_pem: bytes | None = None
    ticket_public_key_pem: bytes | None = None

    @classmethod
    def for_tests(cls, identity: Ed25519PrivateKey, ticket: Ed25519PrivateKey) -> "Settings":
        private_format = serialization.PrivateFormat.PKCS8
        public_format = serialization.PublicFormat.SubjectPublicKeyInfo
        return cls(
            identity_public_key_pem=identity.public_key().public_bytes(serialization.Encoding.PEM, public_format),
            ticket_private_key_pem=ticket.private_bytes(serialization.Encoding.PEM, private_format, serialization.NoEncryption()),
            ticket_public_key_pem=ticket.public_key().public_bytes(serialization.Encoding.PEM, public_format),
        )

    def key_bytes(self, kind: str) -> bytes:
        inline = getattr(self, f"{kind}_pem")
        if inline:
            return inline
        path = getattr(self, f"{kind}_path")
        try:
            return path.read_bytes()
        except OSError as exc:
            raise RuntimeError(f"Required {kind.replace('_', ' ')} is unavailable") from exc
