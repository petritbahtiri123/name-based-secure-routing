from __future__ import annotations

from dataclasses import replace

import pytest

from nbsr.gateway_plan import GatewayPlan, Operation, OperationKind, PlanError, build_gateway_plan
from nbsr.gateway_profile import GatewayProfile, PlatformSnapshot, ProfileError

from tests.test_gateway_profile import profile_data, snapshot_data


def build() -> tuple[GatewayProfile, PlatformSnapshot, GatewayPlan]:
    profile = GatewayProfile.from_dict(profile_data())
    snapshot = PlatformSnapshot.from_dict(snapshot_data())
    return profile, snapshot, build_gateway_plan(profile, snapshot)


def test_plan_has_stable_dual_stack_fail_closed_order() -> None:
    profile, _, plan = build()

    assert plan.profile_digest == profile.digest()
    assert [operation.kind for operation in plan.operations] == [
        OperationKind.NFT_TABLE,
        OperationKind.NFT_CHAIN,
        OperationKind.CAPTURE_V4,
        OperationKind.CAPTURE_V6,
        OperationKind.POLICY_RULE_V4,
        OperationKind.LOCAL_ROUTE_V4,
        OperationKind.POLICY_RULE_V6,
        OperationKind.LOCAL_ROUTE_V6,
        OperationKind.REJECT_V4,
        OperationKind.REJECT_V6,
        OperationKind.DNS_FORWARD,
        OperationKind.NAME_HEALTH,
        OperationKind.ROUTE_HEALTH,
        OperationKind.SERVICE_QUOTA,
    ]
    assert [operation.operation_id for operation in plan.operations] == [
        operation.operation_id for operation in build_gateway_plan(profile, PlatformSnapshot.from_dict(snapshot_data())).operations
    ]
    assert len(set(operation.operation_id for operation in plan.operations)) == len(plan.operations)


def test_plan_arguments_are_exact_prefix_scoped_vectors_without_fallback() -> None:
    profile, _, plan = build()
    arguments = [item for operation in plan.operations for item in operation.arguments]

    assert profile.synthetic_ipv4 in arguments
    assert profile.synthetic_ipv6 in arguments
    assert str(profile.firewall_mark) in arguments
    assert str(profile.policy_table) in arguments
    assert all("origin" not in item.casefold() and "fallback" not in item.casefold() for item in arguments)
    assert all("\n" not in item and "\r" not in item and ";" not in item and "`" not in item for item in arguments)


def test_planner_rejects_colliding_snapshot() -> None:
    profile = GatewayProfile.from_dict(profile_data())
    snapshot = PlatformSnapshot.from_dict(snapshot_data([{"kind": "vpn", "prefix": "192.0.2.128/25", "owner": None}]))
    with pytest.raises(ProfileError, match="collision"):
        build_gateway_plan(profile, snapshot)


def test_operation_rejects_control_or_shell_metacharacters() -> None:
    for value in ("bad\nvalue", "bad\rvalue", "bad;value", "bad`value", "bad|value", "bad&value"):
        with pytest.raises(PlanError):
            Operation.create(OperationKind.NFT_TABLE, (value,), OperationKind.NFT_TABLE, ("safe",))


def test_plan_rejects_duplicate_or_missing_fail_closed_operations() -> None:
    _, _, plan = build()
    with pytest.raises(PlanError, match="unique"):
        GatewayPlan(plan.profile_digest, plan.operations + (plan.operations[0],))
    without_reject = tuple(operation for operation in plan.operations if operation.kind is not OperationKind.REJECT_V6)
    with pytest.raises(PlanError, match="required"):
        GatewayPlan(plan.profile_digest, without_reject)


def test_plan_round_trips_through_closed_json_model() -> None:
    _, _, plan = build()
    assert GatewayPlan.from_dict(plan.to_dict()) == plan
    value = plan.to_dict()
    value["unknown"] = True
    with pytest.raises(PlanError):
        GatewayPlan.from_dict(value)

    operation = plan.operations[0]
    with pytest.raises(PlanError):
        replace(operation, arguments=("bad;value",))
