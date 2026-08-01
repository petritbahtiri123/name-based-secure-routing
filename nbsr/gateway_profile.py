from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from ipaddress import IPv4Network, IPv6Network, ip_address, ip_network
from typing import Any, Mapping


_PROFILE_FIELDS = frozenset(
    {
        "instance_id",
        "synthetic_ipv4",
        "synthetic_ipv6",
        "name_node_host",
        "name_node_port",
        "source_edge_host",
        "source_edge_port",
        "policy_table",
        "firewall_mark",
    }
)
_SNAPSHOT_FIELDS = frozenset(
    {
        "resources",
        "resolver_state",
        "observed_operation_ids",
        "name_plane_healthy",
        "route_plane_healthy",
        "resolver_parity",
        "service_attribution",
        "fair_share",
        "direct_origin_fallback",
    }
)
_RESOURCE_FIELDS = frozenset({"kind", "prefix", "owner"})
_RESOURCE_KINDS = frozenset({"interface", "route", "vpn", "container", "reserved"})
_FORBIDDEN_IPV4 = tuple(IPv4Network(value) for value in ("10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
_IPV6_ULA = IPv6Network("fc00::/7")
_INSTANCE_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?\Z")
_MAX_ITEMS = 256


class ProfileError(ValueError):
    """A gateway profile or injected snapshot is invalid."""


def _mapping(value: object, fields: frozenset[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict) or set(value) != fields or not all(type(key) is str for key in value):
        raise ProfileError(f"{label} must contain exactly the approved fields")
    return value


def _integer(value: object, minimum: int, maximum: int, label: str) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ProfileError(f"{label} is outside the approved range")
    return value


def _host(value: object, label: str) -> str:
    if type(value) is not str:
        raise ProfileError(f"{label} must be a canonical IP address")
    try:
        parsed = ip_address(value)
    except ValueError as exc:
        raise ProfileError(f"{label} must be a canonical IP address") from exc
    if str(parsed) != value or parsed.is_unspecified or parsed.is_multicast:
        raise ProfileError(f"{label} must be a usable canonical IP address")
    return value


def _network(value: object, version: int, label: str) -> IPv4Network | IPv6Network:
    if type(value) is not str:
        raise ProfileError(f"{label} must be a canonical prefix")
    try:
        parsed = ip_network(value, strict=True)
    except ValueError as exc:
        raise ProfileError(f"{label} must be a canonical prefix") from exc
    if parsed.version != version or str(parsed) != value:
        raise ProfileError(f"{label} must be a canonical IPv{version} prefix")
    return parsed


@dataclass(frozen=True)
class GatewayProfile:
    instance_id: str
    synthetic_ipv4: str
    synthetic_ipv6: str
    name_node_host: str
    name_node_port: int
    source_edge_host: str
    source_edge_port: int
    policy_table: int
    firewall_mark: int

    @classmethod
    def from_dict(cls, value: object) -> GatewayProfile:
        data = _mapping(value, _PROFILE_FIELDS, "gateway profile")
        instance_id = data["instance_id"]
        if type(instance_id) is not str or _INSTANCE_RE.fullmatch(instance_id) is None:
            raise ProfileError("instance_id must be a canonical lowercase package identifier")
        ipv4 = _network(data["synthetic_ipv4"], 4, "synthetic_ipv4")
        if any(ipv4.overlaps(forbidden) for forbidden in _FORBIDDEN_IPV4):
            raise ProfileError("synthetic_ipv4 uses a forbidden routed-gateway range")
        ipv6 = _network(data["synthetic_ipv6"], 6, "synthetic_ipv6")
        if not ipv6.subnet_of(_IPV6_ULA):
            raise ProfileError("synthetic_ipv6 must be ULA")
        return cls(
            instance_id=instance_id,
            synthetic_ipv4=str(ipv4),
            synthetic_ipv6=str(ipv6),
            name_node_host=_host(data["name_node_host"], "name_node_host"),
            name_node_port=_integer(data["name_node_port"], 1, 65535, "name_node_port"),
            source_edge_host=_host(data["source_edge_host"], "source_edge_host"),
            source_edge_port=_integer(data["source_edge_port"], 1, 65535, "source_edge_port"),
            policy_table=_integer(data["policy_table"], 10000, 19999, "policy_table"),
            firewall_mark=_integer(data["firewall_mark"], 0x4E420000, 0x4E42FFFF, "firewall_mark"),
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def digest(self) -> str:
        encoded = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class NetworkResource:
    kind: str
    prefix: str
    owner: str | None

    @classmethod
    def from_dict(cls, value: object) -> NetworkResource:
        data = _mapping(value, _RESOURCE_FIELDS, "network resource")
        kind = data["kind"]
        owner = data["owner"]
        if type(kind) is not str or kind not in _RESOURCE_KINDS:
            raise ProfileError("network resource kind is not approved")
        if owner is not None and (type(owner) is not str or _INSTANCE_RE.fullmatch(owner) is None):
            raise ProfileError("network resource owner is invalid")
        prefix = data["prefix"]
        parsed = _network(prefix, ip_network(prefix, strict=False).version if type(prefix) is str else 0, "resource prefix")
        return cls(kind, str(parsed), owner)


@dataclass(frozen=True)
class PlatformSnapshot:
    resources: tuple[NetworkResource, ...]
    resolver_state: tuple[str, ...]
    observed_operation_ids: tuple[str, ...]
    name_plane_healthy: bool
    route_plane_healthy: bool
    resolver_parity: bool
    service_attribution: bool
    fair_share: bool
    direct_origin_fallback: bool

    @classmethod
    def from_dict(cls, value: object) -> PlatformSnapshot:
        data = _mapping(value, _SNAPSHOT_FIELDS, "platform snapshot")
        resources = data["resources"]
        resolver_state = data["resolver_state"]
        observed = data["observed_operation_ids"]
        if type(resources) is not list or len(resources) > _MAX_ITEMS:
            raise ProfileError("resources must be a bounded list")
        if type(resolver_state) is not list or len(resolver_state) > _MAX_ITEMS or not all(type(item) is str for item in resolver_state):
            raise ProfileError("resolver_state must be a bounded string list")
        if type(observed) is not list or len(observed) > _MAX_ITEMS or not all(type(item) is str for item in observed):
            raise ProfileError("observed_operation_ids must be a bounded string list")
        flags = {}
        for field in _SNAPSHOT_FIELDS - {"resources", "resolver_state", "observed_operation_ids"}:
            if type(data[field]) is not bool:
                raise ProfileError(f"{field} must be boolean")
            flags[field] = data[field]
        return cls(
            resources=tuple(NetworkResource.from_dict(item) for item in resources),
            resolver_state=tuple(resolver_state),
            observed_operation_ids=tuple(observed),
            **flags,
        )


def assert_collision_free(profile: GatewayProfile, snapshot: PlatformSnapshot) -> None:
    configured = (ip_network(profile.synthetic_ipv4), ip_network(profile.synthetic_ipv6))
    for resource in snapshot.resources:
        existing = ip_network(resource.prefix)
        for wanted in configured:
            if existing.version != wanted.version or not existing.overlaps(wanted):
                continue
            if existing == wanted and resource.owner == profile.instance_id:
                continue
            raise ProfileError("synthetic prefix collision detected")
