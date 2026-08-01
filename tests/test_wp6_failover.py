from __future__ import annotations

import dataclasses

import pytest

from nbsr.continuity import (
    ContinuityDenied,
    ContinuityRecord,
    ContinuitySnapshot,
    ContinuityState,
    QuorumRejected,
    ReplicaConfig,
    ReplicaObservation,
    StateKey,
    StateKind,
    bounded_failover,
    drain_deadline,
    evaluate_continuity,
)


TENANT = "tenant-a"
SERVICE = "payments"
CONFIG = ReplicaConfig(TENANT, "replicas-a", ("replica-a", "replica-b", "replica-c"), 2)
POLICY = bytes.fromhex("11" * 32)


def item(kind: StateKind, object_id: str, digest_byte: int, *, terminal: bool = False, expires_at: int = 2_000) -> ContinuityRecord:
    return ContinuityRecord(
        StateKey(TENANT, SERVICE, kind, object_id),
        1,
        1,
        bytes([digest_byte]) * 32,
        None,
        expires_at,
        3_000,
        terminal,
    )


def state(*extra: ContinuityRecord) -> ContinuityState:
    baseline = (
        item(StateKind.POLICY, "00", 0x11),
        item(StateKind.CHANNEL, "aa", 0x22),
        item(StateKind.GRANT, "bb", 0x33),
        item(StateKind.REPLAY, "cc", 0x44),
    )
    return ContinuityState(TENANT, (*baseline, *extra))


def view(*extra: ContinuityRecord):  # type: ignore[no-untyped-def]
    snapshot = ContinuitySnapshot(CONFIG, 7, 1_000, state(*extra))
    observations = (
        ReplicaObservation("replica-a", snapshot, True),
        ReplicaObservation("replica-b", snapshot, True),
        ReplicaObservation("replica-c", None, False),
    )
    return bounded_failover(CONFIG, observations, minimum_generation=7, elapsed_ms=4_999)


def permit(**changes: object):  # type: ignore[no-untyped-def]
    values: dict[str, object] = {
        "view": view(),
        "tenant_id": TENANT,
        "service_id": SERVICE,
        "channel_id": "aa",
        "grant_id": "bb",
        "replay_id": "cc",
        "policy_fingerprint": POLICY,
        "now": 1_500,
    }
    values.update(changes)
    return evaluate_continuity(**values)  # type: ignore[arg-type]


def test_continuity_permit_contains_only_safe_local_authority_references() -> None:
    result = permit()
    assert result.tenant_id == TENANT
    assert result.service_id == SERVICE
    assert result.snapshot_digest == view().snapshot.snapshot_digest
    assert result.policy_fingerprint == POLICY
    assert result.channel_digest == bytes.fromhex("22" * 32)
    assert set(field.name for field in dataclasses.fields(result)) == {
        "tenant_id",
        "service_id",
        "channel_digest",
        "policy_fingerprint",
        "snapshot_digest",
    }


@pytest.mark.parametrize("elapsed", [5_001, -1, True])
def test_failover_rejects_time_limit_or_time_source_confusion(elapsed: object) -> None:
    snapshot = ContinuitySnapshot(CONFIG, 7, 1_000, state())
    observations = (ReplicaObservation("replica-a", snapshot, True), ReplicaObservation("replica-b", snapshot, True))
    with pytest.raises(QuorumRejected, match="failover"):
        bounded_failover(CONFIG, observations, minimum_generation=7, elapsed_ms=elapsed)  # type: ignore[arg-type]


def test_failover_requires_fresh_quorum() -> None:
    snapshot = ContinuitySnapshot(CONFIG, 6, 1_000, state())
    observations = (ReplicaObservation("replica-a", snapshot, True), ReplicaObservation("replica-b", snapshot, True))
    with pytest.raises(QuorumRejected, match="stale"):
        bounded_failover(CONFIG, observations, minimum_generation=7, elapsed_ms=1)


@pytest.mark.parametrize(
    "changes,message",
    [
        ({"tenant_id": "tenant-b"}, "context"),
        ({"service_id": "orders"}, "missing"),
        ({"channel_id": "dd"}, "missing"),
        ({"grant_id": "dd"}, "missing"),
        ({"replay_id": "dd"}, "missing"),
        ({"policy_fingerprint": bytes.fromhex("99" * 32)}, "policy"),
        ({"now": 2_000}, "expired"),
    ],
)
def test_continuity_fails_closed_for_context_missing_policy_and_expiry(changes: dict[str, object], message: str) -> None:
    with pytest.raises(ContinuityDenied, match=message):
        permit(**changes)


@pytest.mark.parametrize(
    "terminal",
    [
        item(StateKind.REVOCATION, "dd", 0x55, terminal=True),
        item(StateKind.TOMBSTONE, "ee", 0x66, terminal=True),
    ],
)
def test_revocation_or_tombstone_denies_continuity(terminal: ContinuityRecord) -> None:
    with pytest.raises(ContinuityDenied, match="terminal"):
        permit(view=view(terminal))


@pytest.mark.parametrize("kind,object_id", [(StateKind.CHANNEL, "aa"), (StateKind.GRANT, "bb"), (StateKind.REPLAY, "cc")])
def test_revoked_channel_grant_or_consumed_replay_never_resurrects(kind: StateKind, object_id: str) -> None:
    records = [record for record in state().records if record.key != StateKey(TENANT, SERVICE, kind, object_id)]
    records.append(item(kind, object_id, 0x77, terminal=True))
    snapshot = ContinuitySnapshot(CONFIG, 7, 1_000, ContinuityState(TENANT, tuple(records)))
    observations = (ReplicaObservation("replica-a", snapshot, True), ReplicaObservation("replica-b", snapshot, True))
    denied_view = bounded_failover(CONFIG, observations, minimum_generation=7, elapsed_ms=1)
    with pytest.raises(ContinuityDenied, match="terminal"):
        permit(view=denied_view)


def test_drain_deadline_is_bounded_and_never_extends_authority() -> None:
    assert drain_deadline(now=1_000, requested_seconds=40, authority_expires_at=2_000) == 1_030
    assert drain_deadline(now=1_000, requested_seconds=30, authority_expires_at=1_010) == 1_010
    with pytest.raises(ContinuityDenied):
        drain_deadline(now=1_000, requested_seconds=-1, authority_expires_at=2_000)
