import heapq
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Network, IPv6Network, ip_address, ip_network
from threading import RLock

from nbsr.name_model import normalize_hostname


_LOOPBACK_IPV4 = IPv4Network("127.0.0.0/8")
_NBSR_SYNTHETIC_ULA = IPv6Network("fd00:6e62:7372::/48")


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
        if not self._ipv4_network.subnet_of(_LOOPBACK_IPV4):
            raise ValueError("Synthetic IPv4 pool must be within the loopback range")
        if not self._ipv6_network.subnet_of(_NBSR_SYNTHETIC_ULA):
            raise ValueError("Synthetic IPv6 pool must be within the NBSR synthetic ULA prefix")
        self._ipv4_start, ipv4_capacity = self._host_range(self._ipv4_network)
        self._ipv6_start, ipv6_capacity = self._host_range(self._ipv6_network)
        self._capacity = min(ipv4_capacity, ipv6_capacity)
        if self._capacity <= 0:
            raise ValueError("Synthetic pools must contain usable hosts")
        self._ttl = timedelta(seconds=ttl_seconds)
        self._by_hostname: dict[str, SyntheticMapping] = {}
        self._by_address: dict[str, SyntheticMapping] = {}
        self._index_by_hostname: dict[str, int] = {}
        self._expirations: list[tuple[datetime, str]] = []
        self._free_indices: list[int] = []
        self._next_index = 0
        self._lock = RLock()

    def allocate(
        self,
        hostname: str,
        now: datetime | None = None,
        *,
        minimum_valid_for_seconds: int = 0,
    ) -> SyntheticMapping:
        now = now or datetime.now(UTC)
        hostname = normalize_hostname(hostname)
        required_expiry = now + timedelta(seconds=max(0, minimum_valid_for_seconds))
        with self._lock:
            self._expire(now)
            if mapping := self._by_hostname.get(hostname):
                if mapping.expires_at < required_expiry:
                    mapping = SyntheticMapping(mapping.hostname, mapping.ipv4, mapping.ipv6, required_expiry)
                    self._store(mapping, self._index_by_hostname[hostname])
                return mapping

            if self._free_indices:
                index = heapq.heappop(self._free_indices)
            elif self._next_index < self._capacity:
                index = self._next_index
                self._next_index += 1
            else:
                raise SyntheticPoolExhausted("Synthetic address pool exhausted")
            ipv4_text = str(self._ipv4_network.network_address + self._ipv4_start + index)
            ipv6_text = str(self._ipv6_network.network_address + self._ipv6_start + index)
            mapping = SyntheticMapping(hostname, ipv4_text, ipv6_text, max(now + self._ttl, required_expiry))
            self._store(mapping, index)
            return mapping

    def lookup(self, address: str, now: datetime | None = None) -> SyntheticMapping | None:
        now = now or datetime.now(UTC)
        try:
            address = str(ip_address(address))
        except ValueError:
            return None
        with self._lock:
            self._expire(now)
            return self._by_address.get(address)

    def _store(self, mapping: SyntheticMapping, index: int) -> None:
        self._by_hostname[mapping.hostname] = mapping
        self._by_address[mapping.ipv4] = mapping
        self._by_address[mapping.ipv6] = mapping
        self._index_by_hostname[mapping.hostname] = index
        heapq.heappush(self._expirations, (mapping.expires_at, mapping.hostname))

    def _expire(self, now: datetime) -> None:
        while self._expirations and self._expirations[0][0] <= now:
            expires_at, hostname = heapq.heappop(self._expirations)
            mapping = self._by_hostname.get(hostname)
            if mapping is None or mapping.expires_at != expires_at:
                continue
            del self._by_hostname[hostname]
            del self._by_address[mapping.ipv4]
            del self._by_address[mapping.ipv6]
            heapq.heappush(self._free_indices, self._index_by_hostname.pop(hostname))

    @staticmethod
    def _host_range(network: IPv4Network | IPv6Network) -> tuple[int, int]:
        if isinstance(network, IPv4Network):
            start = 1 if network.prefixlen < 31 else 0
            excluded = 2 if network.prefixlen < 31 else 0
        else:
            start = 1 if network.prefixlen < 127 else 0
            excluded = 1 if network.prefixlen < 127 else 0
        return start, network.num_addresses - excluded
