from __future__ import annotations

import json
from pathlib import Path

import pytest

from nbsr.continuity import (
    MAX_SNAPSHOT_BYTES,
    ContinuityRecord,
    ContinuitySnapshot,
    ContinuityState,
    ReplicaConfig,
    SnapshotRejected,
    SnapshotRepository,
    StateKey,
    StateKind,
    decode_snapshot,
    encode_snapshot,
)


def snapshot(*, generation: int = 7) -> ContinuitySnapshot:
    config = ReplicaConfig("tenant-a", "replicas-a", ("replica-c", "replica-a", "replica-b"), 2)
    record = ContinuityRecord(
        StateKey("tenant-a", "payments", StateKind.POLICY, "00"),
        3,
        1,
        bytes.fromhex("11" * 32),
        None,
        2_000,
        3_000,
        False,
    )
    return ContinuitySnapshot(config, generation, 1_000, ContinuityState("tenant-a", (record,)))


def test_snapshot_encoding_is_canonical_stable_and_round_trips() -> None:
    encoded = encode_snapshot(snapshot())
    assert len(encoded) == 527
    assert snapshot().snapshot_digest.hex() == "63a7047825954e576152988dc12215296f3d14b2b10f74d4beeadbdbc33c87ad"
    assert encoded.endswith(b"\n")
    assert decode_snapshot(encoded) == snapshot()


@pytest.mark.parametrize(
    "mutator",
    [
        lambda value: value | {"unknown": 1},
        lambda value: {key: item for key, item in value.items() if key != "created_at"},
        lambda value: value | {"snapshot_digest": "00" * 32},
        lambda value: value | {"replica_ids": ["replica-b", "replica-a", "replica-c"]},
        lambda value: value | {"records": value["records"] * 2},
    ],
)
def test_decoder_rejects_unknown_missing_corrupt_unsorted_or_duplicate_state(mutator) -> None:  # type: ignore[no-untyped-def]
    value = json.loads(encode_snapshot(snapshot()))
    malformed = json.dumps(mutator(value), sort_keys=True, separators=(",", ":")).encode("ascii") + b"\n"
    with pytest.raises(SnapshotRejected):
        decode_snapshot(malformed)


def test_decoder_rejects_noncanonical_partial_and_oversized_input() -> None:
    value = json.loads(encode_snapshot(snapshot()))
    pretty = json.dumps(value, indent=2).encode("ascii")
    for malformed in (pretty, b'{"schema":', b"x" * (MAX_SNAPSHOT_BYTES + 1)):
        with pytest.raises(SnapshotRejected):
            decode_snapshot(malformed)


def test_replica_config_requires_sorted_unique_bounded_majority() -> None:
    assert ReplicaConfig("tenant-a", "replicas-a", ("replica-b", "replica-a", "replica-c"), 2).replica_ids == (
        "replica-a",
        "replica-b",
        "replica-c",
    )
    for ids, quorum in (((), 1), (("replica-a", "replica-a"), 2), (("replica-a", "replica-b", "replica-c"), 1)):
        with pytest.raises(SnapshotRejected):
            ReplicaConfig("tenant-a", "replicas-a", ids, quorum)


def test_repository_round_trip_rejects_rollback_and_preserves_prior_file(tmp_path: Path) -> None:
    path = tmp_path / "continuity.json"
    repository = SnapshotRepository(path)
    repository.save(snapshot(generation=7))
    before = path.read_bytes()
    assert repository.load(minimum_generation=7) == snapshot(generation=7)

    with pytest.raises(SnapshotRejected, match="rollback"):
        repository.save(snapshot(generation=6))
    assert path.read_bytes() == before
    with pytest.raises(SnapshotRejected, match="rollback"):
        repository.load(minimum_generation=8)


def test_repository_rejects_symlink_directory_torn_and_oversized_files(tmp_path: Path) -> None:
    valid = tmp_path / "valid.json"
    valid.write_bytes(encode_snapshot(snapshot()))
    link = tmp_path / "link.json"
    try:
        link.symlink_to(valid)
    except OSError:
        link = None  # type: ignore[assignment]

    paths = [tmp_path, tmp_path / "torn.json", tmp_path / "large.json"]
    paths[1].write_bytes(b'{"schema":')
    paths[2].write_bytes(b"x" * (MAX_SNAPSHOT_BYTES + 1))
    if link is not None:
        paths.append(link)
    for path in paths:
        with pytest.raises(SnapshotRejected):
            SnapshotRepository(path).load()
