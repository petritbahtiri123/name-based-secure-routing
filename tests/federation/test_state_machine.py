from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from nbsr.federation import BilateralAuthorizer, DecisionOutcome, EnforcementMode, FederationResult, ReasonCode
from nbsr.federation.authorization import FederationResult as Task5FederationResult
from nbsr.federation.state import FederationEvent, FederationState


D1 = bytes.fromhex("11" * 32)
D2 = bytes.fromhex("22" * 32)
OP = bytes.fromhex("aa" * 32)
PEER = bytes.fromhex("bb" * 32)
SERVICE = bytes.fromhex("cc" * 32)


def test_task5_federation_result_constructor_remains_compatible() -> None:
    assert FederationResult(DecisionOutcome.ACCEPT, ReasonCode.NONE).outcome is DecisionOutcome.ACCEPT
    assert isinstance(BilateralAuthorizer()._decisions, dict)
    assert isinstance(Task5FederationResult(DecisionOutcome.ACCEPT, ReasonCode.NONE), FederationResult)


def event(**changes: object) -> FederationEvent:
    base = FederationEvent(
        key="trust:global",
        generation=1,
        sequence=1,
        object_digest=D1,
        object_kind="trust",
        operator_id=OP,
        peer_operator_id=PEER,
        service_id=SERVICE,
        dependencies=(D1,),
        valid_until=10_000,
    )
    return replace(base, **changes)


def test_accept_mutates_idempotent_accept_does_not_and_reject_is_identical() -> None:
    empty = FederationState.empty()
    accepted, result = empty.apply(event(), 100)
    assert (result.outcome, result.reason, result.enforcement, result.state_changed) == (
        DecisionOutcome.ACCEPT,
        ReasonCode.NONE,
        EnforcementMode.NONE,
        True,
    )
    assert result.emitted == (D1,)
    assert result.state_digest == accepted.digest
    same, repeated = accepted.apply(event(), 101)
    assert same is accepted
    assert repeated == replace(result, state_changed=False, emitted=())

    rejected, failure = accepted.apply(event(sequence=0), 102)
    assert rejected is accepted
    assert (failure.outcome, failure.reason, failure.state_changed) == (
        DecisionOutcome.REJECT,
        ReasonCode.ERR_ROLLBACK,
        False,
    )


def test_pending_restricted_and_quarantine_have_exact_side_effects() -> None:
    state = FederationState.empty()
    pending, result = state.apply(event(validation_failures=(ReasonCode.ERR_EVIDENCE_MISSING,), pending_until=130), 100)
    assert pending is state
    assert (result.outcome, result.reason, result.enforcement, result.emitted) == (
        DecisionOutcome.PENDING,
        ReasonCode.ERR_EVIDENCE_MISSING,
        EnforcementMode.DENY_NEW_USE,
        (),
    )

    accepted, _ = state.apply(event(), 100)
    restricted, result = accepted.apply(event(operation="existing_session", source_fresh_at=0), 400)
    assert restricted is accepted
    assert (result.outcome, result.reason, result.enforcement, result.state_changed) == (
        DecisionOutcome.RESTRICTED,
        ReasonCode.ERR_FRESHNESS,
        EnforcementMode.REAUTHENTICATE,
        False,
    )

    quarantined, result = accepted.apply(event(object_digest=D2), 110)
    assert quarantined is not accepted
    assert (result.outcome, result.reason, result.enforcement, result.evidence) == (
        DecisionOutcome.QUARANTINE,
        ReasonCode.ERR_EQUIVOCATION,
        EnforcementMode.DENY_NEW_USE,
        tuple(sorted((D1, D2))),
    )
    assert quarantined.accepted == accepted.accepted


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"generation": 0}, ReasonCode.ERR_ROLLBACK),
        ({"sequence": 0}, ReasonCode.ERR_ROLLBACK),
        ({"generation": 2, "sequence": 1, "previous_digest": None}, ReasonCode.ERR_CONTINUITY),
    ],
)
def test_monotonic_watermarks_and_continuity(changes: dict[str, object], reason: ReasonCode) -> None:
    accepted, _ = FederationState.empty().apply(event(), 100)
    prior_digest = accepted.digest
    result_state, result = accepted.apply(event(**changes), 101)
    assert result_state is accepted
    assert result.reason is reason
    assert result.state_digest == prior_digest


def test_terminal_tombstone_blocks_resurrection_but_new_operator_generation_can_recover() -> None:
    terminal, first = FederationState.empty().apply(event(terminal=True, object_kind="operator"), 100)
    assert first.outcome is DecisionOutcome.ACCEPT
    same, blocked = terminal.apply(event(generation=2, previous_digest=D1, object_digest=D2, object_kind="operator"), 101)
    assert same is terminal
    assert blocked.reason is ReasonCode.ERR_TERMINAL_STATE

    recovered, result = terminal.apply(
        event(
            key="operator:recovery:2",
            generation=2,
            object_digest=D2,
            object_kind="operator",
            recovery_of="trust:global",
            validation_failures=(),
        ),
        102,
    )
    assert recovered is not terminal
    assert result.outcome is DecisionOutcome.ACCEPT
    assert "trust:global" in recovered.tombstones


def test_replay_is_deterministic_before_and_after_compaction() -> None:
    accepted, _ = FederationState.empty().apply(event(replay_digest=D2), 100)
    same, replay = accepted.apply(event(replay_digest=D2), 101)
    assert same is accepted
    assert replay.reason is ReasonCode.ERR_REPLAY
    compacted = accepted.compact(86_500)
    same, replay = compacted.apply(event(replay_digest=D2), 86_500)
    assert same is compacted
    assert replay.reason is ReasonCode.ERR_REPLAY
    expired = accepted.compact(86_501 + 86_400)
    assert D2 not in dict(expired.replay)
    assert expired.tombstones == accepted.tombstones


def test_derived_rollback_precedes_replay() -> None:
    first, _ = FederationState.empty().apply(event(replay_digest=D2), 100)
    higher, _ = first.apply(event(generation=2, sequence=1, object_digest=D2, previous_digest=D1), 101)
    unchanged, result = higher.apply(event(replay_digest=D2), 102)
    assert unchanged is higher
    assert result.reason is ReasonCode.ERR_ROLLBACK


def test_versions_require_immediate_sequence_or_new_generation_one() -> None:
    first, _ = FederationState.empty().apply(event(), 100)
    for candidate in (
        event(sequence=99, object_digest=D2, previous_digest=D1),
        event(generation=2, sequence=99, object_digest=D2, previous_digest=D1),
    ):
        unchanged, result = first.apply(candidate, 101)
        assert unchanged is first
        assert result.reason is ReasonCode.ERR_CONTINUITY


def test_compromise_never_becomes_accepted_authority() -> None:
    first, _ = FederationState.empty().apply(event(), 100)
    unchanged, result = first.apply(
        event(generation=2, sequence=1, object_digest=D2, previous_digest=D1, compromised=True),
        101,
    )
    assert unchanged is first
    assert (result.outcome, result.reason, result.enforcement) == (
        DecisionOutcome.REJECT,
        ReasonCode.ERR_REVOKED,
        EnforcementMode.TERMINATE_ACTIVE_USE,
    )


def test_lkg_is_bound_to_exact_cached_authority_and_dependencies() -> None:
    first, _ = FederationState.empty().apply(event(source_fresh_at=100), 100)
    forged = event(
        operation="existing_session",
        generation=999,
        object_digest=D2,
        operator_id=b"x" * 32,
        peer_operator_id=b"y" * 32,
        service_id=b"z" * 32,
        dependencies=(b"q" * 32,),
    )
    unchanged, result = first.apply(forged, 200)
    assert unchanged is first
    assert (result.outcome, result.reason) == (DecisionOutcome.REJECT, ReasonCode.ERR_AUTHORITY)


def test_specification_authored_literal_state_scenarios() -> None:
    manifest = json.loads((Path(__file__).parent / "fixtures/task6-state-scenarios.json").read_bytes())
    assert manifest["generated"] is False
    state = FederationState.empty()
    events = (
        event(),
        event(),
        event(sequence=0),
        event(object_digest=D2),
    )
    for expected, candidate in zip(manifest["scenarios"], events, strict=True):
        state, result = state.apply(candidate, 100)
        assert {
            "enforcement": result.enforcement.name,
            "evidence": [value.hex() for value in result.evidence],
            "expected_state_digest": result.state_digest.hex(),
            "mutation": result.state_changed,
            "outcome": result.outcome.name,
            "reason": result.reason.name,
        } == {key: expected[key] for key in ("enforcement", "evidence", "expected_state_digest", "mutation", "outcome", "reason")}


def test_empty_node_cannot_bootstrap_arbitrary_recovery_generation() -> None:
    state = FederationState.empty()
    unchanged, result = state.apply(event(generation=9, sequence=99, recovery_of="anything"), 100)
    assert unchanged is state
    assert result.reason is ReasonCode.ERR_CONTINUITY


def test_equivocation_retry_is_idempotent_and_third_branch_is_retained() -> None:
    accepted, _ = FederationState.empty().apply(event(), 100)
    conflicted, _ = accepted.apply(event(object_digest=D2), 101)
    same, repeated = conflicted.apply(event(object_digest=D2), 102)
    assert same is conflicted
    assert repeated.state_changed is False
    third = b"3" * 32
    extended, result = conflicted.apply(event(object_digest=third), 103)
    assert result.evidence == tuple(sorted((D1, D2, third)))
    assert dict(extended.quarantine)["trust:global"] == result.evidence
