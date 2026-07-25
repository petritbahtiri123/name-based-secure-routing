from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from ipaddress import ip_address, ip_network
from pathlib import Path
from typing import Any

from nbsr.name_model import normalize_hostname


_ALLOWED_PORTS = frozenset((80, 443))


class RouteRegistryError(ValueError):
    """A route is missing, disabled, ambiguous, or unsafe."""


def _canonical_hostname(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise RouteRegistryError(f"invalid {field}")
    try:
        normalized = normalize_hostname(value)
    except ValueError as exc:
        raise RouteRegistryError(f"invalid {field}") from exc
    if value != normalized:
        raise RouteRegistryError(f"invalid {field}")
    try:
        ip_address(value)
    except ValueError:
        return normalized
    raise RouteRegistryError(f"invalid {field}")


def _canonical_ip(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise RouteRegistryError("invalid authorized endpoint")
    try:
        parsed = ip_address(value)
    except ValueError as exc:
        raise RouteRegistryError("invalid authorized endpoint") from exc
    if value != str(parsed):
        raise RouteRegistryError("invalid authorized endpoint")
    return value


@dataclass(frozen=True)
class RoutePolicy:
    name: str
    route_id: str
    origin_hostname: str
    ports: tuple[int, ...]
    authorized_endpoints: tuple[str, ...]
    allowed_cidrs: tuple[str, ...]
    expected_http_host: str | None
    expected_tls_sni: str | None
    enabled: bool
    policy_version: int
    fingerprint: str

    @classmethod
    def from_mapping(cls, raw: object) -> "RoutePolicy":
        if not isinstance(raw, dict):
            raise RouteRegistryError("route entry must be an object")
        allowed_fields = {
            "name",
            "route_id",
            "origin_hostname",
            "ports",
            "authorized_endpoints",
            "allowed_cidrs",
            "expected_http_host",
            "expected_tls_sni",
            "enabled",
            "policy_version",
        }
        if set(raw) != allowed_fields:
            raise RouteRegistryError("route entry fields are invalid")

        name = _canonical_hostname(raw["name"], "route name")
        origin_hostname = _canonical_hostname(raw["origin_hostname"], "origin hostname")
        route_id = raw["route_id"]
        if (
            not isinstance(route_id, str)
            or not route_id
            or len(route_id) > 128
            or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for character in route_id)
        ):
            raise RouteRegistryError("invalid route ID")

        raw_ports = raw["ports"]
        if (
            not isinstance(raw_ports, list)
            or not raw_ports
            or any(type(port) is not int or port not in _ALLOWED_PORTS for port in raw_ports)
        ):
            raise RouteRegistryError("invalid route ports")
        ports = tuple(sorted(set(raw_ports)))
        if len(ports) != len(raw_ports):
            raise RouteRegistryError("invalid route ports")

        raw_endpoints = raw["authorized_endpoints"]
        if not isinstance(raw_endpoints, list) or not raw_endpoints:
            raise RouteRegistryError("route requires authorized endpoints")
        endpoints = tuple(sorted({_canonical_ip(value) for value in raw_endpoints}))
        if len(endpoints) != len(raw_endpoints):
            raise RouteRegistryError("duplicate authorized endpoint")

        raw_cidrs = raw["allowed_cidrs"]
        if not isinstance(raw_cidrs, list) or not raw_cidrs:
            raise RouteRegistryError("route requires allowed CIDRs")
        networks = []
        for value in raw_cidrs:
            if not isinstance(value, str) or not value:
                raise RouteRegistryError("invalid allowed CIDR")
            try:
                network = ip_network(value, strict=True)
            except ValueError as exc:
                raise RouteRegistryError("invalid allowed CIDR") from exc
            if value != str(network) or network.prefixlen == 0:
                raise RouteRegistryError("invalid allowed CIDR")
            networks.append(network)
        cidrs = tuple(sorted({str(network) for network in networks}))
        if len(cidrs) != len(raw_cidrs):
            raise RouteRegistryError("duplicate allowed CIDR")

        for endpoint in endpoints:
            parsed = ip_address(endpoint)
            if not any(parsed.version == network.version and parsed in network for network in networks):
                raise RouteRegistryError("authorized endpoint is outside allowed CIDRs")

        expected_http_host = raw["expected_http_host"]
        expected_tls_sni = raw["expected_tls_sni"]
        if expected_http_host is not None:
            expected_http_host = _canonical_hostname(expected_http_host, "HTTP Host")
        if expected_tls_sni is not None:
            expected_tls_sni = _canonical_hostname(expected_tls_sni, "TLS SNI")
        if 80 in ports and expected_http_host is None:
            raise RouteRegistryError("HTTP route requires an expected Host")
        if 443 in ports and expected_tls_sni is None:
            raise RouteRegistryError("HTTPS route requires expected TLS SNI")

        enabled = raw["enabled"]
        policy_version = raw["policy_version"]
        if type(enabled) is not bool or type(policy_version) is not int or policy_version < 1:
            raise RouteRegistryError("invalid route policy state")

        canonical = {
            "allowed_cidrs": list(cidrs),
            "authorized_endpoints": list(endpoints),
            "enabled": enabled,
            "expected_http_host": expected_http_host,
            "expected_tls_sni": expected_tls_sni,
            "name": name,
            "origin_hostname": origin_hostname,
            "policy_version": policy_version,
            "ports": list(ports),
            "route_id": route_id,
        }
        fingerprint = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
        ).hexdigest()
        return cls(
            name=name,
            route_id=route_id,
            origin_hostname=origin_hostname,
            ports=ports,
            authorized_endpoints=endpoints,
            allowed_cidrs=cidrs,
            expected_http_host=expected_http_host,
            expected_tls_sni=expected_tls_sni,
            enabled=enabled,
            policy_version=policy_version,
            fingerprint=fingerprint,
        )

    def as_claims(self) -> dict[str, Any]:
        return {
            "route_id": self.route_id,
            "origin_hostname": self.origin_hostname,
            "authorized_endpoints": list(self.authorized_endpoints),
            "allowed_cidrs": list(self.allowed_cidrs),
            "expected_http_host": self.expected_http_host,
            "expected_tls_sni": self.expected_tls_sni,
            "route_policy_version": self.policy_version,
            "route_policy_fingerprint": self.fingerprint,
        }

    def claims_match(self, claims: dict[str, Any]) -> bool:
        return all(claims.get(key) == value for key, value in self.as_claims().items())


class RouteRegistry:
    def __init__(self, routes: tuple[RoutePolicy, ...]):
        by_name: dict[str, RoutePolicy] = {}
        by_id: dict[str, RoutePolicy] = {}
        for route in routes:
            if route.name in by_name or route.route_id in by_id:
                raise RouteRegistryError("duplicate route name or ID")
            by_name[route.name] = route
            by_id[route.route_id] = route
        self._by_name = by_name
        self._by_id = by_id

    @classmethod
    def from_json(cls, value: str) -> "RouteRegistry":
        try:
            document = json.loads(value)
        except (json.JSONDecodeError, TypeError) as exc:
            raise RouteRegistryError("route registry is not valid JSON") from exc
        if not isinstance(document, dict) or set(document) != {"version", "routes"} or document["version"] != 1:
            raise RouteRegistryError("route registry document is invalid")
        routes = document["routes"]
        if not isinstance(routes, list):
            raise RouteRegistryError("route registry routes must be a list")
        return cls(tuple(RoutePolicy.from_mapping(route) for route in routes))

    @classmethod
    def from_path(cls, path: Path | str) -> "RouteRegistry":
        try:
            value = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            raise RouteRegistryError("route registry is unavailable") from exc
        return cls.from_json(value)

    @classmethod
    def from_settings(cls, settings: object) -> "RouteRegistry":
        inline = getattr(settings, "name_route_registry_json", None)
        if inline:
            return cls.from_json(inline)
        return cls.from_path(getattr(settings, "name_route_registry_path"))

    def require_name(self, requested_name: object) -> RoutePolicy:
        if not isinstance(requested_name, str):
            raise RouteRegistryError("route name is invalid")
        try:
            normalized = normalize_hostname(requested_name)
        except ValueError as exc:
            raise RouteRegistryError("route name is invalid") from exc
        if requested_name != normalized:
            raise RouteRegistryError("route name must be canonical")
        route = self._by_name.get(normalized)
        if route is None:
            raise RouteRegistryError("route is not registered")
        if not route.enabled:
            raise RouteRegistryError("route is disabled")
        return route

    def require_route(self, route_id: object) -> RoutePolicy:
        route = self._by_id.get(route_id) if isinstance(route_id, str) else None
        if route is None:
            raise RouteRegistryError("route is not registered")
        if not route.enabled:
            raise RouteRegistryError("route is disabled")
        return route
