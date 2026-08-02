from __future__ import annotations

from dataclasses import FrozenInstanceError, replace

import pytest

import nbsr.two_operator_lab as wp7
from nbsr.two_operator_lab import AdmissionContext, LabRejected, OperatorProfile, RouteTrust


def digest(byte: str) -> str:
    return byte * 64


def profile_data(operator: str, *, identity: str = "1", policy: str = "2", audit: str = "3", **changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "operator_id": operator,
        "identity_fingerprint": digest(identity),
        "policy_fingerprint": digest(policy),
        "audit_fingerprint": digest(audit),
        "policy_digest": digest("4"),
        "gateway_profile_digest": digest("5"),
        "continuity_digest": digest("6"),
        "policy_version": 7,
    }
    value.update(changes)
    return value


def profiles() -> tuple[OperatorProfile, OperatorProfile]:
    return (
        OperatorProfile.from_dict(profile_data("isp-a")),
        OperatorProfile.from_dict(profile_data("isp-b", identity="a", policy="b", audit="c")),
    )


def context(source: OperatorProfile, destination: OperatorProfile, **changes: object) -> AdmissionContext:
    value: dict[str, object] = {
        "source_operator": source.operator_id,
        "destination_operator": destination.operator_id,
        "tenant_id": "tenant-a",
        "subscriber_pseudonym": digest("d"),
        "name_id": "payments",
        "route_id": "route-a",
        "service_id": "payments",
        "channel_id": "channel-a",
        "tunnel_id": "tunnel-a",
        "source_edge_id": "source-edge-a",
        "destination_edge_id": "destination-edge-b",
        "route_grant_digest": digest("e"),
        "channel_authority_digest": digest("7"),
        "exporter_binding_digest": digest("8"),
        "source_policy_digest": source.policy_digest,
        "destination_policy_digest": destination.policy_digest,
        "source_gateway_digest": source.gateway_profile_digest,
        "destination_gateway_digest": destination.gateway_profile_digest,
        "source_continuity_digest": source.continuity_digest,
        "destination_continuity_digest": destination.continuity_digest,
        "source_policy_version": source.policy_version,
        "destination_policy_version": destination.policy_version,
    }
    value.update(changes)
    return AdmissionContext(**value)  # type: ignore[arg-type]


def trust(source: OperatorProfile, destination: OperatorProfile, **changes: object) -> RouteTrust:
    value: dict[str, object] = {
        "source_operator": source.operator_id,
        "source_identity_fingerprint": source.identity_fingerprint,
        "destination_operator": destination.operator_id,
        "destination_identity_fingerprint": destination.identity_fingerprint,
        "route_id": "route-a",
        "service_id": "payments",
        "route_grant_digest": digest("e"),
    }
    value.update(changes)
    return RouteTrust(**value)  # type: ignore[arg-type]


def test_profiles_and_context_are_immutable_and_exactly_validate_trusted_operators() -> None:
    source, destination = profiles()
    candidate = context(source, destination)

    candidate.validate(source, destination, trust(source, destination))
    with pytest.raises(FrozenInstanceError):
        source.policy_version = 8  # type: ignore[misc]
    with pytest.raises(LabRejected, match="source operator"):
        replace(candidate, source_operator="forged-isp").validate(source, destination, trust(source, destination))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("operator_id", "ISP-A"),
        ("operator_id", "isp_a"),
        ("operator_id", "a" * 65),
        ("identity_fingerprint", digest("A")),
        ("policy_version", 0),
        ("policy_version", 2**64),
        ("policy_version", True),
    ],
)
def test_profile_rejects_noncanonical_ids_fingerprints_and_versions(field: str, value: object) -> None:
    with pytest.raises(LabRejected):
        OperatorProfile.from_dict(profile_data("isp-a", **{field: value}))


def test_profile_rejects_unknown_fields_and_purpose_confused_fingerprints() -> None:
    with pytest.raises(LabRejected, match="exactly"):
        OperatorProfile.from_dict(profile_data("isp-a", unexpected=True))
    with pytest.raises(LabRejected, match="unique"):
        OperatorProfile.from_dict(profile_data("isp-a", policy="1"))


@pytest.mark.parametrize(
    "values",
    [
        profile_data("ISP-A"),
        profile_data("isp-a", policy="1"),
    ],
)
def test_direct_profile_construction_enforces_field_and_key_purpose_invariants(values: dict[str, object]) -> None:
    with pytest.raises(LabRejected):
        OperatorProfile(**values)  # type: ignore[arg-type]


def test_trust_rejects_duplicate_fingerprints_across_operator_key_purposes() -> None:
    source = OperatorProfile.from_dict(profile_data("isp-a"))
    destination = OperatorProfile.from_dict(profile_data("isp-b", identity="a", policy="1", audit="c"))

    with pytest.raises(LabRejected, match="unique"):
        RouteTrust.from_profiles(source, destination, route_id="route-a", service_id="payments", route_grant_digest=digest("e"))


def test_context_rejects_stale_policy_versions_and_substituted_trust_tuple() -> None:
    source, destination = profiles()
    candidate = context(source, destination)

    with pytest.raises(LabRejected, match="policy version"):
        replace(candidate, source_policy_version=6).validate(source, destination, trust(source, destination))
    with pytest.raises(LabRejected, match="trust"):
        candidate.validate(source, destination, trust(source, destination, route_id="route-b"))


def test_context_rejects_substituted_destination_gateway_profile() -> None:
    source, destination = profiles()

    with pytest.raises(LabRejected, match="destination gateway"):
        context(source, destination, destination_gateway_digest=digest("f")).validate(source, destination, trust(source, destination))


def test_verified_authority_is_local_purpose_separated_and_lifecycle_bounded() -> None:
    authority = wp7.VerifiedAuthority(
        route_grant_digest=digest("e"),
        channel_authority_digest=digest("7"),
        exporter_binding_digest=digest("8"),
        source_edge_id="source-edge-a",
        destination_edge_id="destination-edge-b",
        source_gateway_digest=digest("5"),
        destination_gateway_digest=digest("9"),
        source_gateway_conformant=True,
        destination_gateway_conformant=True,
        source_continuity_digest=digest("6"),
        destination_continuity_digest=digest("a"),
        source_continuity_status="current",
        destination_continuity_status="current",
        issued_at_ms=10,
        expires_at_ms=20_000,
    )

    assert authority.expires_at_ms == 20_000
    with pytest.raises(LabRejected, match="purpose"):
        replace(authority, exporter_binding_digest=authority.route_grant_digest)
    with pytest.raises(LabRejected, match="continuity status"):
        replace(authority, destination_continuity_status="accepted")
    with pytest.raises(LabRejected, match="lifetime"):
        replace(authority, issued_at_ms=20_001)
