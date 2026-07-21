from datetime import UTC, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from time import sleep

import pytest

from nbsr.name_model import normalize_hostname
from nbsr.synthetic import SyntheticAddressPool, SyntheticPoolExhausted


def test_normalizes_dns_name():
    assert normalize_hostname("Facebook.COM.") == "facebook.com"


def test_rejects_non_loopback_ipv4_pool():
    with pytest.raises(ValueError, match="loopback"):
        SyntheticAddressPool("10.0.0.0/29", "fd00:6e62:7372::/125", ttl_seconds=60)


def test_rejects_ipv6_pool_outside_nbsr_synthetic_prefix():
    with pytest.raises(ValueError, match="NBSR synthetic ULA prefix"):
        SyntheticAddressPool("127.80.0.0/29", "fd00:6e62:7373::/125", ttl_seconds=60)


def test_rejects_invalid_dns_names():
    for value in ("", ".", "facebook..test", "-facebook.test", "facebook-.test", "face_book.test"):
        with pytest.raises(ValueError, match="Invalid NBSR hostname"):
            normalize_hostname(value)


def test_reuses_live_mapping_and_never_contains_origin_address():
    pool = SyntheticAddressPool("127.80.0.0/29", "fd00:6e62:7372::/125", ttl_seconds=60)

    first = pool.allocate("facebook.test")
    second = pool.allocate("facebook.test")

    assert first == second
    assert first.ipv4.startswith("127.80.")
    assert "203.0.113.10" not in repr(first)


def test_lookup_returns_mapping_for_both_synthetic_addresses():
    pool = SyntheticAddressPool("127.80.0.0/29", "fd00:6e62:7372::/125", ttl_seconds=60)
    mapping = pool.allocate("facebook.test")

    assert pool.lookup(mapping.ipv4) == mapping
    assert pool.lookup(mapping.ipv6) == mapping


def test_expired_mapping_is_removed_from_forward_and_reverse_indexes():
    now = datetime(2026, 7, 20, tzinfo=UTC)
    pool = SyntheticAddressPool("127.80.0.0/29", "fd00:6e62:7372::/125", ttl_seconds=60)
    mapping = pool.allocate("facebook.test", now=now)

    assert pool.lookup(mapping.ipv4, now=now + timedelta(seconds=60)) is None
    assert pool.lookup(mapping.ipv6, now=now + timedelta(seconds=60)) is None
    replacement = pool.allocate("facebook.test", now=now + timedelta(seconds=60))

    assert pool.lookup(replacement.ipv4, now=now + timedelta(seconds=60)) == replacement


def test_pool_exhaustion_fails_closed():
    pool = SyntheticAddressPool("127.80.0.0/30", "fd00:6e62:7372::/126", ttl_seconds=60)
    pool.allocate("one.test")
    pool.allocate("two.test")

    with pytest.raises(SyntheticPoolExhausted):
        pool.allocate("three.test")


def test_reused_mapping_is_renewed_for_the_requested_admission_lifetime():
    now = datetime(2026, 7, 20, tzinfo=UTC)
    pool = SyntheticAddressPool("127.80.0.0/30", "fd00:6e62:7372::/126", ttl_seconds=60)
    first = pool.allocate("facebook.test", now=now)

    renewed = pool.allocate(
        "facebook.test",
        now=now + timedelta(seconds=59),
        minimum_valid_for_seconds=60,
    )

    assert renewed.ipv4 == first.ipv4
    assert renewed.ipv6 == first.ipv6
    assert renewed.expires_at == now + timedelta(seconds=119)
    assert pool.lookup(first.ipv4, now=now + timedelta(seconds=61)) == renewed
    other = pool.allocate("other.test", now=now + timedelta(seconds=61))
    assert (other.ipv4, other.ipv6) != (renewed.ipv4, renewed.ipv6)


def test_concurrent_allocations_never_share_a_synthetic_pair():
    pool = SyntheticAddressPool("127.80.0.0/29", "fd00:6e62:7372::/125", ttl_seconds=60)

    class SlowContainsDict(dict):
        def __contains__(self, key):
            present = super().__contains__(key)
            sleep(0.02)
            return present

    pool._by_address = SlowContainsDict()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = executor.map(pool.allocate, ("one.test", "two.test"))

    assert (first.ipv4, first.ipv6) != (second.ipv4, second.ipv6)
