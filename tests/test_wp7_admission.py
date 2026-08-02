"""Admission contracts for the deterministic WP7 two-operator lab."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from hashlib import sha256

import pytest

from nbsr.two_operator_lab import AdmissionContext, LabRejected, OperatorProfile, RouteTrust, TwoOperatorLab


def digest(value: str) -> str:
    return sha256(value.encode("ascii")).hexdigest()


def profile(operator_id: str, prefix: str) -> OperatorProfile:
    return OperatorProfile(
        operator_id=operator_id,
        identity_fingerprint=digest(f"{prefix}-identity"),
        policy_fingerprint=digest(f"{prefix}-policy-key"),
        audit_fingerprint=digest(f"{prefix}-audit"),
        policy_digest=digest(f"{prefix}-policy"),
        gateway_profile_digest=digest(f"{prefix}-gateway"),
        continuity_digest=digest(f"{prefix}-continuity"),
        policy_version=7,
    )


def request(source: OperatorProfile, destination: OperatorProfile, **changes: object) -> AdmissionContext:
    values: dict[str, object] = {
        "source_operator": source.operator_id,
        "destination_operator": destination.operator_id,
        "tenant_id": "tenant-a",
        "subscriber_pseudonym": digest("subscriber-a"),
        "name_id": "payments",
        "route_id": "route-a",
        "service_id": "payments",
        "channel_id": "channel-a",
        "tunnel_id": "tunnel-a",
        "source_edge_id": "source-edge-a",
        "destination_edge_id": "destination-edge-b",
        "route_grant_digest": digest("grant-a"),
        "source_policy_digest": source.policy_digest,
        "destination_policy_digest": destination.policy_digest,
        "source_gateway_digest": source.gateway_profile_digest,
        "destination_gateway_digest": destination.gateway_profile_digest,
        "source_continuity_digest": source.continuity_digest,
        "destination_continuity_digest": destination.continuity_digest,
        "source_policy_version": source.policy_version,
        "destination_policy_version": destination.policy_version,
    }
    values.update(changes)
    return AdmissionContext(**values)  # type: ignore[arg-type]


def lab_and_request() -> tuple[TwoOperatorLab, AdmissionContext]:
    source = profile("isp-a", "source")
    destination = profile("isp-b", "destination")
    candidate = request(source, destination)
    trust = RouteTrust.from_profiles(
        source,
        destination,
        route_id=candidate.route_id,
        service_id=candidate.service_id,
        route_grant_digest=candidate.route_grant_digest,
    )
    return TwoOperatorLab(source, destination, trust, candidate), candidate


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("source_operator", "forged-isp", "source-operator-mismatch"),
        ("tenant_id", "forged-tenant", "source-tenant-mismatch"),
        ("subscriber_pseudonym", digest("forged-subscriber"), "source-subscriber-mismatch"),
        ("name_id", "forged-name", "source-name-mismatch"),
        ("source_edge_id", "forged-source-edge", "source-edge-mismatch"),
        ("source_policy_digest", digest("stale-source-policy"), "source-policy-mismatch"),
        ("source_policy_version", 8, "source-policy-mismatch"),
        ("source_gateway_digest", digest("forged-source-gateway"), "source-gateway-mismatch"),
        ("source_continuity_digest", digest("denied-source-continuity"), "source-continuity-denied"),
        ("route_grant_digest", digest("substituted-grant"), "source-route-grant-mismatch"),
        ("route_id", "substituted-route", "source-route-grant-mismatch"),
        ("service_id", "substituted-service", "source-route-grant-mismatch"),
        ("destination_operator", "forged-isp", "destination-operator-mismatch"),
        ("channel_id", "forged-channel", "destination-channel-mismatch"),
        ("tunnel_id", "forged-tunnel", "destination-tunnel-mismatch"),
        ("destination_edge_id", "forged-destination-edge", "destination-edge-mismatch"),
        ("destination_policy_digest", digest("stale-destination-policy"), "destination-policy-mismatch"),
        ("destination_policy_version", 8, "destination-policy-mismatch"),
        ("destination_gateway_digest", digest("forged-destination-gateway"), "destination-gateway-mismatch"),
        ("destination_continuity_digest", digest("denied-destination-continuity"), "destination-continuity-denied"),
    ],
)
def test_admission_rejects_each_spoofed_context_without_state_mutation(field: str, value: object, code: str) -> None:
    lab, candidate = lab_and_request()

    with pytest.raises(LabRejected) as rejected:
        lab.admit(replace(candidate, **{field: value}), now_ms=10)

    assert rejected.value.code == code
    assert lab.admitted_grant_count == 0


def test_source_gate_precedes_destination_gate() -> None:
    lab, candidate = lab_and_request()

    with pytest.raises(LabRejected) as rejected:
        lab.admit(replace(candidate, name_id="forged-name", channel_id="forged-channel"), now_ms=10)

    assert rejected.value.code == "source-name-mismatch"
    assert lab.admitted_grant_count == 0


def test_rejected_request_does_not_consume_a_grant_and_valid_sibling_succeeds() -> None:
    lab, candidate = lab_and_request()

    with pytest.raises(LabRejected) as rejected:
        lab.admit(replace(candidate, destination_edge_id="forged-destination-edge"), now_ms=10)
    assert rejected.value.code == "destination-edge-mismatch"
    assert lab.admitted_grant_count == 0

    receipt = lab.admit(candidate, now_ms=11)

    assert receipt.admitted_at_ms == 11
    assert receipt.source_operator == "isp-a"
    assert receipt.destination_operator == "isp-b"
    assert receipt.route_grant_digest == candidate.route_grant_digest
    assert lab.admitted_grant_count == 1


def test_admission_rejects_replayed_exact_grant_after_a_success() -> None:
    lab, candidate = lab_and_request()
    lab.admit(candidate, now_ms=10)

    with pytest.raises(LabRejected) as rejected:
        lab.admit(candidate, now_ms=11)

    assert rejected.value.code == "destination-route-grant-replayed"
    assert lab.admitted_grant_count == 1


def test_admission_rejects_non_uint64_clock_without_consuming_a_grant() -> None:
    lab, candidate = lab_and_request()

    with pytest.raises(LabRejected) as rejected:
        lab.admit(candidate, now_ms=True)

    assert rejected.value.code == "admission-clock-invalid"
    assert lab.admitted_grant_count == 0


def test_destination_gate_independently_rejects_its_owned_context_and_trust() -> None:
    lab, candidate = lab_and_request()

    cases = [
        ("tenant_id", "forged-tenant", "destination-tenant-mismatch"),
        ("service_id", "substituted-service", "destination-service-mismatch"),
        ("route_id", "substituted-route", "destination-route-mismatch"),
        ("route_grant_digest", digest("substituted-grant"), "destination-route-trust-mismatch"),
    ]
    for field, value, code in cases:
        with pytest.raises(LabRejected) as rejected:
            lab.destination_gate(replace(candidate, **{field: value}))
        assert rejected.value.code == code


def test_trusted_lab_configuration_cannot_be_reassigned_after_construction() -> None:
    lab, candidate = lab_and_request()

    with pytest.raises(FrozenInstanceError):
        lab.expected_context = candidate  # type: ignore[misc]
