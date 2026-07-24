from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Request

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
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    authorization = _single_header(request, "authorization", required=False)
    if not authorization or not authorization.startswith("NBSR "):
        raise HTTPException(401, "Routing authorization required")
    metadata = tuple(_single_header(request, name, required=True) for name in ("x-nbsr-method", "x-nbsr-path", "x-nbsr-service"))
    actual_method, actual_path, service = metadata
    try:
        claims = verify_ticket(authorization[5:], actual_method, actual_path, service, settings)
    except SecurityError as exc:
        raise HTTPException(403, "Invalid routing authorization") from exc
    return {"status": "authorized", "subject": claims["sub"]}


def _single_header(request: Request, name: str, *, required: bool) -> str | None:
    values = request.headers.getlist(name)
    if not values and not required:
        return None
    if len(values) != 1 or not values[0].strip():
        detail = "Trusted routing metadata required" if name.startswith("x-nbsr-") else "Routing authorization required"
        raise HTTPException(400, detail)
    return values[0]
