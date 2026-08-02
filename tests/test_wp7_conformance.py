"""Conformance contracts for WP7 audit, connector, and topology closure."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict, replace
from hashlib import sha256
from pathlib import Path

import pytest

from scripts import verify_wp7_lab
from nbsr.two_operator_lab import (
    MAX_UINT64,
    AdmissionContext,
    AuditLog,
    DestinationConnector,
    LabRejected,
    LabTopology,
    LimitProfile,
    OperatorPairRuntime,
    OperatorProfile,
    RouteTrust,
    TwoOperatorLab,
    VerifiedAuthority,
    simulate_raw_scan,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "wp7-two-operator-lab.json"
VERIFIER = ROOT / "scripts" / "verify_wp7_lab.py"


def digest(value: str) -> str:
    return sha256(value.encode("ascii")).hexdigest()


def topology_data(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": "nbsr-wp7-two-operator-lab-v1",
        "operators": ["isp-a", "isp-b"],
        "connector_id": "isp-b-connector",
        "edges": [
            {"source": "isp-a", "destination": "isp-b-connector"},
            {"source": "isp-b-connector", "destination": "isp-b"},
        ],
    }
    value.update(changes)
    return value


def audited_lab(
    *, source_audit_capacity: int = 8, destination_audit_capacity: int = 8, grant_label: str = "grant-a"
) -> tuple[TwoOperatorLab, AdmissionContext]:
    source = OperatorProfile(
        operator_id="isp-a",
        identity_fingerprint=digest("source-identity"),
        policy_fingerprint=digest("source-policy-key"),
        audit_fingerprint=digest("source-audit-key"),
        policy_digest=digest("source-policy"),
        gateway_profile_digest=digest("source-gateway"),
        continuity_digest=digest("source-continuity"),
        policy_version=1,
    )
    destination = OperatorProfile(
        operator_id="isp-b",
        identity_fingerprint=digest("destination-identity"),
        policy_fingerprint=digest("destination-policy-key"),
        audit_fingerprint=digest("destination-audit-key"),
        policy_digest=digest("destination-policy"),
        gateway_profile_digest=digest("destination-gateway"),
        continuity_digest=digest("destination-continuity"),
        policy_version=1,
    )
    request = AdmissionContext(
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
        route_grant_digest=digest(grant_label),
        channel_authority_digest=digest(f"channel-authority-{grant_label}"),
        exporter_binding_digest=digest(f"exporter-binding-{grant_label}"),
        source_policy_digest=source.policy_digest,
        destination_policy_digest=destination.policy_digest,
        source_gateway_digest=source.gateway_profile_digest,
        destination_gateway_digest=destination.gateway_profile_digest,
        source_continuity_digest=source.continuity_digest,
        destination_continuity_digest=destination.continuity_digest,
        source_policy_version=1,
        destination_policy_version=1,
    )
    trust = RouteTrust.from_profiles(
        source, destination, route_id="route-a", service_id="payments", route_grant_digest=request.route_grant_digest
    )
    authority = VerifiedAuthority(
        route_grant_digest=request.route_grant_digest,
        channel_authority_digest=request.channel_authority_digest,
        exporter_binding_digest=request.exporter_binding_digest,
        source_edge_id=request.source_edge_id,
        destination_edge_id=request.destination_edge_id,
        source_gateway_digest=request.source_gateway_digest,
        destination_gateway_digest=request.destination_gateway_digest,
        source_gateway_conformant=True,
        destination_gateway_conformant=True,
        source_continuity_digest=request.source_continuity_digest,
        destination_continuity_digest=request.destination_continuity_digest,
        source_continuity_status="current",
        destination_continuity_status="current",
        issued_at_ms=0,
        expires_at_ms=60_000,
    )
    limits = LimitProfile(
        client_capacity=8,
        name_capacity=8,
        route_capacity=8,
        service_capacity=8,
        channel_capacity=8,
        tunnel_capacity=8,
        operator_capacity=8,
        refill_per_ms=1,
        max_buckets=64,
        max_active_allocations=32,
    )
    runtime = OperatorPairRuntime(
        source=source,
        destination=destination,
        limit_profile=limits,
        source_audit_capacity=source_audit_capacity,
        destination_audit_capacity=destination_audit_capacity,
        connector=DestinationConnector(
            operator_id=destination.operator_id,
            connector_id="isp-b-connector",
            private_destination="https://origin.internal.example:9443/private",
        ),
        max_registered_contexts=1,
    )
    lab = runtime.register_context(expected_context=request, trust=trust, verified_authority=authority)
    return lab, request


def admit_lab(lab: TwoOperatorLab, request: AdmissionContext) -> object:
    return lab.admit(
        request,
        amount=1,
        source_started_ms=100,
        source_completed_ms=200,
        destination_started_ms=300,
        destination_completed_ms=400,
    )


def test_audit_logs_are_operator_owned_bounded_and_monotonic() -> None:
    source = AuditLog(operator_id="isp-a", capacity=1)
    destination = AuditLog(operator_id="isp-b", capacity=1)

    source_event = source.record(action="admitted", subject_digest=digest("grant-a"))
    destination_event = destination.record(action="admitted", subject_digest=digest("grant-a"))

    assert (source_event.operator_id, source_event.sequence) == ("isp-a", 1)
    assert (destination_event.operator_id, destination_event.sequence) == ("isp-b", 1)
    with pytest.raises(LabRejected, match="audit capacity"):
        source.record(action="admitted", subject_digest=digest("grant-b"))
    assert len(source.events) == 1


def test_audit_sequence_exhaustion_fails_closed_before_recording() -> None:
    audit = AuditLog(operator_id="isp-a", capacity=2, next_sequence=MAX_UINT64)

    assert audit.record(action="denied", subject_digest=digest("grant-a")).sequence == MAX_UINT64
    with pytest.raises(LabRejected, match="audit sequence"):
        audit.record(action="denied", subject_digest=digest("grant-b"))
    assert len(audit.events) == 1


def test_safe_operator_report_and_errors_exclude_private_destination() -> None:
    private_destination = "https://origin.internal.example:9443/private"
    lab, request = audited_lab()

    capability = admit_lab(lab, request)
    receipt = lab.connector.connect(capability=capability, now_ms=400)
    report = lab.report("isp-b")

    public_values = (repr(receipt), repr(report), json.dumps(asdict(report), sort_keys=True))
    assert all(private_destination not in value for value in public_values)
    with pytest.raises(LabRejected) as rejected:
        DestinationConnector(operator_id="isp-a", private_destination=private_destination).connect(capability=capability, now_ms=400)
    assert private_destination not in str(rejected.value)


def test_connector_receipt_cannot_be_used_as_a_private_destination_guessing_or_linkage_oracle() -> None:
    private_destination = "https://origin.internal.example:9443/private"
    first_lab, first_request = audited_lab(grant_label="grant-a")
    second_lab, second_request = audited_lab(grant_label="grant-b")

    first = first_lab.connector.connect(capability=admit_lab(first_lab, first_request), now_ms=400)
    second = second_lab.connector.connect(capability=admit_lab(second_lab, second_request), now_ms=400)

    assert first != second
    assert first.connector_digest != digest(private_destination)
    assert second.connector_digest != digest(private_destination)
    assert private_destination not in repr(first)


def test_audit_overload_has_no_fallback_log_or_unbounded_growth() -> None:
    audit = AuditLog(operator_id="isp-a", capacity=1)
    audit.record(action="admitted", subject_digest=digest("grant-a"))

    with pytest.raises(LabRejected) as rejected:
        audit.record(action="admitted", subject_digest=digest("grant-b"))

    assert rejected.value.code == "audit-capacity"
    assert len(audit.events) == 1


def test_audit_capacity_is_preflighted_before_admission_success_or_peer_audit_mutation() -> None:
    lab, request = audited_lab(source_audit_capacity=1, destination_audit_capacity=1)
    with pytest.raises(LabRejected):
        admit_lab(lab, replace(request, name_id="forged-name"))

    with pytest.raises(LabRejected) as rejected:
        admit_lab(lab, request)

    assert rejected.value.code == "audit-capacity"
    assert lab.admitted_grant_count == 0
    assert len(lab.audit_events("isp-a")) == 1
    assert lab.audit_events("isp-b") == ()


def test_public_admission_cannot_bypass_full_or_missing_operator_audits() -> None:
    lab, request = audited_lab(source_audit_capacity=1, destination_audit_capacity=1)
    with pytest.raises(LabRejected):
        admit_lab(lab, replace(request, name_id="forged-name"))
    replacement_source = AuditLog(operator_id="isp-a", capacity=8)
    replacement_destination = AuditLog(operator_id="isp-b", capacity=8)

    with pytest.raises(TypeError):
        lab.admit(
            request,
            amount=1,
            source_started_ms=100,
            source_completed_ms=200,
            destination_started_ms=300,
            destination_completed_ms=400,
            source_audit=replacement_source,
            destination_audit=replacement_destination,
        )
    assert lab.admitted_grant_count == 0
    assert replacement_source.events == replacement_destination.events == ()


def test_closed_topology_rejects_direct_operator_edge_and_oversized_collections() -> None:
    direct = topology_data(
        edges=[
            {"source": "isp-a", "destination": "isp-b"},
            {"source": "isp-b-connector", "destination": "isp-b"},
        ]
    )
    reverse_direct = topology_data(
        edges=[
            {"source": "isp-b", "destination": "isp-a"},
            {"source": "isp-b-connector", "destination": "isp-b"},
        ]
    )
    oversized = topology_data(operators=["isp-a", "isp-b", "isp-c"])
    oversized_edges = topology_data(edges=[{"source": "isp-a"}, {"source": "isp-a"}, {"source": "isp-a"}])

    with pytest.raises(LabRejected, match="direct"):
        LabTopology.from_dict(direct)
    with pytest.raises(LabRejected, match="direct"):
        LabTopology.from_dict(reverse_direct)
    with pytest.raises(LabRejected, match="topology operators"):
        LabTopology.from_dict(oversized)
    with pytest.raises(LabRejected) as rejected:
        LabTopology.from_dict(oversized_edges)
    assert rejected.value.code == "topology-edges-invalid"


def test_config_is_canonical_bounded_and_contains_no_private_destination() -> None:
    raw = CONFIG.read_text(encoding="utf-8")
    topology = LabTopology.from_dict(json.loads(raw))

    assert topology == LabTopology.from_dict(topology_data())
    assert "origin.internal.example" not in raw
    assert "https://" not in raw


def test_raw_scan_is_deterministic_reaches_service_only_through_connector_and_discovers_no_private_destination() -> None:
    topology = LabTopology.from_dict(topology_data())

    first = simulate_raw_scan(topology)
    second = simulate_raw_scan(topology)

    assert first == second
    assert first.reachable_nodes == ("isp-a", "isp-b-connector", "isp-b")
    assert first.direct_operator_edges == ()
    assert first.discovered_connector_digests == ()


def test_verifier_exits_zero_and_is_byte_for_byte_deterministic() -> None:
    first = subprocess.run([sys.executable, str(VERIFIER)], cwd=ROOT, capture_output=True, text=True, check=False)
    second = subprocess.run([sys.executable, str(VERIFIER)], cwd=ROOT, capture_output=True, text=True, check=False)

    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout
    assert first.stderr == second.stderr == ""
    assert "origin.internal.example" not in first.stdout


@pytest.mark.parametrize(
    "raw",
    [
        b'{"schema":"ignored","schema":"nbsr-wp7-two-operator-lab-v1","operators":["isp-a","isp-b"],"connector_id":"isp-b-connector","edges":[{"source":"isp-a","destination":"isp-b-connector"},{"source":"isp-b-connector","destination":"isp-b"}]}',
        b'{"schema":"nbsr-wp7-two-operator-lab-v1","operators":["isp-a","isp-b"],"connector_id":"isp-b-connector","edges":[{"source":"ignored","source":"isp-a","destination":"isp-b-connector"},{"source":"isp-b-connector","destination":"isp-b"}]}',
    ],
)
def test_verifier_rejects_duplicate_json_members_at_every_object(raw: bytes) -> None:
    with pytest.raises(LabRejected) as rejected:
        verify_wp7_lab.parse_topology_config(raw)

    assert rejected.value.code == "topology-duplicate-key"
