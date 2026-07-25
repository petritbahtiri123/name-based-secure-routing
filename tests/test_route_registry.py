import json

import pytest

from nbsr.route_registry import RouteRegistry, RouteRegistryError


def route_entry(**overrides):
    entry = {
        "name": "facebook.test",
        "route_id": "isp-demo-facebook",
        "origin_hostname": "name-origin",
        "ports": [80, 443],
        "authorized_endpoints": ["172.31.0.10"],
        "allowed_cidrs": ["172.31.0.10/32"],
        "expected_http_host": "facebook.test",
        "expected_tls_sni": "facebook.test",
        "enabled": True,
        "policy_version": 1,
    }
    entry.update(overrides)
    return entry


def registry_with(**overrides):
    return RouteRegistry.from_json(json.dumps({"version": 1, "routes": [route_entry(**overrides)]}))


def test_registry_returns_an_immutable_default_deny_route():
    policy = registry_with().require_name("facebook.test")

    assert policy.route_id == "isp-demo-facebook"
    assert policy.authorized_endpoints == ("172.31.0.10",)
    assert policy.allowed_cidrs == ("172.31.0.10/32",)
    assert len(policy.fingerprint) == 64
    with pytest.raises(RouteRegistryError, match="not registered"):
        registry_with().require_name("example.com")


@pytest.mark.parametrize(
    "requested_name",
    [
        "FACEBOOK.TEST",
        "facebook.test.",
        "facebook\u3002test",
        "xn--facebook-9za.test",
        "93.184.216.34",
    ],
)
def test_registry_rejects_noncanonical_or_unregistered_names(requested_name):
    with pytest.raises(RouteRegistryError):
        registry_with().require_name(requested_name)


def test_registry_rejects_disabled_routes_and_unknown_route_ids():
    with pytest.raises(RouteRegistryError, match="disabled"):
        registry_with(enabled=False).require_name("facebook.test")
    with pytest.raises(RouteRegistryError, match="not registered"):
        registry_with().require_route("other-route")


@pytest.mark.parametrize(
    "overrides",
    [
        {"route_id": ""},
        {"origin_hostname": "172.31.0.10"},
        {"ports": [22]},
        {"authorized_endpoints": []},
        {"authorized_endpoints": ["172.31.0.11"]},
        {"allowed_cidrs": ["0.0.0.0/0"]},
        {"expected_http_host": "172.31.0.10"},
        {"expected_tls_sni": "facebook\u3002test"},
        {"policy_version": 0},
    ],
)
def test_registry_rejects_unsafe_or_ambiguous_entries(overrides):
    with pytest.raises(RouteRegistryError):
        registry_with(**overrides)


def test_registry_fingerprint_changes_with_enforcement_relevant_policy():
    before = registry_with().require_name("facebook.test")
    after = registry_with(ports=[443]).require_name("facebook.test")

    assert before.fingerprint != after.fingerprint
