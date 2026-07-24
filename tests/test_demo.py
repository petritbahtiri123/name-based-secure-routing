from base64 import urlsafe_b64decode
from io import StringIO

from nbsr import demo_client
from scripts import demo
from scripts.demo import tamper_ticket


def decode_segment(segment: str) -> bytes:
    return urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def test_tamper_ticket_changes_decoded_signature_bytes():
    signature = "A" * 86
    ticket = f"header.payload.{signature}"

    tampered = tamper_ticket(ticket)
    original_parts = ticket.split(".")
    tampered_parts = tampered.split(".")

    assert tampered_parts[:2] == original_parts[:2]
    assert decode_segment(tampered_parts[2]) != decode_segment(original_parts[2])


def test_demo_sends_enterprise_credentials_only_over_https(monkeypatch, tmp_path):
    observed: list[tuple[str, str, object]] = []
    token_dir = tmp_path / "tokens"
    token_dir.mkdir()
    (token_dir / "client-allowed.jwt").write_text("identity-token", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    class Response:
        status_code = 200

    def record_post(url, **kwargs):
        observed.append(("POST", url, kwargs.get("verify")))
        return Response()

    def record_request(method, url, **kwargs):
        observed.append((method, url, kwargs.get("verify")))
        return Response()

    monkeypatch.setattr(demo.httpx, "post", record_post)
    monkeypatch.setattr(demo.httpx, "request", record_request)

    demo.resolve("allowed")
    demo.gateway("routing-ticket")

    assert observed == [
        ("POST", "https://localhost:8000/v1/routes/resolve", "secrets/demo-ca.pem"),
        ("GET", "https://localhost:8080/api/payment-status", "secrets/demo-ca.pem"),
    ]


def test_container_demo_client_uses_https_and_the_enterprise_ca(monkeypatch):
    observed: dict[str, object] = {}

    class Response:
        status_code = 200
        is_success = True

        @staticmethod
        def json():
            return {"routing_ticket": "ticket", "service": "payments.internal"}

    class Client:
        def __init__(self, **kwargs):
            observed["client_kwargs"] = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, url, **_kwargs):
            observed["control_url"] = url
            return Response()

        def request(self, _method, url, **_kwargs):
            observed["gateway_url"] = url
            return Response()

    monkeypatch.delenv("NBSR_CONTROL_URL", raising=False)
    monkeypatch.delenv("NBSR_GATEWAY_URL", raising=False)
    monkeypatch.delenv("NBSR_ENTERPRISE_CA_PATH", raising=False)
    monkeypatch.setattr(demo_client.httpx, "Client", Client)
    monkeypatch.setattr("builtins.open", lambda *_args, **_kwargs: StringIO("identity-token"))
    monkeypatch.setattr("sys.argv", ["nbsr.demo_client"])

    assert demo_client.main() == 0
    assert observed == {
        "client_kwargs": {"timeout": 5, "verify": "/run/secrets/demo-ca.pem"},
        "control_url": "https://control-plane:8000/v1/routes/resolve",
        "gateway_url": "https://gateway:8080/api/payment-status",
    }
