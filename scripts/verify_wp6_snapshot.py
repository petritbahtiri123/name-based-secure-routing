"""Dependency-independent verifier for the deterministic WP6 snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


MAX_BYTES = 256 * 1024
ROOT_FIELDS = {
    "created_at",
    "generation",
    "quorum",
    "records",
    "replica_ids",
    "replica_set_id",
    "schema",
    "snapshot_digest",
    "tenant_id",
}
RECORD_FIELDS = {
    "authority_digest",
    "expires_at",
    "generation",
    "key",
    "previous_digest",
    "retained_until",
    "sequence",
    "terminal",
}


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")


def verify(path: Path) -> None:
    data = path.read_bytes()
    if not data or len(data) > MAX_BYTES:
        raise ValueError("snapshot size is invalid")
    value = json.loads(data)
    if type(value) is not dict or set(value) != ROOT_FIELDS:
        raise ValueError("snapshot fields are invalid")
    if value["schema"] != "nbsr-continuity-snapshot-v1":
        raise ValueError("snapshot schema is invalid")
    replicas = value["replica_ids"]
    if type(replicas) is not list or replicas != sorted(set(replicas)) or not 1 <= len(replicas) <= 32:
        raise ValueError("replica identities are invalid")
    if type(value["quorum"]) is not int or value["quorum"] <= len(replicas) // 2 or value["quorum"] > len(replicas):
        raise ValueError("quorum is invalid")
    records = value["records"]
    if type(records) is not list or len(records) > 4096:
        raise ValueError("record count is invalid")
    keys: list[tuple[object, ...]] = []
    for record in records:
        if type(record) is not dict or set(record) != RECORD_FIELDS:
            raise ValueError("record fields are invalid")
        key = record["key"]
        if type(key) is not list or len(key) != 4:
            raise ValueError("record key is invalid")
        keys.append(tuple(key))
    if keys != sorted(set(keys)):
        raise ValueError("record keys are not canonical")
    supplied = value.pop("snapshot_digest")
    if type(supplied) is not str or supplied != hashlib.sha256(canonical(value)).hexdigest():
        raise ValueError("snapshot digest is invalid")
    value["snapshot_digest"] = supplied
    if data != canonical(value) + b"\n":
        raise ValueError("snapshot serialization is not canonical")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    arguments = parser.parse_args()
    verify(arguments.path)
    print("WP6 snapshot verified: 1 valid deterministic snapshot")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
