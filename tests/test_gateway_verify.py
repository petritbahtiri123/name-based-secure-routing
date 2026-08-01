from __future__ import annotations

import json

import pytest

from nbsr.gateway_journal import OwnershipJournal
from nbsr.gateway_plan import OperationKind, build_gateway_plan
from nbsr.gateway_profile import GatewayProfile, PlatformSnapshot
from nbsr.gateway_verify import CheckCode, verify_gateway

from tests.test_gateway_profile import profile_data, snapshot_data


def complete_inputs(**snapshot_overrides: object):
    profile = GatewayProfile.from_dict(profile_data())
    empty = PlatformSnapshot.from_dict(snapshot_data())
    plan = build_gateway_plan(profile, empty)
    observed = [operation.operation_id for operation in plan.operations]
    data = snapshot_data(
        [{"kind": "route", "prefix": profile.synthetic_ipv4, "owner": profile.instance_id}],
        observed_operation_ids=observed,
        name_plane_healthy=True,
        route_plane_healthy=True,
        resolver_parity=True,
        service_attribution=True,
        fair_share=True,
    )
    data.update(snapshot_overrides)
    snapshot = PlatformSnapshot.from_dict(data)
    journal = OwnershipJournal.create(plan, ("nameserver", "192.0.2.53"), observed)
    return profile, plan, journal, snapshot


def test_complete_snapshot_passes_every_stable_check() -> None:
    profile, plan, journal, snapshot = complete_inputs()
    report = verify_gateway(profile, plan, journal, snapshot)

    assert report.passed
    assert [check.code for check in report.checks] == list(CheckCode)
    assert all(check.passed for check in report.checks)
    assert len(report.profile_ref) == 16
    assert report.to_dict() == verify_gateway(profile, plan, journal, snapshot).to_dict()


@pytest.mark.parametrize(
    ("code", "override", "missing_kind"),
    (
        (CheckCode.CAPTURE_V4, {}, OperationKind.CAPTURE_V4),
        (CheckCode.CAPTURE_V6, {}, OperationKind.CAPTURE_V6),
        (CheckCode.REJECT_V4, {}, OperationKind.REJECT_V4),
        (CheckCode.REJECT_V6, {}, OperationKind.REJECT_V6),
        (CheckCode.POLICY_V4, {}, OperationKind.POLICY_RULE_V4),
        (CheckCode.POLICY_V6, {}, OperationKind.POLICY_RULE_V6),
        (CheckCode.DNS_FORWARD, {}, OperationKind.DNS_FORWARD),
        (CheckCode.NAME_PLANE, {"name_plane_healthy": False}, None),
        (CheckCode.ROUTE_PLANE, {"route_plane_healthy": False}, None),
        (CheckCode.RESOLVER_PARITY, {"resolver_parity": False}, None),
        (CheckCode.SERVICE_ATTRIBUTION, {"service_attribution": False}, None),
        (CheckCode.FAIR_SHARE, {"fair_share": False}, None),
        (CheckCode.NO_ORIGIN_FALLBACK, {"direct_origin_fallback": True}, None),
    ),
)
def test_each_invariant_fails_independently(code: CheckCode, override: dict[str, object], missing_kind: OperationKind | None) -> None:
    profile, plan, journal, snapshot = complete_inputs(**override)
    if missing_kind is not None:
        missing_id = next(operation.operation_id for operation in plan.operations if operation.kind is missing_kind)
        snapshot = PlatformSnapshot.from_dict(
            snapshot_data(
                [{"kind": "route", "prefix": profile.synthetic_ipv4, "owner": profile.instance_id}],
                observed_operation_ids=[value for value in snapshot.observed_operation_ids if value != missing_id],
                name_plane_healthy=snapshot.name_plane_healthy,
                route_plane_healthy=snapshot.route_plane_healthy,
                resolver_parity=snapshot.resolver_parity,
                service_attribution=snapshot.service_attribution,
                fair_share=snapshot.fair_share,
                direct_origin_fallback=snapshot.direct_origin_fallback,
            )
        )

    report = verify_gateway(profile, plan, journal, snapshot)
    results = {check.code: check.passed for check in report.checks}

    assert not report.passed
    assert not results[code]
    if code is CheckCode.NAME_PLANE:
        assert results[CheckCode.ROUTE_PLANE]
    if code is CheckCode.ROUTE_PLANE:
        assert results[CheckCode.NAME_PLANE]


def test_collision_ownership_and_rollback_failures_are_reported() -> None:
    profile, plan, journal, _ = complete_inputs()
    collision = PlatformSnapshot.from_dict(
        snapshot_data(
            [{"kind": "vpn", "prefix": "192.0.2.128/25", "owner": None}],
            observed_operation_ids=[operation.operation_id for operation in plan.operations],
            name_plane_healthy=True,
            route_plane_healthy=True,
            resolver_parity=True,
            service_attribution=True,
            fair_share=True,
        )
    )
    report = verify_gateway(profile, plan, journal, collision)
    results = {check.code: check.passed for check in report.checks}
    assert not results[CheckCode.COLLISION_FREE]

    partial = PlatformSnapshot.from_dict(snapshot_data(observed_operation_ids=[]))
    results = {check.code: check.passed for check in verify_gateway(profile, plan, journal, partial).checks}
    assert not results[CheckCode.OWNERSHIP]
    assert not results[CheckCode.ROLLBACK_COMPLETE]


def test_report_never_contains_injected_sensitive_strings() -> None:
    sensitive = "origin.example credential-secret client-raw packet-payload"
    profile, plan, journal, snapshot = complete_inputs(resolver_state=[sensitive])
    encoded = json.dumps(verify_gateway(profile, plan, journal, snapshot).to_dict(), sort_keys=True)

    for token in sensitive.split():
        assert token not in encoded
    assert len(encoded) < 8192
