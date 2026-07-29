from __future__ import annotations

import pytest

from nbsr.legacy_origin import (
    LegacyDnsResult,
    LegacyDnsSnapshot,
    LegacyOriginCache,
    LegacyOriginCapacityError,
    LegacyOriginRequest,
    LegacyOriginUnavailable,
    LegacyOriginValidationError,
    derive_originset,
)
from nbsr.originset import DnssecStatus, OriginEndpoint, PublicationMode


NOW = 1_785_000_000


def request(**changes: object) -> LegacyOriginRequest:
    values: dict[str, object] = {
        "service_name": "api.example.test",
        "service_id": "svc_api",
        "service_record_generation": 42,
        "issuer_id": b"resolver-a",
        "origin_name": "origin.example.test",
        "allowed_ports": [443],
        "allowed_networks": ["192.0.2.0/24", "2001:db8::/32"],
        "max_endpoints": 32,
    }
    values.update(changes)
    return LegacyOriginRequest(**values)  # type: ignore[arg-type]


def endpoint(address: str = "192.0.2.10", port: int = 443) -> OriginEndpoint:
    return OriginEndpoint(address=address, port=port)


def snapshot(**changes: object) -> LegacyDnsSnapshot:
    values: dict[str, object] = {
        "result": LegacyDnsResult.POSITIVE,
        "requested_name": "api.example.test",
        "origin_name": "origin.example.test",
        "endpoints": [endpoint("2001:db8::10"), endpoint()],
        "ttl_seconds": 60,
        "dnssec_status": DnssecStatus.SECURE,
        "observed_at": NOW,
    }
    values.update(changes)
    return LegacyDnsSnapshot(**values)  # type: ignore[arg-type]


def allow(_request: LegacyOriginRequest, _endpoint: OriginEndpoint) -> bool:
    return True


def test_positive_snapshot_derives_deterministic_bounded_originset() -> None:
    candidate = derive_originset(
        request(),
        snapshot(),
        sequence=1,
        previous_digest=None,
        validator=allow,
    )

    assert candidate.service_id == "svc_api"
    assert candidate.service_record_generation == 42
    assert candidate.origin_generation == 1
    assert candidate.sequence == 1
    assert candidate.publication_mode is PublicationMode.LEGACY_DNS
    assert [item.address for item in candidate.endpoints] == [
        "192.0.2.10",
        "2001:db8::10",
    ]
    assert candidate.not_before == NOW
    assert candidate.expires_at == NOW + 360


def test_source_ttl_is_clamped_without_becoming_authorization_lifetime() -> None:
    candidate = derive_originset(
        request(),
        snapshot(ttl_seconds=3_600),
        sequence=1,
        previous_digest=None,
        validator=allow,
    )

    assert candidate.expires_at == NOW + 600


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("service_name", "API.example.test"),
        ("service_id", "Upper"),
        ("service_record_generation", True),
        ("issuer_id", b""),
        ("origin_name", "origin.example.test."),
        ("allowed_ports", [True]),
        ("allowed_ports", [0]),
        ("allowed_networks", ["0.0.0.0/0"]),
        ("max_endpoints", 0),
        ("max_endpoints", 33),
    ),
)
def test_request_rejects_ambiguous_types_and_unsafe_bounds(
    field: str,
    value: object,
) -> None:
    with pytest.raises(LegacyOriginValidationError):
        request(**{field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("requested_name", "API.example.test"),
        ("origin_name", "origin.example.test."),
        ("ttl_seconds", True),
        ("ttl_seconds", 0),
        ("observed_at", False),
        ("endpoints", "192.0.2.10"),
    ),
)
def test_snapshot_rejects_ambiguous_types_and_invalid_bounds(
    field: str,
    value: object,
) -> None:
    with pytest.raises(LegacyOriginValidationError):
        snapshot(**{field: value})


def test_conversion_rejects_policy_mismatch_and_excess_endpoints() -> None:
    invalid_cases = (
        snapshot(requested_name="other.example.test"),
        snapshot(origin_name="other-origin.example.test"),
        snapshot(endpoints=[endpoint(port=80)]),
        snapshot(endpoints=[endpoint("198.51.100.10")]),
        snapshot(endpoints=[endpoint(f"192.0.2.{index}") for index in range(1, 4)]),
    )

    for candidate_snapshot in invalid_cases:
        with pytest.raises(LegacyOriginValidationError):
            derive_originset(
                request(max_endpoints=2),
                candidate_snapshot,
                sequence=1,
                previous_digest=None,
                validator=allow,
            )


def test_conversion_rejects_bogus_nonpositive_and_validator_denial_without_ip_leak() -> None:
    invalid_cases = (
        snapshot(dnssec_status=DnssecStatus.BOGUS),
        snapshot(
            result=LegacyDnsResult.TEMPORARY_FAILURE,
            endpoints=[],
        ),
    )

    for candidate_snapshot in invalid_cases:
        with pytest.raises(LegacyOriginValidationError) as rejected:
            derive_originset(
                request(),
                candidate_snapshot,
                sequence=1,
                previous_digest=None,
                validator=allow,
            )
        assert "192.0.2.10" not in str(rejected.value)

    with pytest.raises(LegacyOriginValidationError) as denied:
        derive_originset(
            request(),
            snapshot(),
            sequence=1,
            previous_digest=None,
            validator=lambda _request, _endpoint: False,
        )
    assert "192.0.2.10" not in str(denied.value)


def temporary_snapshot(observed_at: int) -> LegacyDnsSnapshot:
    return snapshot(
        result=LegacyDnsResult.TEMPORARY_FAILURE,
        endpoints=[],
        ttl_seconds=1,
        observed_at=observed_at,
    )


def authenticated_negative(observed_at: int) -> LegacyDnsSnapshot:
    return snapshot(
        result=LegacyDnsResult.AUTHENTICATED_NEGATIVE,
        endpoints=[],
        ttl_seconds=30,
        observed_at=observed_at,
    )


def test_successful_refresh_sets_independent_freshness_and_grace_deadlines() -> None:
    cache = LegacyOriginCache()

    view = cache.apply_snapshot(request(), snapshot(), validator=allow)

    assert view.fresh is True
    assert view.originset.sequence == 1
    assert view.dns_fresh_until == NOW + 60
    assert view.last_known_good_until == NOW + 360
    assert view.next_refresh_at == NOW + 48


def test_temporary_failure_uses_last_known_good_only_within_grace() -> None:
    cache = LegacyOriginCache()
    cache.apply_snapshot(request(), snapshot(), validator=allow)

    stale = cache.apply_snapshot(
        request(),
        temporary_snapshot(NOW + 61),
        validator=allow,
    )

    assert stale.fresh is False
    assert stale.originset.sequence == 1
    assert stale.next_refresh_at == NOW + 62
    with pytest.raises(LegacyOriginUnavailable):
        cache.lookup(request(), now=NOW + 360)


def test_temporary_failure_retry_backoff_is_bounded() -> None:
    cache = LegacyOriginCache()
    cache.apply_snapshot(request(), snapshot(), validator=allow)

    observed = NOW + 61
    expected_delays = (1, 2, 4, 8, 16, 30, 30)
    for offset, expected_delay in enumerate(expected_delays):
        view = cache.apply_snapshot(
            request(),
            temporary_snapshot(observed + offset),
            validator=allow,
        )
        assert view.next_refresh_at == observed + offset + expected_delay


def test_successful_refresh_replaces_atomically_and_chains_digest() -> None:
    cache = LegacyOriginCache()
    first = cache.apply_snapshot(request(), snapshot(), validator=allow)

    second = cache.apply_snapshot(
        request(),
        snapshot(
            endpoints=[endpoint("192.0.2.11")],
            observed_at=NOW + 50,
        ),
        validator=allow,
    )

    assert second.originset.sequence == 2
    assert second.originset.previous_digest == first.originset.content_digest
    assert [item.address for item in second.originset.endpoints] == ["192.0.2.11"]


def test_repeated_observation_is_idempotent_and_different_content_equivocates() -> None:
    cache = LegacyOriginCache()
    first = cache.apply_snapshot(request(), snapshot(), validator=allow)

    repeated = cache.apply_snapshot(request(), snapshot(), validator=allow)

    assert repeated.originset is first.originset
    assert repeated.originset.sequence == 1
    with pytest.raises(LegacyOriginUnavailable):
        cache.apply_snapshot(
            request(),
            snapshot(endpoints=[endpoint("192.0.2.11")]),
            validator=allow,
        )


def test_older_observation_fails_closed() -> None:
    cache = LegacyOriginCache()
    cache.apply_snapshot(request(), snapshot(), validator=allow)

    with pytest.raises(LegacyOriginUnavailable):
        cache.apply_snapshot(
            request(),
            snapshot(observed_at=NOW - 1),
            validator=allow,
        )


@pytest.mark.parametrize(
    "failure",
    (
        authenticated_negative(NOW + 10),
        snapshot(
            dnssec_status=DnssecStatus.BOGUS,
            observed_at=NOW + 10,
        ),
        snapshot(
            dnssec_status=DnssecStatus.INSECURE,
            observed_at=NOW + 10,
        ),
        temporary_snapshot(NOW + 10),
    ),
)
def test_hard_failure_invalidates_new_use_immediately(
    failure: LegacyDnsSnapshot,
) -> None:
    cache = LegacyOriginCache()
    cache.apply_snapshot(request(), snapshot(), validator=allow)

    if failure.result is LegacyDnsResult.TEMPORARY_FAILURE:
        failure = snapshot(
            result=LegacyDnsResult.TEMPORARY_FAILURE,
            endpoints=[],
            ttl_seconds=1,
            dnssec_status=DnssecStatus.BOGUS,
            observed_at=NOW + 10,
        )
    with pytest.raises(LegacyOriginUnavailable) as unavailable:
        cache.apply_snapshot(request(), failure, validator=allow)
    with pytest.raises(LegacyOriginUnavailable):
        cache.lookup(request(), now=NOW + 11)

    assert "192.0.2.10" not in str(unavailable.value)


def test_tombstone_prevents_same_state_resurrection() -> None:
    cache = LegacyOriginCache()
    first = cache.apply_snapshot(request(), snapshot(), validator=allow)
    with pytest.raises(LegacyOriginUnavailable):
        cache.apply_snapshot(
            request(),
            authenticated_negative(NOW + 10),
            validator=allow,
        )

    restored = cache.apply_snapshot(
        request(),
        snapshot(observed_at=NOW + 20),
        validator=allow,
    )

    assert restored.originset.sequence == 2
    assert restored.originset.previous_digest == first.originset.content_digest


def test_cache_capacity_fails_closed_without_evicting_security_state() -> None:
    cache = LegacyOriginCache(max_entries=1)
    first_request = request()
    cache.apply_snapshot(first_request, snapshot(), validator=allow)

    with pytest.raises(LegacyOriginCapacityError):
        cache.apply_snapshot(
            request(service_id="svc_other", issuer_id=b"resolver-b"),
            snapshot(),
            validator=allow,
        )

    assert cache.lookup(first_request, now=NOW + 1).originset.service_id == "svc_api"
