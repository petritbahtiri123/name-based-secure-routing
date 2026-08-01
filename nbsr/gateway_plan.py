from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

from nbsr.gateway_profile import GatewayProfile, PlatformSnapshot, assert_collision_free


_PLAN_FIELDS = frozenset({"profile_digest", "phase", "operations"})
_OPERATION_FIELDS = frozenset({"operation_id", "kind", "arguments", "inverse_kind", "inverse_arguments"})
_FORBIDDEN_ARGUMENT_CHARACTERS = frozenset("\r\n;`|&")
_MAX_OPERATIONS = 256
_MAX_ARGUMENTS = 16


class PlanError(ValueError):
    """A gateway operation or plan violates the closed profile."""


class PlanPhase(str, Enum):
    INSTALL = "install"
    ROLLBACK = "rollback"


class OperationKind(str, Enum):
    NFT_TABLE = "nft_table"
    NFT_CHAIN = "nft_chain"
    CAPTURE_V4 = "capture_v4"
    CAPTURE_V6 = "capture_v6"
    POLICY_RULE_V4 = "policy_rule_v4"
    LOCAL_ROUTE_V4 = "local_route_v4"
    POLICY_RULE_V6 = "policy_rule_v6"
    LOCAL_ROUTE_V6 = "local_route_v6"
    REJECT_V4 = "reject_v4"
    REJECT_V6 = "reject_v6"
    DNS_FORWARD = "dns_forward"
    NAME_HEALTH = "name_health"
    ROUTE_HEALTH = "route_health"
    SERVICE_QUOTA = "service_quota"
    RESOLVER_RESTORE = "resolver_restore"


def _closed_mapping(value: object, fields: frozenset[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict) or set(value) != fields or not all(type(key) is str for key in value):
        raise PlanError(f"{label} must contain exactly the approved fields")
    return value


def _arguments(value: object) -> tuple[str, ...]:
    if type(value) not in (list, tuple) or len(value) > _MAX_ARGUMENTS or not all(type(item) is str for item in value):
        raise PlanError("operation arguments must be a bounded string sequence")
    result = tuple(value)
    if any(not item or len(item) > 256 or any(character in _FORBIDDEN_ARGUMENT_CHARACTERS for character in item) for item in result):
        raise PlanError("operation arguments contain unsafe characters")
    return result


@dataclass(frozen=True)
class Operation:
    operation_id: str
    kind: OperationKind
    arguments: tuple[str, ...]
    inverse_kind: OperationKind
    inverse_arguments: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            type(self.operation_id) is not str
            or len(self.operation_id) != 24
            or any(c not in "0123456789abcdef" for c in self.operation_id)
        ):
            raise PlanError("operation_id must be a stable hexadecimal reference")
        if type(self.kind) is not OperationKind or type(self.inverse_kind) is not OperationKind:
            raise PlanError("operation kind is not approved")
        object.__setattr__(self, "arguments", _arguments(self.arguments))
        object.__setattr__(self, "inverse_arguments", _arguments(self.inverse_arguments))

    @classmethod
    def create(
        cls,
        kind: OperationKind,
        arguments: Sequence[str],
        inverse_kind: OperationKind,
        inverse_arguments: Sequence[str],
    ) -> Operation:
        checked_arguments = _arguments(tuple(arguments))
        checked_inverse = _arguments(tuple(inverse_arguments))
        canonical = json.dumps([kind.value, checked_arguments, inverse_kind.value, checked_inverse], separators=(",", ":")).encode()
        return cls(hashlib.sha256(canonical).hexdigest()[:24], kind, checked_arguments, inverse_kind, checked_inverse)

    def to_dict(self) -> dict[str, object]:
        return {
            "operation_id": self.operation_id,
            "kind": self.kind.value,
            "arguments": list(self.arguments),
            "inverse_kind": self.inverse_kind.value,
            "inverse_arguments": list(self.inverse_arguments),
        }

    @classmethod
    def from_dict(cls, value: object) -> Operation:
        data = _closed_mapping(value, _OPERATION_FIELDS, "operation")
        try:
            kind = OperationKind(data["kind"])
            inverse_kind = OperationKind(data["inverse_kind"])
        except (TypeError, ValueError) as exc:
            raise PlanError("operation kind is not approved") from exc
        operation = cls(data["operation_id"], kind, _arguments(data["arguments"]), inverse_kind, _arguments(data["inverse_arguments"]))
        expected = cls.create(kind, operation.arguments, inverse_kind, operation.inverse_arguments)
        if operation.operation_id != expected.operation_id:
            raise PlanError("operation identifier does not match its content")
        return operation


@dataclass(frozen=True)
class GatewayPlan:
    profile_digest: str
    operations: tuple[Operation, ...]
    phase: PlanPhase = PlanPhase.INSTALL

    def __post_init__(self) -> None:
        if (
            type(self.profile_digest) is not str
            or len(self.profile_digest) != 64
            or any(c not in "0123456789abcdef" for c in self.profile_digest)
        ):
            raise PlanError("profile digest is invalid")
        if type(self.phase) is not PlanPhase:
            raise PlanError("plan phase is invalid")
        if type(self.operations) is not tuple or not 1 <= len(self.operations) <= _MAX_OPERATIONS:
            raise PlanError("plan operations must be a non-empty bounded tuple")
        if len({operation.operation_id for operation in self.operations}) != len(self.operations):
            raise PlanError("operation identifiers must be unique")
        if self.phase is PlanPhase.INSTALL:
            required = set(OperationKind) - {OperationKind.RESOLVER_RESTORE}
            present = {operation.kind for operation in self.operations}
            if not required <= present:
                raise PlanError("install plan is missing required fail-closed operations")

    def to_dict(self) -> dict[str, object]:
        return {
            "profile_digest": self.profile_digest,
            "phase": self.phase.value,
            "operations": [operation.to_dict() for operation in self.operations],
        }

    @classmethod
    def from_dict(cls, value: object) -> GatewayPlan:
        data = _closed_mapping(value, _PLAN_FIELDS, "gateway plan")
        operations = data["operations"]
        if type(operations) is not list or not 1 <= len(operations) <= _MAX_OPERATIONS:
            raise PlanError("operations must be a non-empty bounded list")
        try:
            phase = PlanPhase(data["phase"])
        except (TypeError, ValueError) as exc:
            raise PlanError("plan phase is invalid") from exc
        return cls(data["profile_digest"], tuple(Operation.from_dict(item) for item in operations), phase)


def _operation(kind: OperationKind, *arguments: str) -> Operation:
    inverse = ("remove", *arguments)
    return Operation.create(kind, arguments, kind, inverse)


def _canonical_operations(profile: GatewayProfile) -> tuple[Operation, ...]:
    instance = profile.instance_id
    mark = str(profile.firewall_mark)
    table = str(profile.policy_table)
    return (
        _operation(OperationKind.NFT_TABLE, instance),
        _operation(OperationKind.NFT_CHAIN, instance, "synthetic-capture"),
        _operation(OperationKind.CAPTURE_V4, profile.synthetic_ipv4, mark, profile.source_edge_host, str(profile.source_edge_port)),
        _operation(OperationKind.CAPTURE_V6, profile.synthetic_ipv6, mark, profile.source_edge_host, str(profile.source_edge_port)),
        _operation(OperationKind.POLICY_RULE_V4, mark, table),
        _operation(OperationKind.LOCAL_ROUTE_V4, profile.synthetic_ipv4, table),
        _operation(OperationKind.POLICY_RULE_V6, mark, table),
        _operation(OperationKind.LOCAL_ROUTE_V6, profile.synthetic_ipv6, table),
        _operation(OperationKind.REJECT_V4, profile.synthetic_ipv4),
        _operation(OperationKind.REJECT_V6, profile.synthetic_ipv6),
        _operation(OperationKind.DNS_FORWARD, profile.name_node_host, str(profile.name_node_port)),
        _operation(OperationKind.NAME_HEALTH, profile.name_node_host, str(profile.name_node_port)),
        _operation(OperationKind.ROUTE_HEALTH, profile.source_edge_host, str(profile.source_edge_port)),
        _operation(OperationKind.SERVICE_QUOTA, instance, "per-service", "bounded-fair-share"),
    )


def plan_matches_profile(plan: GatewayPlan, profile: GatewayProfile) -> bool:
    return plan.phase is PlanPhase.INSTALL and plan.profile_digest == profile.digest() and plan.operations == _canonical_operations(profile)


def build_gateway_plan(profile: GatewayProfile, snapshot: PlatformSnapshot) -> GatewayPlan:
    assert_collision_free(profile, snapshot)
    return GatewayPlan(profile.digest(), _canonical_operations(profile))
