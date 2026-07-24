import pytest

from nbsr.destination_policy import DestinationDenied, DestinationPolicy


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.1.1",
        "224.0.0.1",
        "0.0.0.0",
        "192.0.2.1",
        "::1",
        "fe80::1",
        "ff02::1",
        "::",
        "fc00::1",
        "::ffff:127.0.0.1",
    ],
)
def test_default_destination_policy_rejects_non_global_addresses(address):
    with pytest.raises(DestinationDenied):
        DestinationPolicy().validate("attacker.test", address)


def test_default_destination_policy_accepts_global_unicast():
    assert DestinationPolicy().validate("example.com", "93.184.216.34") == "93.184.216.34"


def test_trusted_origin_rule_is_exact_for_both_hostname_and_network():
    policy = DestinationPolicy.from_config("facebook.test=127.0.0.1/32")

    assert policy.validate("facebook.test", "127.0.0.1") == "127.0.0.1"
    with pytest.raises(DestinationDenied):
        policy.validate("other.test", "127.0.0.1")
    with pytest.raises(DestinationDenied):
        policy.validate("facebook.test", "127.0.0.2")


@pytest.mark.parametrize(
    "configuration",
    ["facebook.test", "facebook.test=", "=127.0.0.1/32", "*.test=127.0.0.1/32", "facebook.test=not-a-network"],
)
def test_invalid_trusted_origin_configuration_fails_closed(configuration):
    with pytest.raises(ValueError):
        DestinationPolicy.from_config(configuration)
