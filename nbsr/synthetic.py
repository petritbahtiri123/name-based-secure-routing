from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Network, IPv6Network, ip_address, ip_network

from nbsr.name_model import normalize_hostname


class SyntheticPoolExhausted(Exception):
    """Raised when no unused synthetic address pair remains."""


@dataclass(frozen=True)
class SyntheticMapping:
    hostname: str
    ipv4: str
    ipv6: str
    expires_at: datetime


class SyntheticAddressPool:
    def __init__(self, ipv4_cidr: str, ipv6_cidr: str, *, ttl_seconds: int):
        self._ipv4_network = ip_network(ipv4_cidr)
        self._ipv6_network = ip_network(ipv6_cidr)
        if not isinstance(self._ipv4_network, IPv4Network) or not isinstance(self._ipv6_network, IPv6Network):
            raise ValueError("Synthetic pools must be IPv4 and IPv6 networks")
        self._ttl = timedelta(seconds=ttl_seconds)
        self._by_hostname: dict[str, SyntheticMapping] = {}
        self._by_address: dict[str, SyntheticMapping] = {}

    def allocate(self, hostname: str, now: datetime | None = None) -> SyntheticMapping:
        now = now or datetime.now(UTC)
        self._expire(now)
        hostname = normalize_hostname(hostname)
        if mapping := self._by_hostname.get(hostname):
            return mapping

        for ipv4, ipv6 in zip(self._ipv4_network.hosts(), self._ipv6_network.hosts(), strict=False):
            ipv4_text = str(ipv4)
            ipv6_text = str(ipv6)
            if ipv4_text not in self._by_address and ipv6_text not in self._by_address:
                mapping = SyntheticMapping(hostname, ipv4_text, ipv6_text, now + self._ttl)
                self._by_hostname[hostname] = mapping
                self._by_address[ipv4_text] = mapping
                self._by_address[ipv6_text] = mapping
                return mapping
        raise SyntheticPoolExhausted("Synthetic address pool exhausted")

    def lookup(self, address: str, now: datetime | None = None) -> SyntheticMapping | None:
        now = now or datetime.now(UTC)
        self._expire(now)
        try:
            address = str(ip_address(address))
        except ValueError:
            return None
        return self._by_address.get(address)

    def _expire(self, now: datetime) -> None:
        for hostname, mapping in list(self._by_hostname.items()):
            if mapping.expires_at <= now:
                del self._by_hostname[hostname]
                del self._by_address[mapping.ipv4]
                del self._by_address[mapping.ipv6]
