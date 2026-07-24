from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from nbsr.admission import AdmissionLimiter
from nbsr.config import Settings
from nbsr.name_model import normalize_hostname
from nbsr.name_security import capability_ports, client_session_thumbprint, issue_name_binding
from nbsr.synthetic import SyntheticAddressPool


class NameRouteResponse(BaseModel):
    hostname: str
    synthetic_ipv4: str
    synthetic_ipv6: str
    gateway_id: str
    route_binding: str
    expires_in: int


class NameRouteService:
    def __init__(
        self,
        *,
        pool: SyntheticAddressPool,
        settings: Settings,
        admission_limiter: AdmissionLimiter | None = None,
    ):
        self._pool = pool
        self._settings = settings
        self._admission_limiter = admission_limiter or AdmissionLimiter(
            global_limit=settings.name_route_global_requests_per_minute,
            client_limit=settings.name_route_client_requests_per_minute,
            max_clients=settings.name_route_admission_max_clients,
        )

    def resolve(
        self,
        hostname: str,
        session_public_key: str,
        capabilities: Sequence[str] = ("http", "https"),
    ) -> NameRouteResponse:
        hostname = normalize_hostname(hostname)
        client_id = client_session_thumbprint(session_public_key)
        ports = capability_ports(capabilities)
        self._admission_limiter.consume(client_id)
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
            ports=ports,
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
