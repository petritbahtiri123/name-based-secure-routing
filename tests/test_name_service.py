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


@pytest.mark.parametrize("hostname", ("", "facebook..test", "face_book.test"))
def test_name_route_rejects_invalid_hostname(service, hostname):
    with pytest.raises(ValueError, match="Invalid NBSR hostname"):
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

    response = service.resolve("three.test", ClientSession.generate().public_key_b64)

    assert response.synthetic_ipv4 == "127.80.0.1"
