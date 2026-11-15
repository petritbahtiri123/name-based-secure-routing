from datetime import UTC, datetime, timedelta
import json

import pytest

from nbsr.config import Settings
from nbsr.name_security import ClientSession
from nbsr.name_service import NameRouteService
from nbsr.synthetic import SyntheticAddressPool


@pytest.fixture()
def settings():
    return Settings.for_tests(
        ClientSession.generate().private_key,
        ClientSession.generate().private_key,
        ClientSession.generate().private_key,
    )


@pytest.fixture()
def service(settings):
    return NameRouteService(
        pool=SyntheticAddressPool("127.80.0.0/29", "fd00:6e62:7372::/125", ttl_seconds=60),
        settings=settings,
    )


def test_name_route_response_contains_only_synthetic_addresses(service):
    response = service.resolve("facebook.test", ClientSession.generate().public_key_b64)

    encoded = response.model_dump_json()
    assert response.hostname == "facebook.test"
    assert response.synthetic_ipv4.startswith("127.80.")
    assert "203.0.113.10" not in encoded
    assert "resolved_addresses" not in encoded


@pytest.mark.parametrize(
    "hostname",
    (
        "",
        "facebook..test",
        "face_book.test",
        "FACEBOOK.TEST",
        "facebook.test.",
        "facebook\u3002test",
        "example.com",
        "93.184.216.34",
    ),
)
def test_name_route_rejects_invalid_hostname(service, hostname):
    with pytest.raises(ValueError):
        service.resolve(hostname, ClientSession.generate().public_key_b64)


def test_name_route_rejects_invalid_session_key(service):
    with pytest.raises(ValueError, match="Invalid client session key"):
        service.resolve("facebook.test", "not-a-key")


def test_invalid_session_keys_do_not_consume_synthetic_addresses(settings):
    service = NameRouteService(
        pool=SyntheticAddressPool("127.80.0.0/30", "fd00:6e62:7372::/126", ttl_seconds=60),
        settings=settings,
    )

    for hostname in ("one.test", "two.test"):
        with pytest.raises(ValueError, match="Invalid client session key"):
            service.resolve(hostname, "not-a-key")

    response = service.resolve("facebook.test", ClientSession.generate().public_key_b64)

    assert response.synthetic_ipv4 == "127.80.0.1"


def test_name_route_rejects_invalid_capability(service):
    with pytest.raises(ValueError, match="route capabilities"):
        service.resolve("facebook.test", ClientSession.generate().public_key_b64, ("tcp:22",))


def test_route_binding_never_outlives_its_synthetic_mapping(settings):
    pool = SyntheticAddressPool("127.80.0.0/29", "fd00:6e62:7372::/125", ttl_seconds=1)
    service = NameRouteService(pool=pool, settings=settings)
    before = datetime.now(UTC)

    response = service.resolve("facebook.test", ClientSession.generate().public_key_b64)

    mapping = pool.lookup(response.synthetic_ipv4, now=before + timedelta(seconds=30))
    assert mapping is not None


def test_valid_capability_outside_policy_is_rejected_before_side_effects(settings, monkeypatch):
    registry = json.loads(settings.name_route_registry_json)
    for route in registry["routes"]:
        route["ports"] = [443]
    restricted = settings.model_copy(update={"name_route_registry_json": json.dumps(registry)})
    pool = SyntheticAddressPool("127.80.0.0/29", "fd00:6e62:7372::/125", ttl_seconds=60)
    service = NameRouteService(pool=pool, settings=restricted)
    calls = []

    def forbidden(*args, **kwargs):
        calls.append("side effect")
        raise AssertionError("denied capability reached admission, allocation or signing")

    monkeypatch.setattr(service._admission_limiter, "consume", forbidden)
    monkeypatch.setattr(pool, "allocate", forbidden)
    monkeypatch.setattr("nbsr.name_service.issue_name_binding", forbidden)
    with pytest.raises(ValueError, match="outside the registered route policy"):
        service.resolve("facebook.test", ClientSession.generate().public_key_b64, ("http",))
    assert calls == []
