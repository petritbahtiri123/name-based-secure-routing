from __future__ import annotations

import pytest

from nbsr.continuity import (
    ContinuitySnapshot,
    ContinuityState,
    QuorumRejected,
    ReplicaConfig,
    ReplicaObservation,
    resolve_quorum,
)


CONFIG = ReplicaConfig("tenant-a", "replicas-a", ("replica-a", "replica-b", "replica-c"), 2)


def snapshot(generation: int = 7, *, created_at: int = 1_000, config: ReplicaConfig = CONFIG) -> ContinuitySnapshot:
    return ContinuitySnapshot(config, generation, created_at, ContinuityState.empty(config.tenant_id))


def observation(replica_id: str, value: ContinuitySnapshot | None = None, *, complete: bool = True) -> ReplicaObservation:
    return ReplicaObservation(replica_id, snapshot() if value is None else value, complete)


def test_exact_quorum_returns_immutable_agreed_view_deterministically() -> None:
    observations = (observation("replica-b"), observation("replica-a"), ReplicaObservation("replica-c", None, False))
    view = resolve_quorum(CONFIG, observations, minimum_generation=7)
    assert view.replica_ids == ("replica-a", "replica-b")
    assert view.snapshot == snapshot()


@pytest.mark.parametrize(
    "observations,message",
    [
        ((observation("replica-a"),), "quorum"),
        ((observation("replica-a"), observation("replica-a")), "duplicate"),
        ((observation("replica-a"), observation("replica-x")), "unknown"),
        ((observation("replica-a"), ReplicaObservation("replica-b", snapshot(), False)), "partial"),
        ((observation("replica-a", snapshot(6)), observation("replica-b", snapshot(6))), "stale"),
        ((observation("replica-a"), observation("replica-b", snapshot(created_at=1_001))), "conflict"),
    ],
)
def test_quorum_rejects_missing_duplicate_forged_partial_stale_and_conflicting_evidence(
    observations: tuple[ReplicaObservation, ...],
    message: str,
) -> None:
    with pytest.raises(QuorumRejected, match=message):
        resolve_quorum(CONFIG, observations, minimum_generation=7)


def test_quorum_rejects_tenant_and_replica_set_confusion() -> None:
    other_tenant = ReplicaConfig("tenant-b", "replicas-a", ("replica-a", "replica-b", "replica-c"), 2)
    other_set = ReplicaConfig("tenant-a", "replicas-b", ("replica-a", "replica-b", "replica-c"), 2)
    for wrong in (snapshot(config=other_tenant), snapshot(config=other_set)):
        with pytest.raises(QuorumRejected, match="context"):
            resolve_quorum(CONFIG, (observation("replica-a", wrong), observation("replica-b", wrong)), minimum_generation=1)


def test_unavailable_replica_is_tolerated_only_when_complete_quorum_agrees() -> None:
    unavailable = ReplicaObservation("replica-c", None, False)
    assert resolve_quorum(CONFIG, (observation("replica-a"), observation("replica-b"), unavailable), minimum_generation=7)
    with pytest.raises(QuorumRejected, match="quorum"):
        resolve_quorum(CONFIG, (observation("replica-a"), unavailable), minimum_generation=7)
