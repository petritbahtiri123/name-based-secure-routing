from __future__ import annotations

from dnslib import DNSRecord, QTYPE, RCODE

from nbsr.dns_stub import ClientRoute, DnsStub, RouteTable


def route_for(hostname: str) -> ClientRoute:
    assert hostname == "facebook.test"
    return ClientRoute(
        hostname=hostname,
        synthetic_ipv4="127.80.0.1",
        synthetic_ipv6="fd00:6e62:7372::1",
        route_binding="signed-route",
        expires_in=30,
    )


def test_dns_stub_returns_synthetic_a_record_only():
    table = RouteTable()
    stub = DnsStub(route_for, table, ttl_seconds=20)
    request = DNSRecord.question("facebook.test", "A")

    answer = DNSRecord.parse(stub.resolve_query(request.pack()))

    assert answer.header.rcode == RCODE.NOERROR
    assert answer.header.id == request.header.id
    assert len(answer.rr) == 1
    assert answer.rr[0].rtype == QTYPE.A
    assert str(answer.rr[0].rdata).startswith("127.80.")
    assert answer.rr[0].ttl == 20
    assert "203.0.113.10" not in str(answer)
    assert table.lookup("127.80.0.1") is not None


def test_dns_stub_returns_synthetic_aaaa_record_only():
    table = RouteTable()
    stub = DnsStub(route_for, table)

    answer = DNSRecord.parse(stub.resolve_query(DNSRecord.question("facebook.test", "AAAA").pack()))

    assert answer.header.rcode == RCODE.NOERROR
    assert len(answer.rr) == 1
    assert answer.rr[0].rtype == QTYPE.AAAA
    assert str(answer.rr[0].rdata) == "fd00:6e62:7372::1"
    assert "203.0.113.10" not in str(answer)


def test_dns_stub_returns_no_aaaa_record_when_ipv6_interception_is_unavailable():
    request = DNSRecord.question("facebook.test", "AAAA")
    stub = DnsStub(route_for, RouteTable(), ipv6_available=lambda: False)

    answer = DNSRecord.parse(stub.resolve_query(request.pack()))

    assert answer.header.rcode == RCODE.NOERROR
    assert answer.rr == []


def test_dns_stub_rejects_multiple_questions_with_formerr():
    request = DNSRecord.question("facebook.test", "A")
    request.add_question(DNSRecord.question("example.test", "A").questions[0])
    stub = DnsStub(route_for, RouteTable())

    answer = DNSRecord.parse(stub.resolve_query(request.pack()))

    assert answer.header.id == request.header.id
    assert answer.header.rcode == RCODE.FORMERR
    assert answer.rr == []


def test_dns_stub_rejects_non_in_a_queries_with_notimp():
    request = DNSRecord.question("facebook.test", "TXT")
    stub = DnsStub(route_for, RouteTable())

    answer = DNSRecord.parse(stub.resolve_query(request.pack()))

    assert answer.header.id == request.header.id
    assert answer.header.rcode == RCODE.NOTIMP
    assert answer.rr == []


def test_dns_stub_rejects_response_packets_without_resolving():
    calls: list[str] = []

    def resolver(hostname: str) -> ClientRoute:
        calls.append(hostname)
        return route_for(hostname)

    request = DNSRecord.question("facebook.test", "A")
    request.header.qr = 1
    answer = DNSRecord.parse(DnsStub(resolver, RouteTable()).resolve_query(request.pack()))

    assert answer.header.id == request.header.id
    assert answer.header.rcode == RCODE.FORMERR
    assert calls == []


def test_dns_stub_rejects_non_query_opcodes_without_resolving():
    calls: list[str] = []

    def resolver(hostname: str) -> ClientRoute:
        calls.append(hostname)
        return route_for(hostname)

    request = DNSRecord.question("facebook.test", "A")
    request.header.opcode = 5  # UPDATE
    answer = DNSRecord.parse(DnsStub(resolver, RouteTable()).resolve_query(request.pack()))

    assert answer.header.id == request.header.id
    assert answer.header.rcode == RCODE.NOTIMP
    assert calls == []


def test_dns_stub_returns_formerr_for_malformed_packet_with_original_id():
    stub = DnsStub(route_for, RouteTable())

    answer = DNSRecord.parse(stub.resolve_query(b"\xbe\xef\x01"))

    assert answer.header.id == 0xBEEF
    assert answer.header.rcode == RCODE.FORMERR


def test_dns_stub_returns_servfail_when_route_resolution_fails():
    def unavailable(_: str) -> ClientRoute:
        raise RuntimeError("route service is unavailable")

    request = DNSRecord.question("facebook.test", "A")
    stub = DnsStub(unavailable, RouteTable())

    answer = DNSRecord.parse(stub.resolve_query(request.pack()))

    assert answer.header.id == request.header.id
    assert answer.header.rcode == RCODE.SERVFAIL


def test_dns_stub_never_emits_a_non_synthetic_resolver_address():
    def public_route(hostname: str) -> ClientRoute:
        return ClientRoute(hostname, "203.0.113.10", "fd00:6e62:7372::1", "binding", 30)

    request = DNSRecord.question("facebook.test", "A")
    stub = DnsStub(public_route, RouteTable())

    answer = DNSRecord.parse(stub.resolve_query(request.pack()))

    assert answer.header.rcode == RCODE.SERVFAIL
    assert "203.0.113.10" not in str(answer)
