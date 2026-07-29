from __future__ import annotations

import pytest

from nbsr.legacy_origin import (
    LegacyDnsResult,
    LegacyDnsSnapshot,
    LegacyOriginRequest,
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
