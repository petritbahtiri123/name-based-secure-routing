from datetime import UTC, datetime, timedelta

import pytest

from nbsr.name_model import normalize_hostname
from nbsr.synthetic import SyntheticAddressPool, SyntheticPoolExhausted


def test_normalizes_dns_name():
    assert normalize_hostname("Facebook.COM.") == "facebook.com"


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
