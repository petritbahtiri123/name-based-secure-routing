from __future__ import annotations

from typing import Annotated, Literal

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field, StrictInt, field_validator

from nbsr.config import Settings
from nbsr.name_model import normalize_hostname
from nbsr.name_service import NameRouteService
from nbsr.security import SecurityError, issue_ticket, validate_identity
from nbsr.synthetic import SyntheticAddressPool, SyntheticPoolExhausted

app = FastAPI(title="NBSR control plane")


class RouteRequest(BaseModel):
    service: str = Field(min_length=1, max_length=253, pattern=r"^[a-z0-9.-]+$")
    method: str = Field(min_length=3, max_length=7)
    path: str = Field(min_length=1, max_length=512)

    @field_validator("method")
    @classmethod
    def normalize_method(cls, value: str) -> str:
        return value.upper()

    @field_validator("path")
    @classmethod
    def absolute_path(cls, value: str) -> str:
        if not value.startswith("/") or ".." in value:
            raise ValueError("path must be absolute and normalized")
        return value


class NameRouteRequest(BaseModel):
    protocol_version: StrictInt
    request_id: str = Field(min_length=1, max_length=128)
    hostname: str
    transport: Literal["tcp"]
    client_nonce: str = Field(min_length=1, max_length=256)
    client_public_key: str = Field(min_length=1, max_length=128)
    capabilities: list[Annotated[str, Field(min_length=1, max_length=64)]] = Field(min_length=1, max_length=32)

    @field_validator("request_id", "client_nonce", "client_public_key")
    @classmethod
    def require_non_whitespace_value(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be blank")
        return value

    @field_validator("protocol_version")
    @classmethod
    def require_protocol_version_one(cls, value: int) -> int:
        if value != 1:
            raise ValueError("protocol version 1 is required")
        return value

    @field_validator("hostname")
    @classmethod
    def normalize_requested_hostname(cls, value: str) -> str:
        return normalize_hostname(value)

    @field_validator("capabilities")
    @classmethod
    def reject_blank_capabilities(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("capability values must not be blank")
        return values


def get_settings() -> Settings:
    return Settings()


_name_route_pool = SyntheticAddressPool("127.80.0.0/16", "fd00:6e62:7372::/64", ttl_seconds=60)


def get_name_route_service(settings: Settings = Depends(get_settings)) -> NameRouteService:
    return NameRouteService(pool=_name_route_pool, settings=settings)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/routes/resolve")
async def resolve(
    route: RouteRequest,
    authorization: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid workload identity")
    try:
        subject = validate_identity(authorization[7:], settings)
    except SecurityError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid workload identity") from exc
    policy_input = {"identity": subject, "service": route.service, "method": route.method, "path": route.path}
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.post(settings.opa_url, json={"input": policy_input})
            response.raise_for_status()
            decision = response.json().get("result", {})
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Authorization service unavailable") from exc
    if not decision.get("allow"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Route not authorized")
    token = issue_ticket(subject, route.service, route.method, route.path, decision, settings)
    return {"service": route.service, "gateway_url": settings.gateway_url, "routing_ticket": token, "expires_in": min(decision["ticket_ttl"], settings.ticket_ttl_seconds)}


@app.post("/v1/name-routes/resolve")
def resolve_name_route(
    route: NameRouteRequest,
    service: NameRouteService = Depends(get_name_route_service),
) -> dict[str, object]:
    try:
        response = service.resolve(route.hostname, route.client_public_key)
    except SecurityError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid name-route request") from exc
    except SyntheticPoolExhausted as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Name-route capacity unavailable",
            headers={"Retry-After": "60"},
        ) from exc
    return {
        "protocol_version": route.protocol_version,
        "request_id": route.request_id,
        **response.model_dump(),
    }
