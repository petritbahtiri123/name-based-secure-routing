from fastapi.testclient import TestClient

from nbsr.payments import app as payments_app


def test_payments_demo_endpoint():
    response = TestClient(payments_app).get("/api/payment-status")
    assert response.status_code == 200
    assert response.json()["service"] == "payments.internal"
