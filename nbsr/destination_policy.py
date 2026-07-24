from __future__ import annotations

from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network, ip_address, ip_network

from nbsr.name_model import normalize_hostname


Address = IPv4Address | IPv6Address
Network = IPv4Network | IPv6Network


class DestinationDenied(ValueError):
    """A resolved origin address is outside the configured relay boundary."""


class DestinationPolicy:
    def __init__(self, trusted_origins: dict[str, tuple[Network, ...]] | None = None):
        self._trusted_origins = trusted_origins or {}

    @classmethod
    def from_config(cls, value: str) -> "DestinationPolicy":
        trusted: dict[str, list[Network]] = {}
        if not value.strip():
            return cls()
        for raw_rule in value.split(";"):
            if raw_rule.count("=") != 1:
                raise ValueError("Invalid trusted-origin rule")
            raw_hostname, raw_network = (part.strip() for part in raw_rule.split("=", 1))
            if not raw_hostname or not raw_network:
                raise ValueError("Invalid trusted-origin rule")
            try:
                hostname = normalize_hostname(raw_hostname)
                network = ip_network(raw_network, strict=True)
            except ValueError as exc:
                raise ValueError("Invalid trusted-origin rule") from exc
            trusted.setdefault(hostname, []).append(network)
        return cls({hostname: tuple(networks) for hostname, networks in trusted.items()})

    def validate(self, hostname: str, address: str) -> str:
        try:
            normalized_hostname = normalize_hostname(hostname)
            parsed = ip_address(address)
        except ValueError as exc:
            raise DestinationDenied("resolved destination is invalid") from exc

        effective: Address = parsed.ipv4_mapped if isinstance(parsed, IPv6Address) and parsed.ipv4_mapped else parsed
        if self._is_global_unicast(effective):
            return str(parsed)
        if any(effective.version == network.version and effective in network for network in self._trusted_origins.get(normalized_hostname, ())):
            return str(parsed)
        raise DestinationDenied("resolved destination is outside relay policy")

    @staticmethod
    def _is_global_unicast(address: Address) -> bool:
        return bool(
            address.is_global
            and not address.is_loopback
            and not address.is_link_local
            and not address.is_multicast
            and not address.is_reserved
            and not address.is_unspecified
        )
