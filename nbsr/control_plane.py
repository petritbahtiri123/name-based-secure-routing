from __future__ import annotations

from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from nbsr.config import Settings
from nbsr.security import SecurityError, issue_ticket, validate_identity
from nbsr.service_tls import ServiceTlsError, create_mtls_client_context

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


def get_settings() -> Settings:
    return Settings()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def create_opa_mtls_context(settings: Settings):
    return create_mtls_client_context(
        url=settings.opa_url,
        ca_path=settings.enterprise_ca_path,
        certificate_path=settings.control_plane_client_cert_path,
        private_key_path=settings.control_plane_client_key_path,
    )


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
        async with httpx.AsyncClient(timeout=2.0, verify=create_opa_mtls_context(settings)) as client:
            response = await client.post(settings.opa_url, json={"input": policy_input})
            response.raise_for_status()
            decision = response.json().get("result", {})
    except (httpx.HTTPError, ValueError, ServiceTlsError) as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Authorization service unavailable") from exc
    if not decision.get("allow"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Route not authorized")
    token = issue_ticket(subject, route.service, route.method, route.path, decision, settings)
    return {
        "service": route.service,
        "gateway_url": settings.gateway_url,
        "routing_ticket": token,
        "expires_in": min(decision["ticket_ttl"], settings.ticket_ttl_seconds),
    }
