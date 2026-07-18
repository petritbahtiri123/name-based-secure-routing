from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException, Request

from nbsr.config import Settings
from nbsr.security import SecurityError, verify_ticket

app = FastAPI(title="NBSR ticket verifier")


def get_settings() -> Settings:
    return Settings()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.api_route("/authorize", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@app.api_route("/authorize/{original_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def authorize(
    request: Request,
    original_path: str = "",
    authorization: str | None = Header(default=None),
    x_nbsr_method: str | None = Header(default=None),
    x_nbsr_path: str | None = Header(default=None),
    x_nbsr_service: str = Header(default="payments.internal"),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    if not authorization or not authorization.startswith("NBSR "):
        raise HTTPException(401, "Routing authorization required")
    actual_method = x_nbsr_method or request.method
    actual_path = x_nbsr_path or f"/{original_path}"
    try:
        claims = verify_ticket(authorization[5:], actual_method, actual_path, x_nbsr_service, settings)
    except SecurityError as exc:
        raise HTTPException(403, "Invalid routing authorization") from exc
    return {"status": "authorized", "subject": claims["sub"]}
