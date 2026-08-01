"""Dependency-independent verifier for the deterministic WP6 snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
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
TEXT_ID = re.compile(r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*\Z")
OBJECT_ID = re.compile(r"[0-9a-f]{2,64}\Z")
KINDS = {"origin", "policy", "revocation", "replay", "tombstone", "grant", "channel"}
MAX_UINT64 = 2**64 - 1
MAX_TIMESTAMP = 253_402_300_799


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")


def require_uint(value: object, name: str, *, minimum: int = 0, maximum: int = MAX_UINT64) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} is invalid")
    return value


def require_text_id(value: object, name: str) -> str:
    if type(value) is not str or len(value) > 64 or TEXT_ID.fullmatch(value) is None:
        raise ValueError(f"{name} is invalid")
    return value


def require_digest(value: object, name: str, *, optional: bool = False) -> None:
    if optional and value is None:
        return
    if type(value) is not str or len(value) != 64:
        raise ValueError(f"{name} is invalid")
    try:
        decoded = bytes.fromhex(value)
    except ValueError as exc:
        raise ValueError(f"{name} is invalid") from exc
    if value != decoded.hex() or len(decoded) != 32:
        raise ValueError(f"{name} is invalid")


def read_bounded_regular_file(path: Path) -> bytes:
    before = path.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode) or before.st_size > MAX_BYTES:
        raise ValueError("snapshot file is not a bounded regular file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError("snapshot file changed during open")
        data = os.read(descriptor, MAX_BYTES + 1)
        if len(data) != opened.st_size or len(data) > MAX_BYTES:
            raise ValueError("snapshot file is partial or oversized")
        return data
    finally:
        os.close(descriptor)


def verify(path: Path) -> None:
    data = read_bounded_regular_file(path)
    if not data or len(data) > MAX_BYTES:
        raise ValueError("snapshot size is invalid")
    value = json.loads(data)
    if type(value) is not dict or set(value) != ROOT_FIELDS:
        raise ValueError("snapshot fields are invalid")
    if value["schema"] != "nbsr-continuity-snapshot-v1":
        raise ValueError("snapshot schema is invalid")
    tenant_id = require_text_id(value["tenant_id"], "tenant_id")
    require_text_id(value["replica_set_id"], "replica_set_id")
    require_uint(value["generation"], "generation", minimum=1)
    require_uint(value["created_at"], "created_at", maximum=MAX_TIMESTAMP)
    replicas = value["replica_ids"]
    if type(replicas) is not list or replicas != sorted(set(replicas)) or not 1 <= len(replicas) <= 32:
        raise ValueError("replica identities are invalid")
    for replica_id in replicas:
        require_text_id(replica_id, "replica identity")
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
        if key[0] != tenant_id:
            raise ValueError("record tenant context is invalid")
        require_text_id(key[0], "record tenant")
        require_text_id(key[1], "record service")
        if key[2] not in KINDS or type(key[3]) is not str or OBJECT_ID.fullmatch(key[3]) is None:
            raise ValueError("record key is invalid")
        require_uint(record["generation"], "record generation", minimum=1)
        require_uint(record["sequence"], "record sequence", minimum=1)
        expires_at = require_uint(record["expires_at"], "record expires_at", maximum=MAX_TIMESTAMP)
        retained_until = require_uint(record["retained_until"], "record retained_until", maximum=MAX_TIMESTAMP)
        if retained_until < expires_at or type(record["terminal"]) is not bool:
            raise ValueError("record retention or terminal state is invalid")
        if key[2] in {"revocation", "tombstone"} and not record["terminal"]:
            raise ValueError("terminal security record is invalid")
        require_digest(record["authority_digest"], "authority_digest")
        require_digest(record["previous_digest"], "previous_digest", optional=True)
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
