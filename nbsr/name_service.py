from __future__ import annotations

from pydantic import BaseModel

from nbsr.config import Settings
from nbsr.name_model import normalize_hostname
from nbsr.name_security import issue_name_binding, validate_client_session_public_key
from nbsr.synthetic import SyntheticAddressPool


class NameRouteResponse(BaseModel):
    hostname: str
    synthetic_ipv4: str
    synthetic_ipv6: str
    gateway_id: str
    route_binding: str
    expires_in: int


class NameRouteService:
    def __init__(self, *, pool: SyntheticAddressPool, settings: Settings):
        self._pool = pool
        self._settings = settings

    def resolve(self, hostname: str, session_public_key: str) -> NameRouteResponse:
        hostname = normalize_hostname(hostname)
        validate_client_session_public_key(session_public_key)
        mapping = self._pool.allocate(
            hostname,
            minimum_valid_for_seconds=self._settings.name_binding_ttl_seconds,
        )
        route_binding = issue_name_binding(
            hostname=hostname,
            synthetic_ipv4=mapping.ipv4,
            synthetic_ipv6=mapping.ipv6,
            gateway_id=self._settings.name_binding_gateway_id,
            session_public_key=session_public_key,
            settings=self._settings,
        )
        return NameRouteResponse(
            hostname=hostname,
            synthetic_ipv4=mapping.ipv4,
            synthetic_ipv6=mapping.ipv6,
            gateway_id=self._settings.name_binding_gateway_id,
            route_binding=route_binding,
            expires_in=self._settings.name_binding_ttl_seconds,
        )
