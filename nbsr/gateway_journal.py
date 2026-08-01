from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from nbsr.gateway_plan import GatewayPlan, Operation, OperationKind, PlanPhase, plan_matches_profile
from nbsr.gateway_profile import GatewayProfile
from nbsr.secure_files import secure_write_text


_JOURNAL_FIELDS = frozenset({"version", "profile_digest", "resolver_before", "applied_operation_ids", "integrity_digest"})
_MAX_FILE_BYTES = 64 * 1024
_MAX_ITEMS = 256


class JournalError(ValueError):
    """Ownership state is invalid or cannot authorize rollback."""


def _closed_mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, dict) or set(value) != _JOURNAL_FIELDS or not all(type(key) is str for key in value):
        raise JournalError("journal must contain exactly the approved fields")
    return value


def _strings(value: object, label: str) -> tuple[str, ...]:
    if type(value) not in (list, tuple) or len(value) > _MAX_ITEMS or not all(type(item) is str for item in value):
        raise JournalError(f"{label} must be a bounded string sequence")
    if any(len(item) > 256 or "\x00" in item for item in value):
        raise JournalError(f"{label} contains an invalid value")
    return tuple(value)


def _integrity_payload(version: int, profile_digest: str, resolver_before: Sequence[str], applied: Sequence[str]) -> bytes:
    value = {
        "version": version,
        "profile_digest": profile_digest,
        "resolver_before": list(resolver_before),
        "applied_operation_ids": list(applied),
    }
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


@dataclass(frozen=True)
class OwnershipJournal:
    version: int
    profile_digest: str
    resolver_before: tuple[str, ...]
    applied_operation_ids: tuple[str, ...]
    integrity_digest: str

    def __post_init__(self) -> None:
        if type(self.version) is not int or self.version != 1:
            raise JournalError("journal version is not supported")
        for label, value, length in (
            ("profile", self.profile_digest, 64),
            ("integrity", self.integrity_digest, 64),
        ):
            if type(value) is not str or len(value) != length or any(character not in "0123456789abcdef" for character in value):
                raise JournalError(f"journal {label} digest is invalid")
        object.__setattr__(self, "resolver_before", _strings(self.resolver_before, "resolver state"))
        object.__setattr__(self, "applied_operation_ids", _strings(self.applied_operation_ids, "applied operation IDs"))

    @classmethod
    def create(
        cls,
        plan: GatewayPlan,
        resolver_before: Sequence[str],
        applied_operation_ids: Sequence[str],
    ) -> OwnershipJournal:
        resolver = _strings(tuple(resolver_before), "resolver state")
        applied = _strings(tuple(applied_operation_ids), "applied operation IDs")
        if len(applied) != len(set(applied)):
            raise JournalError("journal contains duplicate applied operation IDs")
        known = {operation.operation_id for operation in plan.operations}
        if not set(applied) <= known:
            raise JournalError("journal contains an unknown applied operation ID")
        digest = hashlib.sha256(_integrity_payload(1, plan.profile_digest, resolver, applied)).hexdigest()
        return cls(1, plan.profile_digest, resolver, applied, digest)

    def validate_integrity(self) -> None:
        expected = hashlib.sha256(
            _integrity_payload(self.version, self.profile_digest, self.resolver_before, self.applied_operation_ids)
        ).hexdigest()
        if not hmac.compare_digest(expected, self.integrity_digest):
            raise JournalError("journal integrity check failed")

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "profile_digest": self.profile_digest,
            "resolver_before": list(self.resolver_before),
            "applied_operation_ids": list(self.applied_operation_ids),
            "integrity_digest": self.integrity_digest,
        }

    @classmethod
    def from_dict(cls, value: object) -> OwnershipJournal:
        data = _closed_mapping(value)
        journal = cls(
            data["version"],
            data["profile_digest"],
            _strings(data["resolver_before"], "resolver state"),
            _strings(data["applied_operation_ids"], "applied operation IDs"),
            data["integrity_digest"],
        )
        if len(journal.applied_operation_ids) != len(set(journal.applied_operation_ids)):
            raise JournalError("journal contains duplicate applied operation IDs")
        journal.validate_integrity()
        return journal

    def save(self, path: Path | str) -> None:
        self.validate_integrity()
        encoded = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")) + "\n"
        if len(encoded.encode()) > _MAX_FILE_BYTES:
            raise JournalError("journal exceeds the maximum size")
        secure_write_text(path, encoded)

    @classmethod
    def load(cls, path: Path | str) -> OwnershipJournal:
        target = Path(path)
        try:
            with target.open("rb") as stream:
                encoded = stream.read(_MAX_FILE_BYTES + 1)
            if len(encoded) > _MAX_FILE_BYTES:
                raise JournalError("journal exceeds the maximum size")
            value = json.loads(encoded.decode("utf-8"))
        except JournalError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise JournalError("journal could not be read") from exc
        return cls.from_dict(value)


def build_rollback_plan(plan: GatewayPlan, journal: OwnershipJournal, profile: GatewayProfile) -> GatewayPlan:
    journal.validate_integrity()
    if not plan_matches_profile(plan, profile) or plan.profile_digest != journal.profile_digest:
        raise JournalError("journal profile does not match the plan")
    by_id = {operation.operation_id: operation for operation in plan.operations}
    if not set(journal.applied_operation_ids) <= set(by_id):
        raise JournalError("journal contains an unknown applied operation ID")
    selected = [by_id[operation_id] for operation_id in journal.applied_operation_ids]
    rollback = [
        Operation.create(operation.inverse_kind, operation.inverse_arguments, operation.kind, operation.arguments)
        for operation in reversed(selected)
    ]
    rollback.append(Operation.create(OperationKind.RESOLVER_RESTORE, journal.resolver_before, OperationKind.RESOLVER_RESTORE, ("clear",)))
    return GatewayPlan(plan.profile_digest, tuple(rollback), PlanPhase.ROLLBACK)
