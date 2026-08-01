from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum

from nbsr.gateway_journal import JournalError, OwnershipJournal, build_rollback_plan
from nbsr.gateway_plan import GatewayPlan, OperationKind, plan_matches_profile
from nbsr.gateway_profile import GatewayProfile, PlatformSnapshot, ProfileError, assert_collision_free


class CheckCode(str, Enum):
    COLLISION_FREE = "collision_free"
    CAPTURE_V4 = "capture_v4"
    CAPTURE_V6 = "capture_v6"
    REJECT_V4 = "reject_v4"
    REJECT_V6 = "reject_v6"
    POLICY_V4 = "policy_v4"
    POLICY_V6 = "policy_v6"
    DNS_FORWARD = "dns_forward"
    RESOLVER_PARITY = "resolver_parity"
    NAME_PLANE = "name_plane"
    ROUTE_PLANE = "route_plane"
    OWNERSHIP = "ownership"
    NO_ORIGIN_FALLBACK = "no_origin_fallback"
    SERVICE_ATTRIBUTION = "service_attribution"
    FAIR_SHARE = "fair_share"
    ROLLBACK_COMPLETE = "rollback_complete"


@dataclass(frozen=True)
class CheckResult:
    code: CheckCode
    passed: bool
    resource_ref: str

    def __post_init__(self) -> None:
        if type(self.code) is not CheckCode or type(self.passed) is not bool:
            raise TypeError("check result fields are invalid")
        if type(self.resource_ref) is not str or len(self.resource_ref) != 16:
            raise ValueError("resource reference is invalid")

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code.value, "passed": self.passed, "resource_ref": self.resource_ref}


@dataclass(frozen=True)
class ConformanceReport:
    profile_ref: str
    passed: bool
    checks: tuple[CheckResult, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "profile_ref": self.profile_ref,
            "passed": self.passed,
            "checks": [check.to_dict() for check in self.checks],
        }


def _reference(profile_digest: str, code: CheckCode) -> str:
    return hashlib.sha256(f"{profile_digest}:{code.value}".encode()).hexdigest()[:16]


def verify_gateway(
    profile: GatewayProfile,
    plan: GatewayPlan,
    journal: OwnershipJournal,
    snapshot: PlatformSnapshot,
) -> ConformanceReport:
    observed = set(snapshot.observed_operation_ids)
    planned_by_kind = {operation.kind: operation.operation_id for operation in plan.operations}

    def seen(*kinds: OperationKind) -> bool:
        return all(kind in planned_by_kind and planned_by_kind[kind] in observed for kind in kinds)

    ownership = (
        plan_matches_profile(plan, profile)
        and journal.profile_digest == profile.digest() == plan.profile_digest
        and set(journal.applied_operation_ids) == observed
        and set(journal.applied_operation_ids) <= {operation.operation_id for operation in plan.operations}
    )
    try:
        assert_collision_free(profile, snapshot, trusted_owner=profile.instance_id if ownership else None)
        collision_free = True
    except ProfileError:
        collision_free = False
    try:
        rollback = build_rollback_plan(plan, journal)
        rollback_complete = ownership and len(rollback.operations) == len(journal.applied_operation_ids) + 1
    except JournalError:
        rollback_complete = False

    values = {
        CheckCode.COLLISION_FREE: collision_free,
        CheckCode.CAPTURE_V4: seen(OperationKind.CAPTURE_V4),
        CheckCode.CAPTURE_V6: seen(OperationKind.CAPTURE_V6),
        CheckCode.REJECT_V4: seen(OperationKind.REJECT_V4),
        CheckCode.REJECT_V6: seen(OperationKind.REJECT_V6),
        CheckCode.POLICY_V4: seen(OperationKind.POLICY_RULE_V4, OperationKind.LOCAL_ROUTE_V4),
        CheckCode.POLICY_V6: seen(OperationKind.POLICY_RULE_V6, OperationKind.LOCAL_ROUTE_V6),
        CheckCode.DNS_FORWARD: seen(OperationKind.DNS_FORWARD),
        CheckCode.RESOLVER_PARITY: snapshot.resolver_parity,
        CheckCode.NAME_PLANE: snapshot.name_plane_healthy,
        CheckCode.ROUTE_PLANE: snapshot.route_plane_healthy,
        CheckCode.OWNERSHIP: ownership,
        CheckCode.NO_ORIGIN_FALLBACK: not snapshot.direct_origin_fallback,
        CheckCode.SERVICE_ATTRIBUTION: snapshot.service_attribution and seen(OperationKind.SERVICE_QUOTA),
        CheckCode.FAIR_SHARE: snapshot.fair_share and seen(OperationKind.SERVICE_QUOTA),
        CheckCode.ROLLBACK_COMPLETE: rollback_complete,
    }
    checks = tuple(CheckResult(code, values[code], _reference(profile.digest(), code)) for code in CheckCode)
    return ConformanceReport(profile.digest()[:16], all(check.passed for check in checks), checks)
