from __future__ import annotations

import json
from pathlib import Path

import pytest

from nbsr.gateway_journal import JournalError, OwnershipJournal, build_rollback_plan
from nbsr.gateway_plan import OperationKind, PlanPhase, build_gateway_plan
from nbsr.gateway_profile import GatewayProfile, PlatformSnapshot

from tests.test_gateway_profile import profile_data, snapshot_data


def inputs():
    profile = GatewayProfile.from_dict(profile_data())
    plan = build_gateway_plan(profile, PlatformSnapshot.from_dict(snapshot_data()))
    return profile, plan


def test_journal_secure_round_trip_and_closed_schema(tmp_path: Path) -> None:
    _, plan = inputs()
    journal = OwnershipJournal.create(plan, ("nameserver", "192.0.2.53"), [item.operation_id for item in plan.operations])
    path = tmp_path / "owned.json"

    journal.save(path)

    assert OwnershipJournal.load(path) == journal
    assert path.stat().st_size < 65536
    value = json.loads(path.read_text(encoding="utf-8"))
    assert set(value) == {"version", "profile_digest", "resolver_before", "applied_operation_ids", "integrity_digest"}


def test_journal_rejects_unknown_corrupt_or_oversized_data(tmp_path: Path) -> None:
    _, plan = inputs()
    journal = OwnershipJournal.create(plan, (), ())
    path = tmp_path / "owned.json"
    value = journal.to_dict()
    value["unknown"] = True
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(JournalError):
        OwnershipJournal.load(path)

    value = journal.to_dict()
    value["profile_digest"] = "0" * 64
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(JournalError, match="integrity"):
        OwnershipJournal.load(path)

    path.write_bytes(b" " * 65537)
    with pytest.raises(JournalError, match="size"):
        OwnershipJournal.load(path)


def test_journal_rejects_duplicate_unknown_or_mismatched_operations() -> None:
    _, plan = inputs()
    operation_id = plan.operations[0].operation_id
    with pytest.raises(JournalError, match="duplicate"):
        OwnershipJournal.create(plan, (), (operation_id, operation_id))
    with pytest.raises(JournalError, match="unknown"):
        OwnershipJournal.create(plan, (), ("0" * 24,))

    journal = OwnershipJournal.create(plan, (), (operation_id,))
    with pytest.raises(JournalError, match="profile"):
        build_rollback_plan(plan.__class__("0" * 64, plan.operations), journal)


def test_partial_rollback_uses_only_owned_operations_in_reverse_then_resolver() -> None:
    _, plan = inputs()
    applied = tuple(operation.operation_id for operation in plan.operations[:4])
    journal = OwnershipJournal.create(plan, ("nameserver", "192.0.2.53"), applied)

    rollback = build_rollback_plan(plan, journal)

    assert rollback.phase is PlanPhase.ROLLBACK
    assert [operation.kind for operation in rollback.operations[:-1]] == [
        operation.inverse_kind for operation in reversed(plan.operations[:4])
    ]
    assert [operation.arguments for operation in rollback.operations[:-1]] == [
        operation.inverse_arguments for operation in reversed(plan.operations[:4])
    ]
    assert rollback.operations[-1].kind is OperationKind.RESOLVER_RESTORE
    assert rollback.operations[-1].arguments == ("nameserver", "192.0.2.53")


def test_invalid_journal_never_produces_rollback_operations() -> None:
    _, plan = inputs()
    journal = OwnershipJournal.create(plan, (), (plan.operations[0].operation_id,))
    broken = journal.__class__(
        journal.version,
        journal.profile_digest,
        journal.resolver_before,
        journal.applied_operation_ids,
        "0" * 64,
    )
    with pytest.raises(JournalError, match="integrity"):
        build_rollback_plan(plan, broken)


def test_journal_bounds_resolver_and_applied_collections() -> None:
    _, plan = inputs()
    with pytest.raises(JournalError, match="resolver"):
        OwnershipJournal.create(plan, ("x",) * 257, ())
    with pytest.raises(JournalError, match="applied"):
        OwnershipJournal.create(plan, (), tuple("0" * 24 for _ in range(257)))
