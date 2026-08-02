"""Regression contracts for independently confirmed WP7 review findings."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

import pytest

import nbsr.two_operator_lab as wp7


def digest(value: str) -> str:
    return sha256(value.encode("ascii")).hexdigest()


def build_lab(
    *,
    limit_changes: dict[str, int] | None = None,
    source_audit_capacity: int = 16,
    destination_audit_capacity: int = 16,
    authority_changes: dict[str, object] | None = None,
) -> tuple[wp7.TwoOperatorLab, wp7.AdmissionContext, wp7.VerifiedAuthority]:
    source = wp7.OperatorProfile(
        operator_id="isp-a",
        identity_fingerprint=digest("source-identity"),
        policy_fingerprint=digest("source-policy-key"),
        audit_fingerprint=digest("source-audit-key"),
        policy_digest=digest("source-policy"),
        gateway_profile_digest=digest("source-gateway"),
        continuity_digest=digest("source-continuity"),
        policy_version=1,
    )
    destination = wp7.OperatorProfile(
        operator_id="isp-b",
        identity_fingerprint=digest("destination-identity"),
        policy_fingerprint=digest("destination-policy-key"),
        audit_fingerprint=digest("destination-audit-key"),
        policy_digest=digest("destination-policy"),
        gateway_profile_digest=digest("destination-gateway"),
        continuity_digest=digest("destination-continuity"),
        policy_version=1,
    )
    request = wp7.AdmissionContext(
        source_operator="isp-a",
        destination_operator="isp-b",
        tenant_id="tenant-a",
        subscriber_pseudonym=digest("subscriber-a"),
        name_id="payments",
        route_id="route-a",
        service_id="payments",
        channel_id="channel-a",
        tunnel_id="tunnel-a",
        source_edge_id="source-edge-a",
        destination_edge_id="destination-edge-b",
        route_grant_digest=digest("grant-a"),
        channel_authority_digest=digest("channel-authority-a"),
        exporter_binding_digest=digest("exporter-binding-a"),
        source_policy_digest=source.policy_digest,
        destination_policy_digest=destination.policy_digest,
        source_gateway_digest=source.gateway_profile_digest,
        destination_gateway_digest=destination.gateway_profile_digest,
        source_continuity_digest=source.continuity_digest,
        destination_continuity_digest=destination.continuity_digest,
        source_policy_version=1,
        destination_policy_version=1,
    )
    trust = wp7.RouteTrust.from_profiles(
        source,
        destination,
        route_id=request.route_id,
        service_id=request.service_id,
        route_grant_digest=request.route_grant_digest,
    )
    authority_values: dict[str, object] = {
        "route_grant_digest": request.route_grant_digest,
        "channel_authority_digest": request.channel_authority_digest,
        "exporter_binding_digest": request.exporter_binding_digest,
        "source_edge_id": request.source_edge_id,
        "destination_edge_id": request.destination_edge_id,
        "source_gateway_digest": request.source_gateway_digest,
        "destination_gateway_digest": request.destination_gateway_digest,
        "source_gateway_conformant": True,
        "destination_gateway_conformant": True,
        "source_continuity_digest": request.source_continuity_digest,
        "destination_continuity_digest": request.destination_continuity_digest,
        "source_continuity_status": "current",
        "destination_continuity_status": "current",
        "issued_at_ms": 0,
        "expires_at_ms": 60_000,
    }
    authority_values.update(authority_changes or {})
    authority = wp7.VerifiedAuthority(**authority_values)  # type: ignore[arg-type]
    limit_values = {
        "client_capacity": 8,
        "name_capacity": 8,
        "route_capacity": 8,
        "service_capacity": 8,
        "channel_capacity": 8,
        "tunnel_capacity": 8,
        "operator_capacity": 8,
        "refill_per_ms": 1,
        "max_buckets": 64,
        "max_active_allocations": 32,
    }
    limit_values.update(limit_changes or {})
    lab = wp7.TwoOperatorLab(
        source,
        destination,
        trust,
        request,
        verified_authority=authority,
        limit_profile=wp7.LimitProfile(**limit_values),
        source_audit_capacity=source_audit_capacity,
        destination_audit_capacity=destination_audit_capacity,
        connector_id="isp-b-connector",
        private_destination="https://origin.internal.example:9443/private",
    )
    return lab, request, authority


def admit(lab: wp7.TwoOperatorLab, request: wp7.AdmissionContext, *, amount: int = 1) -> object:
    return lab.admit(
        request,
        amount=amount,
        source_started_ms=100,
        source_completed_ms=200,
        destination_started_ms=300,
        destination_completed_ms=400,
    )


def test_composed_admission_commits_limits_allocation_audits_replay_and_exact_capability() -> None:
    lab, request, _ = build_lab()

    capability = admit(lab, request)
    receipt = lab.connector.connect(capability=capability, now_ms=400)

    assert lab.limit_bucket_count == 8
    assert lab.active_allocation_count == 1
    assert lab.admitted_grant_count == 1
    assert [event.action for event in lab.audit_events("isp-a")] == ["admitted"]
    assert [event.action for event in lab.audit_events("isp-b")] == ["admitted"]
    assert receipt.route_grant_digest == request.route_grant_digest
    with pytest.raises(wp7.LabRejected) as rejected:
        lab.connector.connect(capability=replace(capability), now_ms=400)
    assert rejected.value.code == "connector-capability-rejected"


def test_quota_denial_after_valid_gates_records_atomic_overload_without_success_state() -> None:
    lab, request, _ = build_lab(limit_changes={"client_capacity": 1})

    with pytest.raises(wp7.LabRejected) as rejected:
        admit(lab, request, amount=2)

    assert rejected.value.code == "client-limit"
    assert (lab.limit_bucket_count, lab.active_allocation_count, lab.admitted_grant_count) == (0, 0, 0)
    assert [(event.action, event.reason_code) for event in lab.audit_events("isp-a")] == [("overload", "client-limit")]
    assert [(event.action, event.reason_code) for event in lab.audit_events("isp-b")] == [("overload", "client-limit")]


def test_source_denial_precedes_destination_and_audit_preflight_without_quota_mutation() -> None:
    lab, request, _ = build_lab(source_audit_capacity=1)
    forged = replace(request, name_id="forged-name", destination_edge_id="forged-destination")

    with pytest.raises(wp7.LabRejected) as rejected:
        admit(lab, forged)

    assert rejected.value.code == "source-name-mismatch"
    assert (lab.limit_bucket_count, lab.active_allocation_count, lab.admitted_grant_count) == (0, 0, 0)
    assert [(event.action, event.reason_code) for event in lab.audit_events("isp-a")] == [("denied", "source-name-mismatch")]
    assert lab.audit_events("isp-b") == ()


def test_owned_audit_exhaustion_prevents_all_success_state_and_peer_audit_mutation() -> None:
    lab, request, _ = build_lab(source_audit_capacity=1)
    with pytest.raises(wp7.LabRejected):
        admit(lab, replace(request, name_id="forged-name"))

    with pytest.raises(wp7.LabRejected) as rejected:
        admit(lab, request)

    assert rejected.value.code == "audit-capacity"
    assert (lab.limit_bucket_count, lab.active_allocation_count, lab.admitted_grant_count) == (0, 0, 0)
    assert len(lab.audit_events("isp-a")) == 1
    assert lab.audit_events("isp-b") == ()


@pytest.mark.parametrize(
    ("authority_changes", "code"),
    [
        ({"channel_authority_digest": digest("foreign-channel-authority")}, "source-verified-authority-mismatch"),
        ({"exporter_binding_digest": digest("foreign-exporter-binding")}, "source-verified-authority-mismatch"),
        ({"source_gateway_conformant": False}, "source-gateway-conformance-denied"),
        ({"destination_gateway_conformant": False}, "destination-gateway-conformance-denied"),
        ({"source_continuity_status": "unavailable"}, "source-continuity-unavailable"),
        ({"source_continuity_status": "revoked"}, "source-continuity-revoked"),
        ({"destination_continuity_status": "tombstoned"}, "destination-continuity-tombstoned"),
        ({"destination_continuity_status": "equivocated"}, "destination-continuity-equivocated"),
    ],
)
def test_verified_authority_requires_exact_positive_gateway_channel_exporter_and_continuity(
    authority_changes: dict[str, object], code: str
) -> None:
    lab, request, _ = build_lab(authority_changes=authority_changes)

    with pytest.raises(wp7.LabRejected) as rejected:
        admit(lab, request)

    assert rejected.value.code == code
    assert (lab.limit_bucket_count, lab.active_allocation_count, lab.admitted_grant_count) == (0, 0, 0)


def test_source_and_destination_admission_allow_exact_five_second_boundaries() -> None:
    lab, request, _ = build_lab(authority_changes={"expires_at_ms": 20_000})

    capability = lab.admit(
        request,
        amount=1,
        source_started_ms=0,
        source_completed_ms=5_000,
        destination_started_ms=5_000,
        destination_completed_ms=10_000,
    )

    assert capability.admitted_at_ms == 10_000


@pytest.mark.parametrize(
    ("times", "authority_changes", "code"),
    [
        ((0, 5_001, 5_001, 5_002), {}, "source-admission-timeout"),
        ((10, 9, 9, 10), {}, "source-clock-rollback"),
        ((0, 1, 0, 1), {}, "destination-clock-rollback"),
        ((0, 1, 2, 5_003), {}, "destination-admission-timeout"),
        ((99, 100, 101, 102), {"issued_at_ms": 100}, "source-authority-not-current"),
        ((0, 101, 101, 102), {"expires_at_ms": 100}, "source-authority-expired"),
        ((0, 99, 99, 101), {"expires_at_ms": 100}, "destination-authority-expired"),
        ((0, 1, 1, wp7.MAX_UINT64 + 1), {}, "destination-completed-invalid"),
    ],
)
def test_admission_timing_rollback_overflow_and_authority_expiry_fail_before_resources(
    times: tuple[int, int, int, int], authority_changes: dict[str, object], code: str
) -> None:
    lab, request, _ = build_lab(authority_changes=authority_changes)

    with pytest.raises(wp7.LabRejected) as rejected:
        lab.admit(
            request,
            amount=1,
            source_started_ms=times[0],
            source_completed_ms=times[1],
            destination_started_ms=times[2],
            destination_completed_ms=times[3],
        )

    assert rejected.value.code == code
    assert (lab.limit_bucket_count, lab.active_allocation_count, lab.admitted_grant_count) == (0, 0, 0)


def test_drain_is_bounded_by_thirty_seconds_and_authority_expiry_and_revokes_connector_capability() -> None:
    lab, request, _ = build_lab(authority_changes={"expires_at_ms": 40_000})
    capability = admit(lab, request)

    lab.drain(capability=capability, started_ms=500, completed_ms=30_500)

    assert lab.active_allocation_count == 0
    with pytest.raises(wp7.LabRejected) as rejected:
        lab.connector.connect(capability=capability, now_ms=30_500)
    assert rejected.value.code == "connector-capability-rejected"

    for completed_ms, authority_expiry, code in (
        (30_501, 40_000, "drain-timeout"),
        (20_001, 20_000, "drain-authority-expired"),
        (499, 40_000, "drain-clock-rollback"),
        (wp7.MAX_UINT64 + 1, wp7.MAX_UINT64, "drain-completed-invalid"),
    ):
        candidate_lab, candidate_request, _ = build_lab(authority_changes={"expires_at_ms": authority_expiry})
        candidate_capability = admit(candidate_lab, candidate_request)
        with pytest.raises(wp7.LabRejected) as rejected:
            candidate_lab.drain(capability=candidate_capability, started_ms=500, completed_ms=completed_ms)
        assert rejected.value.code == code
        assert candidate_lab.active_allocation_count == 1
        assert [(event.action, event.reason_code) for event in candidate_lab.audit_events("isp-a")] == [
            ("admitted", "admitted"),
            ("denied", code),
        ]
        assert [(event.action, event.reason_code) for event in candidate_lab.audit_events("isp-b")] == [
            ("admitted", "admitted"),
            ("denied", code),
        ]


def test_connector_rejects_an_expired_capability() -> None:
    lab, request, _ = build_lab(authority_changes={"expires_at_ms": 500})
    capability = admit(lab, request)

    with pytest.raises(wp7.LabRejected) as rejected:
        lab.connector.connect(capability=capability, now_ms=501)

    assert rejected.value.code == "connector-capability-expired"


def test_operator_reports_derive_counts_and_safe_codes_from_owned_audits() -> None:
    lab, request, _ = build_lab()
    with pytest.raises(wp7.LabRejected):
        admit(lab, replace(request, name_id="forged-name"))
    admit(lab, request)

    source_report = lab.report("isp-a")
    destination_report = lab.report("isp-b")

    assert (source_report.admitted, source_report.denied, source_report.overloads) == (1, 1, 0)
    assert source_report.safe_code_counts == (("admitted", 1), ("source-name-mismatch", 1))
    assert (destination_report.admitted, destination_report.denied, destination_report.overloads) == (1, 0, 0)
    assert destination_report.safe_code_counts == (("admitted", 1),)

    standalone = wp7.AuditLog(operator_id="isp-a", capacity=1)
    standalone.record(action="denied", reason_code="source-name-mismatch", subject_digest=digest("subject"))
    with pytest.raises(TypeError):
        wp7.OperatorReport.from_audit(standalone, admitted=99, denied=77, overloads=55)
    with pytest.raises(TypeError):
        wp7.OperatorReport(
            operator_id="isp-a",
            admitted=99,
            denied=77,
            overloads=55,
            audit_event_count=0,
            audit_tail_digest=digest("fabricated-tail"),
            safe_code_counts=(("admitted", 99),),
        )
