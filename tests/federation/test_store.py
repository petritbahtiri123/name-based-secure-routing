from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from nbsr.federation import ReasonCode
from nbsr.federation.state import FederationEvent, FederationState
from nbsr.federation.store import (
    MAX_FEDERATION_RECORDS,
    MAX_FEDERATION_SNAPSHOT_BYTES,
    FederationSnapshotRejected,
    FederationStateRepository,
    decode_state,
    encode_state,
)


def populated() -> FederationState:
    def item(generation: int, digest: bytes, previous: bytes | None, **extra: object) -> FederationEvent:
        return FederationEvent(
            "operator:a",
            generation,
            1,
            digest,
            "operator",
            b"a" * 32,
            b"b" * 32,
            b"s" * 32,
            previous_digest=previous,
            dependencies=(b"q" * 32,),
            **extra,
        )

    state, _ = FederationState.empty().apply(item(1, b"1" * 32, None), 98)
    state, _ = state.apply(item(2, b"2" * 32, b"1" * 32), 99)
    state, result = state.apply(item(3, b"d" * 32, b"2" * 32, terminal=True, replay_digest=b"r" * 32), 100)
    assert result.reason is ReasonCode.NONE
    return state


def test_canonical_snapshot_round_trip_contains_only_bounded_safety_state() -> None:
    state = populated()
    encoded = encode_state(state, created_at=101)
    assert decode_state(encoded) == state
    assert encoded == encode_state(state, created_at=101)
    for forbidden in (b"private_key", b"subscriber", b"origin_endpoint", b"traffic_payload", b"exporter_secret"):
        assert forbidden not in encoded.lower()


def test_repository_valid_restart_preserves_watermark_terminal_and_replay(tmp_path: Path) -> None:
    path = tmp_path / "federation.json"
    repository = FederationStateRepository(path)
    state = populated()
    repository.save(state, created_at=101)
    restored = FederationStateRepository(path).load()
    assert restored == state
    resurrected, result = restored.apply(
        FederationEvent("operator:a", 4, 1, b"n" * 32, "operator", b"a" * 32, b"b" * 32, b"s" * 32, previous_digest=b"d" * 32),
        102,
    )
    assert resurrected is restored
    assert result.reason is ReasonCode.ERR_TERMINAL_STATE
    replayed, result = restored.apply(
        FederationEvent("new:a", 1, 1, b"n" * 32, "service", b"a" * 32, b"b" * 32, b"s" * 32, replay_digest=b"r" * 32),
        102,
    )
    assert replayed is restored
    assert result.reason is ReasonCode.ERR_REPLAY


def test_repository_rejects_corrupt_truncated_oversized_stale_and_nonregular_without_mutation(tmp_path: Path) -> None:
    path = tmp_path / "federation.json"
    repo = FederationStateRepository(path)
    current = populated()
    repo.save(current, created_at=101)
    valid = path.read_bytes()
    assert repo.load() == current
    cases = (valid[:-1], valid.replace(b'"schema":1', b'"schema":2'), b"x" * (MAX_FEDERATION_SNAPSHOT_BYTES + 1))
    for malformed in cases:
        path.write_bytes(malformed)
        with pytest.raises(FederationSnapshotRejected):
            repo.load()
    path.write_bytes(valid)
    with pytest.raises(FederationSnapshotRejected, match="rollback"):
        repo.save(replace(current, accepted=()), created_at=102)
    path.unlink()
    path.mkdir()
    with pytest.raises(FederationSnapshotRejected):
        repo.load()


def test_fresh_node_does_not_accept_first_seen_authority_without_current_proof() -> None:
    event = FederationEvent(
        "trust:first",
        1,
        1,
        b"d" * 32,
        "trust",
        b"a" * 32,
        b"b" * 32,
        b"s" * 32,
        requires_prior_authority=True,
    )
    state = FederationState.empty()
    same, result = state.apply(event, 100)
    assert same is state
    assert result.reason is ReasonCode.ERR_EVIDENCE_MISSING


def test_durable_watermark_rejects_restored_old_snapshot_after_repository_restart(tmp_path: Path) -> None:
    path = tmp_path / "federation.json"
    repo = FederationStateRepository(path)
    first, _ = FederationState.empty().apply(
        FederationEvent("service:a", 1, 1, b"1" * 32, "service", b"a" * 32, b"b" * 32, b"s" * 32),
        100,
    )
    repo.save(first, created_at=101)
    old_bytes = path.read_bytes()
    higher, _ = first.apply(
        FederationEvent(
            "service:a",
            2,
            1,
            b"2" * 32,
            "service",
            b"a" * 32,
            b"b" * 32,
            b"s" * 32,
            previous_digest=b"1" * 32,
        ),
        102,
    )
    repo.save(higher, created_at=103)
    path.write_bytes(old_bytes)
    with pytest.raises(FederationSnapshotRejected, match="rollback"):
        FederationStateRepository(path).load()


@pytest.mark.parametrize("field", ["tombstones", "replay", "quarantine"])
def test_save_cannot_remove_retained_safety_state(tmp_path: Path, field: str) -> None:
    path = tmp_path / "federation.json"
    state = replace(populated(), quarantine=(("operator:a", (b"d" * 32, b"e" * 32)),))
    FederationStateRepository(path).save(state, created_at=101)
    candidate = replace(state, **{field: ()})
    with pytest.raises(FederationSnapshotRejected, match="retained"):
        FederationStateRepository(path).save(candidate, created_at=102)


def test_snapshot_rejects_invalid_semantics_and_limit_plus_one() -> None:
    state = populated()
    with pytest.raises((FederationSnapshotRejected, ValueError)):
        encode_state(replace(state, accepted=(replace(state.accepted[0], generation=-1),)), created_at=101)
    with pytest.raises((FederationSnapshotRejected, ValueError)):
        encode_state(replace(state, accepted=(replace(state.accepted[0], terminal=1),)), created_at=101)
    with pytest.raises((FederationSnapshotRejected, ValueError)):
        encode_state(
            replace(state, tombstones=tuple(f"key:{index:04d}" for index in range(MAX_FEDERATION_RECORDS + 1))),
            created_at=101,
        )
    for candidate in (
        lambda: replace(state, tombstones=(1,)),
        lambda: replace(state, replay=((b"r" * 32, "bad"),)),
        lambda: replace(state, pending=(("key", -1),)),
        lambda: replace(state, quarantine=(("key", (b"short", b"d" * 32)),)),
    ):
        with pytest.raises((FederationSnapshotRejected, ValueError, TypeError)):
            encode_state(candidate(), created_at=101)


def test_quarantine_evidence_can_extend_but_not_remove(tmp_path: Path) -> None:
    path = tmp_path / "federation.json"
    state = replace(populated(), quarantine=(("operator:a", (b"d" * 32, b"e" * 32)),))
    repo = FederationStateRepository(path)
    repo.save(state, created_at=101)
    extended = replace(state, quarantine=(("operator:a", (b"d" * 32, b"e" * 32, b"f" * 32)),))
    repo.save(extended, created_at=102)
    assert FederationStateRepository(path).load() == extended


def test_interrupted_main_only_compaction_recovers_safe_anchor(tmp_path: Path) -> None:
    path = tmp_path / "federation.json"
    state = populated()
    repo = FederationStateRepository(path)
    repo.save(state, created_at=101)
    compacted = state.compact(86_501)
    path.write_bytes(encode_state(compacted, created_at=86_501))
    assert FederationStateRepository(path).load() == state
    assert decode_state(path.read_bytes()) == state
