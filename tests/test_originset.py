from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from nbsr.originset import (
    AuthorityKind,
    DerivedOriginSet,
    DnssecStatus,
    OriginEndpoint,
    OriginSetEquivocationError,
    OriginSetStaleError,
    OriginSetValidationError,
    PublicationMode,
    accept_originset,
    make_tombstone,
)


NOW = 1_785_000_000


def endpoint(address: str = "192.0.2.10", **changes: object) -> OriginEndpoint:
    values: dict[str, object] = {
        "address": address,
        "port": 443,
        "transport": "tcp",
        "priority": 10,
        "weight": 20,
        "region": "eu",
        "locality": "bud",
    }
    values.update(changes)
    return OriginEndpoint(**values)  # type: ignore[arg-type]


def originset(**changes: object) -> DerivedOriginSet:
    values: dict[str, object] = {
        "service_id": "svc_api",
        "service_record_generation": 42,
        "origin_generation": 7,
        "sequence": 9,
        "endpoints": [endpoint()],
        "publication_mode": PublicationMode.LEGACY_DNS,
        "authority_kind": AuthorityKind.LOCAL_DERIVATION,
        "issuer_id": b"resolver-a",
        "not_before": NOW,
        "expires_at": NOW + 60,
        "dnssec_status": DnssecStatus.SECURE,
        "previous_digest": None,
    }
    values.update(changes)
    return DerivedOriginSet(**values)  # type: ignore[arg-type]


def test_models_copy_collections_normalize_endpoints_and_are_immutable() -> None:
    endpoints = [endpoint("2001:db8::10"), endpoint()]
    candidate = originset(endpoints=endpoints)
    endpoints.append(endpoint("192.0.2.11"))

    assert [item.address for item in candidate.endpoints] == [
        "192.0.2.10",
        "2001:db8::10",
    ]
    assert len(candidate.endpoints) == 2
    with pytest.raises((FrozenInstanceError, AttributeError)):
        candidate.sequence = 10  # type: ignore[misc]
    with pytest.raises((FrozenInstanceError, AttributeError)):
        candidate.endpoints[0].port = 8443  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("port", True),
        ("port", 0),
        ("port", 65_536),
        ("priority", -1),
        ("weight", 65_536),
        ("transport", "udp"),
        ("region", "Upper"),
        ("address", "origin.example.com"),
    ),
)
def test_endpoint_rejects_wrong_types_bounds_and_unsupported_values(
    field: str,
    value: object,
) -> None:
    with pytest.raises(OriginSetValidationError):
        endpoint(**{field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("service_id", "Upper"),
        ("service_record_generation", True),
        ("service_record_generation", 0),
        ("origin_generation", 2**64),
        ("sequence", 0),
        ("issuer_id", b""),
        ("issuer_id", b"k" * 65),
        ("not_before", False),
        ("expires_at", NOW),
        ("previous_digest", b"short"),
    ),
)
def test_originset_rejects_wrong_types_and_bounds(field: str, value: object) -> None:
    with pytest.raises(OriginSetValidationError):
        originset(**{field: value})


def test_originset_bounds_endpoint_count_and_identity_duplicates() -> None:
    with pytest.raises(OriginSetValidationError):
        originset(endpoints=[])
    with pytest.raises(OriginSetValidationError):
        originset(
            endpoints=[endpoint(f"192.0.2.{index}", priority=0, weight=0) for index in range(1, 34)],
        )
    with pytest.raises(OriginSetValidationError):
        originset(
            endpoints=[
                endpoint(priority=0, weight=0),
                endpoint(priority=1, weight=1),
            ],
        )


@pytest.mark.parametrize(
    ("mode", "authority", "dnssec_status"),
    (
        (PublicationMode.LEGACY_DNS, AuthorityKind.OWNER, None),
        (PublicationMode.HYBRID, AuthorityKind.OWNER, None),
        (PublicationMode.NBSR_NATIVE, AuthorityKind.LOCAL_DERIVATION, DnssecStatus.SECURE),
        (PublicationMode.LEGACY_DNS, AuthorityKind.LOCAL_DERIVATION, None),
        (PublicationMode.LEGACY_DNS, AuthorityKind.LOCAL_DERIVATION, DnssecStatus.BOGUS),
    ),
)
def test_originset_enforces_mode_specific_authority(
    mode: PublicationMode,
    authority: AuthorityKind,
    dnssec_status: DnssecStatus | None,
) -> None:
    with pytest.raises(OriginSetValidationError):
        originset(
            publication_mode=mode,
            authority_kind=authority,
            dnssec_status=dnssec_status,
        )


def test_originset_has_a_stable_internal_digest_fixture() -> None:
    candidate = originset(
        endpoints=[endpoint("2001:db8::10"), endpoint()],
    )
    same_content = originset(
        endpoints=[endpoint(), endpoint("2001:0db8:0:0:0:0:0:10")],
    )
    changed_content = originset(
        endpoints=[endpoint(), endpoint("2001:db8::10", weight=21)],
    )

    assert candidate.content_digest.hex() == ("2d7fc8fd214dbf99ba0dc6c7418aa2cde2d34d4c569559bfe010e1f4c34c2322")
    assert same_content.content_digest == candidate.content_digest
    assert changed_content.content_digest != candidate.content_digest


def test_acceptance_is_idempotent_and_requires_digest_continuity() -> None:
    current = originset()

    assert accept_originset(originset(), current=current) is current
    successor = originset(
        sequence=10,
        previous_digest=current.content_digest,
    )
    assert accept_originset(successor, current=current) is successor

    with pytest.raises(OriginSetValidationError):
        accept_originset(originset(sequence=10), current=current)
    with pytest.raises(OriginSetValidationError):
        accept_originset(
            originset(sequence=10, previous_digest=b"x" * 32),
            current=current,
        )


def test_acceptance_rejects_stale_and_equivocated_candidates() -> None:
    current = originset()

    with pytest.raises(OriginSetStaleError):
        accept_originset(originset(sequence=8), current=current)
    with pytest.raises(OriginSetStaleError):
        accept_originset(
            originset(origin_generation=6, sequence=100),
            current=current,
        )
    with pytest.raises(OriginSetStaleError):
        accept_originset(
            originset(origin_generation=8, sequence=8),
            current=current,
        )
    with pytest.raises(OriginSetEquivocationError):
        accept_originset(
            originset(endpoints=[endpoint(weight=21)]),
            current=current,
        )


def test_tombstone_prevents_resurrection_and_allows_a_chained_successor() -> None:
    removed = originset()
    tombstone = make_tombstone(removed)

    with pytest.raises(OriginSetStaleError):
        accept_originset(originset(), tombstone=tombstone)
    with pytest.raises(OriginSetEquivocationError):
        accept_originset(
            originset(endpoints=[endpoint(weight=21)]),
            tombstone=tombstone,
        )

    successor = originset(
        sequence=10,
        previous_digest=removed.content_digest,
    )
    assert accept_originset(successor, tombstone=tombstone) is successor


def test_validity_window_is_checked_without_reusing_dns_ttl() -> None:
    candidate = originset()

    candidate.require_valid_at(NOW)
    candidate.require_valid_at(NOW + 59)
    with pytest.raises(OriginSetStaleError):
        candidate.require_valid_at(NOW - 1)
    with pytest.raises(OriginSetStaleError):
        candidate.require_valid_at(NOW + 60)
