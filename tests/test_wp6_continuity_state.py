from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from nbsr.continuity import (
    MAX_RECORDS,
    ContinuityRecord,
    ContinuityState,
    StateKey,
    StateKind,
    StateRejected,
)


TENANT = "tenant-a"
SERVICE = "payments"
DIGEST_A = bytes.fromhex("11" * 32)
DIGEST_B = bytes.fromhex("22" * 32)


def key(kind: StateKind = StateKind.ORIGIN, object_id: str = "01") -> StateKey:
    return StateKey(TENANT, SERVICE, kind, object_id)


def record(**changes: object) -> ContinuityRecord:
    values: dict[str, object] = {
        "key": key(),
        "generation": 1,
        "sequence": 1,
        "authority_digest": DIGEST_A,
        "previous_digest": None,
        "expires_at": 2_000,
        "retained_until": 3_000,
        "terminal": False,
    }
    values.update(changes)
    return ContinuityRecord(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("field,value", [("tenant_id", "Tenant"), ("service_id", "a/b"), ("object_id", "xyz" * 30)])
def test_state_key_rejects_unsafe_or_oversized_identifiers(field: str, value: object) -> None:
    values = {"tenant_id": TENANT, "service_id": SERVICE, "kind": StateKind.ORIGIN, "object_id": "01"}
    values[field] = value
    with pytest.raises(StateRejected, match="invalid state key"):
        StateKey(**values)  # type: ignore[arg-type]


def test_record_is_immutable_and_has_stable_canonical_digest() -> None:
    candidate = record()
    assert candidate.content_digest.hex() == "7e253d40f196a6947d279cdf2856bce66f011d736780e3fdab74caf54c2a6132"
    with pytest.raises(FrozenInstanceError):
        candidate.sequence = 2  # type: ignore[misc]


@pytest.mark.parametrize(
    "changes",
    [
        {"generation": 0},
        {"sequence": True},
        {"authority_digest": b"short"},
        {"previous_digest": b"short"},
        {"expires_at": -1},
        {"retained_until": 1_999},
        {"terminal": 1},
    ],
)
def test_record_rejects_invalid_types_bounds_and_retention(changes: dict[str, object]) -> None:
    with pytest.raises(StateRejected):
        record(**changes)


def test_state_apply_is_idempotent_and_requires_digest_chain() -> None:
    first = record()
    accepted = ContinuityState.empty(TENANT).apply(first)
    assert accepted.apply(first) is accepted

    successor = record(sequence=2, authority_digest=DIGEST_B, previous_digest=first.content_digest)
    assert accepted.apply(successor).get(key()) is successor
    with pytest.raises(StateRejected, match="previous digest"):
        accepted.apply(record(sequence=2, authority_digest=DIGEST_B))


def test_state_rejects_stale_rollback_and_same_sequence_equivocation_atomically() -> None:
    first = record(generation=2, sequence=3)
    state = ContinuityState.empty(TENANT).apply(first)
    for candidate, message in (
        (record(generation=1, sequence=4), "stale"),
        (record(generation=3, sequence=2), "stale"),
        (record(generation=2, sequence=3, authority_digest=DIGEST_B), "equivocation"),
    ):
        with pytest.raises(StateRejected, match=message):
            state.apply(candidate)
        assert state.get(key()) is first


def test_policy_version_and_fingerprint_cannot_roll_back_or_equivocate() -> None:
    policy_key = key(StateKind.POLICY, "00")
    current = record(key=policy_key, generation=7, sequence=1)
    state = ContinuityState.empty(TENANT).apply(current)
    with pytest.raises(StateRejected, match="stale"):
        state.apply(record(key=policy_key, generation=6, sequence=2, previous_digest=current.content_digest))
    with pytest.raises(StateRejected, match="equivocation"):
        state.apply(record(key=policy_key, generation=7, sequence=1, authority_digest=DIGEST_B))


@pytest.mark.parametrize("kind", [StateKind.REVOCATION, StateKind.REPLAY, StateKind.TOMBSTONE])
def test_terminal_security_fact_never_resurrects(kind: StateKind) -> None:
    state_key = key(kind)
    terminal = record(key=state_key, terminal=True)
    state = ContinuityState.empty(TENANT).apply(terminal)
    with pytest.raises(StateRejected, match="terminal"):
        state.apply(
            record(
                key=state_key,
                sequence=2,
                authority_digest=DIGEST_B,
                previous_digest=terminal.content_digest,
                terminal=False,
            ),
        )


@pytest.mark.parametrize("kind", [StateKind.REVOCATION, StateKind.TOMBSTONE])
def test_revocation_and_tombstone_records_must_be_terminal(kind: StateKind) -> None:
    with pytest.raises(StateRejected, match="must be terminal"):
        record(key=key(kind), terminal=False)


def test_state_rejects_cross_tenant_confusion_and_fails_closed_at_capacity() -> None:
    state = ContinuityState.empty(TENANT)
    with pytest.raises(StateRejected, match="tenant"):
        state.apply(record(key=StateKey("tenant-b", SERVICE, StateKind.ORIGIN, "01")))

    records = tuple(record(key=key(StateKind.REPLAY, f"{index:04x}"), terminal=True) for index in range(MAX_RECORDS))
    full = ContinuityState(TENANT, records)
    with pytest.raises(StateRejected, match="capacity"):
        full.apply(record(key=key(StateKind.REPLAY, "ffff"), terminal=True))
