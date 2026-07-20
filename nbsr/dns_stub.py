from __future__ import annotations

from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network, ip_address
from time import monotonic
from typing import Callable

from dnslib import A, AAAA, CLASS, DNSHeader, DNSRecord, QTYPE, RCODE, RR
from dnslib.dns import DNSError


_MAX_DNS_TTL = 60
_NBSR_SYNTHETIC_IPV4 = IPv4Network("127.80.0.0/16")
_NBSR_SYNTHETIC_IPV6 = IPv6Network("fd00:6e62:7372::/48")


@dataclass(frozen=True)
class ClientRoute:
    hostname: str
    synthetic_ipv4: str
    synthetic_ipv6: str
    route_binding: str
    expires_in: int


class RouteTable:
    """In-memory client route state keyed only by synthetic address."""

    def __init__(self) -> None:
        self._routes: dict[str, tuple[ClientRoute, float]] = {}

    def put(self, mapping: ClientRoute) -> None:
        self._validate(mapping)
        expires_in = max(0, min(mapping.expires_in, _MAX_DNS_TTL))
        expires_at = monotonic() + expires_in
        self._routes[mapping.synthetic_ipv4] = (mapping, expires_at)
        self._routes[mapping.synthetic_ipv6] = (mapping, expires_at)

    def lookup(self, address: str) -> ClientRoute | None:
        entry = self._routes.get(str(ip_address(address)))
        if entry is None:
            return None
        mapping, expires_at = entry
        if expires_at <= monotonic():
            self._routes.pop(mapping.synthetic_ipv4, None)
            self._routes.pop(mapping.synthetic_ipv6, None)
            return None
        return mapping

    @staticmethod
    def _validate(mapping: ClientRoute) -> None:
        ipv4 = ip_address(mapping.synthetic_ipv4)
        ipv6 = ip_address(mapping.synthetic_ipv6)
        if (
            not isinstance(ipv4, IPv4Address)
            or not isinstance(ipv6, IPv6Address)
            or ipv4 not in _NBSR_SYNTHETIC_IPV4
            or ipv6 not in _NBSR_SYNTHETIC_IPV6
            or str(ipv4) != mapping.synthetic_ipv4
            or str(ipv6) != mapping.synthetic_ipv6
        ):
            raise ValueError("route must contain NBSR synthetic addresses")


class DnsStub:
    """Strict DNS response builder that never exposes origin addresses."""

    def __init__(
        self,
        resolve_route: Callable[[str], ClientRoute],
        route_table: RouteTable,
        *,
        ttl_seconds: int = _MAX_DNS_TTL,
        ipv6_available: Callable[[], bool] | None = None,
    ):
        if not 0 < ttl_seconds <= _MAX_DNS_TTL:
            raise ValueError("DNS TTL must be between 1 and 60 seconds")
        self._resolve_route = resolve_route
        self._route_table = route_table
        self._ttl_seconds = ttl_seconds
        self._ipv6_available = ipv6_available or (lambda: True)

    def resolve_query(self, packet: bytes) -> bytes:
        request_id = int.from_bytes(packet[:2], "big") if len(packet) >= 2 else 0
        try:
            request = DNSRecord.parse(packet)
        except DNSError:
            return self._error_response(request_id, RCODE.FORMERR)
        if request.header.qr != 0:
            return self._reply_with_error(request, RCODE.FORMERR)
        if request.header.opcode != 0:
            return self._reply_with_error(request, RCODE.NOTIMP)
        if len(request.questions) != 1:
            return self._reply_with_error(request, RCODE.FORMERR)

        question = request.questions[0]
        if question.qclass != CLASS.IN:
            return self._reply_with_error(request, RCODE.NOTIMP)
        if question.qtype not in (QTYPE.A, QTYPE.AAAA):
            return self._reply_with_error(request, RCODE.NOTIMP)
        if question.qtype == QTYPE.AAAA and not self._ipv6_available():
            return request.reply(ra=1).pack()

        try:
            route = self._resolve_route(str(question.qname).rstrip("."))
            self._route_table.put(route)
            address = route.synthetic_ipv4 if question.qtype == QTYPE.A else route.synthetic_ipv6
            ttl = min(self._ttl_seconds, max(0, route.expires_in))
            answer = request.reply(ra=1)
            answer.add_answer(RR(question.qname, question.qtype, CLASS.IN, ttl, A(address) if question.qtype == QTYPE.A else AAAA(address)))
            return answer.pack()
        except Exception:
            return self._reply_with_error(request, RCODE.SERVFAIL)

    @staticmethod
    def _error_response(request_id: int, rcode: int) -> bytes:
        return DNSRecord(DNSHeader(id=request_id, qr=1, ra=1, rcode=rcode)).pack()

    @staticmethod
    def _reply_with_error(request: DNSRecord, rcode: int) -> bytes:
        reply = request.reply(ra=1)
        reply.header.rcode = rcode
        return reply.pack()
