from fastapi import FastAPI

app = FastAPI(title="NBSR demo payments")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/payment-status")
def payment_status() -> dict[str, str]:
    return {"service": "payments.internal", "status": "operational", "data": "demo-only"}


@app.post("/api/payments")
def create_payment() -> dict[str, str]:
    return {"service": "payments.internal", "status": "accepted", "data": "demo-only"}
