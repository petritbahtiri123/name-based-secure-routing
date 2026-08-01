from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from nbsr.gateway_profile import GatewayProfile, PlatformSnapshot, ProfileError, assert_collision_free


def profile_data(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "instance_id": "lab-edge-01",
        "synthetic_ipv4": "192.0.2.0/24",
        "synthetic_ipv6": "fd00:6e62:7372:5::/64",
        "name_node_host": "127.0.0.1",
        "name_node_port": 5353,
        "source_edge_host": "127.0.0.1",
        "source_edge_port": 7443,
        "policy_table": 10042,
        "firewall_mark": 0x4E42002A,
    }
    value.update(overrides)
    return value


def snapshot_data(resources: list[dict[str, object]] | None = None, **overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "resources": resources or [],
        "resolver_state": ["nameserver", "192.0.2.53"],
        "observed_operation_ids": [],
        "name_plane_healthy": False,
        "route_plane_healthy": False,
        "resolver_parity": False,
        "service_attribution": False,
        "fair_share": False,
        "direct_origin_fallback": False,
    }
    value.update(overrides)
    return value


def test_profile_accepts_exact_lab_boundary_and_is_immutable() -> None:
    profile = GatewayProfile.from_dict(profile_data())

    assert profile.synthetic_ipv4 == "192.0.2.0/24"
    assert profile.synthetic_ipv6 == "fd00:6e62:7372:5::/64"
    assert len(profile.digest()) == 64
    with pytest.raises(FrozenInstanceError):
        profile.policy_table = 10043  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("instance_id", "../edge"),
        ("instance_id", "EDGE"),
        ("synthetic_ipv4", "192.0.2.1/24"),
        ("synthetic_ipv4", "127.80.0.0/16"),
        ("synthetic_ipv4", "10.0.0.0/8"),
        ("synthetic_ipv4", "100.64.0.0/10"),
        ("synthetic_ipv6", "2001:db8::/64"),
        ("synthetic_ipv6", "fd00:6e62:7372:5::1/64"),
        ("name_node_host", "0.0.0.0"),
        ("source_edge_host", "::"),
        ("name_node_port", 0),
        ("source_edge_port", True),
        ("policy_table", 9999),
        ("policy_table", 20000),
        ("firewall_mark", 0x4E41FFFF),
        ("firewall_mark", 0x4E430000),
    ),
)
def test_profile_rejects_invalid_or_unsafe_values(field: str, value: object) -> None:
    with pytest.raises(ProfileError):
        GatewayProfile.from_dict(profile_data(**{field: value}))


def test_profile_rejects_unknown_and_missing_fields() -> None:
    with pytest.raises(ProfileError):
        GatewayProfile.from_dict(profile_data(extra=True))
    missing = profile_data()
    missing.pop("policy_table")
    with pytest.raises(ProfileError):
        GatewayProfile.from_dict(missing)


def test_snapshot_is_closed_bounded_and_strictly_typed() -> None:
    with pytest.raises(ProfileError):
        PlatformSnapshot.from_dict(snapshot_data(extra=True))
    with pytest.raises(ProfileError):
        PlatformSnapshot.from_dict(snapshot_data([{"kind": "route", "prefix": "192.0.2.0/24", "owner": 4}]))
    with pytest.raises(ProfileError):
        PlatformSnapshot.from_dict(snapshot_data([{"kind": "route", "prefix": "192.0.2.0/24", "owner": None}] * 257))


@pytest.mark.parametrize("kind", ("interface", "route", "vpn", "container", "reserved"))
def test_collision_inventory_rejects_every_resource_kind(kind: str) -> None:
    profile = GatewayProfile.from_dict(profile_data())
    snapshot = PlatformSnapshot.from_dict(snapshot_data([{"kind": kind, "prefix": "192.0.2.128/25", "owner": None}]))

    with pytest.raises(ProfileError, match="collision"):
        assert_collision_free(profile, snapshot)


def test_collision_allows_only_exact_prefix_owned_by_same_instance() -> None:
    profile = GatewayProfile.from_dict(profile_data())
    owned = PlatformSnapshot.from_dict(snapshot_data([{"kind": "route", "prefix": "192.0.2.0/24", "owner": "lab-edge-01"}]))
    assert_collision_free(profile, owned)

    for prefix, owner in (("192.0.2.0/24", "other-edge"), ("192.0.2.0/25", "lab-edge-01")):
        snapshot = PlatformSnapshot.from_dict(snapshot_data([{"kind": "route", "prefix": prefix, "owner": owner}]))
        with pytest.raises(ProfileError, match="collision"):
            assert_collision_free(profile, snapshot)
