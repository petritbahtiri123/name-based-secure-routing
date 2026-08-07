from __future__ import annotations

import hashlib
import json
import os
import stat
import threading
from pathlib import Path

from nbsr.federation.state import AcceptedFederationObject, FederationState, StaticRecoveryPolicy
from nbsr.federation.profile import FederationProfile
from nbsr.secure_files import ensure_private_directory, secure_write_private


MAX_FEDERATION_SNAPSHOT_BYTES = 262_144
MAX_FEDERATION_RECORDS = 4_096
_SCHEMA = 1


class FederationSnapshotRejected(ValueError):
    pass


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")


def _state_value(state: FederationState) -> dict[str, object]:
    return {
        "accepted": [
            {
                "dependencies": [value.hex() for value in item.dependencies],
                "digest": item.object_digest.hex(),
                "fresh": item.source_fresh_at,
                "generation": item.generation,
                "key": item.key,
                "kind": item.object_kind,
                "operator": item.operator_id.hex(),
                "peer": item.peer_operator_id.hex(),
                "sequence": item.sequence,
                "service": item.service_id.hex(),
                "terminal": item.terminal,
                "valid_until": item.valid_until,
            }
            for item in state.accepted
        ],
        "pending": [[key, until] for key, until in state.pending],
        "quarantine": [[key, [value.hex() for value in digests]] for key, digests in state.quarantine],
        "replay": [[digest.hex(), seen] for digest, seen in state.replay],
        "static_policies": [
            {
                "activated_at": item.activated_at,
                "allowed_triggers": list(item.allowed_triggers),
                "expires_at": item.expires_at,
                "operators": [value.hex() for value in item.operators],
                "policy_digest": item.policy_digest.hex(),
                "scope": item.scope,
                "service_id": item.service_id.hex(),
            }
            for item in state.static_policies
        ],
        "tombstones": list(state.tombstones),
    }


def encode_state(state: FederationState, *, created_at: int) -> bytes:
    if type(state) is not FederationState or type(created_at) is not int or created_at < 0:
        raise FederationSnapshotRejected("snapshot input is invalid")
    root = {"created_at": created_at, "schema": _SCHEMA, "state": _state_value(state), "state_digest": state.digest.hex()}
    root["snapshot_digest"] = hashlib.sha256(_canonical(root)).hexdigest()
    encoded = _canonical(root) + b"\n"
    if len(encoded) > MAX_FEDERATION_SNAPSHOT_BYTES:
        raise FederationSnapshotRejected("snapshot exceeds size limit")
    return encoded


def _digest(value: object) -> bytes:
    if type(value) is not str or len(value) != 64:
        raise FederationSnapshotRejected("snapshot digest field is invalid")
    try:
        result = bytes.fromhex(value)
    except ValueError as exc:
        raise FederationSnapshotRejected("snapshot digest field is invalid") from exc
    if value != result.hex():
        raise FederationSnapshotRejected("snapshot digest field is noncanonical")
    return result


def decode_state(data: bytes) -> FederationState:
    if type(data) is not bytes or not data or len(data) > MAX_FEDERATION_SNAPSHOT_BYTES:
        raise FederationSnapshotRejected("snapshot size is invalid")
    try:
        root = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FederationSnapshotRejected("snapshot parsing failed") from exc
    if (
        type(root) is not dict
        or set(root) != {"created_at", "schema", "snapshot_digest", "state", "state_digest"}
        or root["schema"] != _SCHEMA
    ):
        raise FederationSnapshotRejected("snapshot schema is unsupported")
    supplied = root.pop("snapshot_digest")
    if _digest(supplied) != hashlib.sha256(_canonical(root)).digest():
        raise FederationSnapshotRejected("snapshot digest mismatch")
    root["snapshot_digest"] = supplied
    state_value = root["state"]
    if type(state_value) is not dict or set(state_value) != {
        "accepted",
        "pending",
        "quarantine",
        "replay",
        "static_policies",
        "tombstones",
    }:
        raise FederationSnapshotRejected("snapshot state fields are invalid")
    try:
        accepted = tuple(
            AcceptedFederationObject(
                item["key"],
                item["generation"],
                item["sequence"],
                _digest(item["digest"]),
                item["kind"],
                _digest(item["operator"]),
                _digest(item["peer"]),
                _digest(item["service"]),
                tuple(_digest(value) for value in item["dependencies"]),
                item["valid_until"],
                item["fresh"],
                item["terminal"],
            )
            for item in state_value["accepted"]
        )
        policies = tuple(
            StaticRecoveryPolicy(
                _digest(item["policy_digest"]),
                tuple(_digest(value) for value in item["operators"]),
                _digest(item["service_id"]),
                item["scope"],
                tuple(item["allowed_triggers"]),
                item["activated_at"],
                item["expires_at"],
            )
            for item in state_value["static_policies"]
        )
        state = FederationState(
            accepted,
            tuple(state_value["tombstones"]),
            tuple((key, tuple(_digest(value) for value in digests)) for key, digests in state_value["quarantine"]),
            tuple((key, until) for key, until in state_value["pending"]),
            tuple((_digest(value), seen) for value, seen in state_value["replay"]),
            policies,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise FederationSnapshotRejected("snapshot state is invalid") from exc
    if _digest(root["state_digest"]) != state.digest or data != encode_state(state, created_at=root["created_at"]):
        raise FederationSnapshotRejected("snapshot state digest or encoding is invalid")
    return state


class FederationStateRepository:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.watermark_path = self.path.with_name(f".{self.path.name}.watermark")
        self._watermarks: dict[str, tuple[int, int, bytes]] = {}
        self._mutex = threading.RLock()

    def load(self) -> FederationState:
        with self._mutex:
            state = decode_state(self._read_bounded_regular_file())
            if self.watermark_path.exists() or self.watermark_path.is_symlink():
                durable = decode_state(self._read_bounded_regular_file(self.watermark_path))
                self._remember(durable)
                try:
                    self._require_retained(durable, state, created_at=0)
                except FederationSnapshotRejected:
                    if not self._same_or_higher_watermarks(state, durable):
                        raise
                    secure_write_private(self.path, encode_state(durable, created_at=0))
                    return durable
            self._check_watermarks(state)
            self._remember(state)
            return state

    def save(self, state: FederationState, *, created_at: int) -> None:
        with self._mutex:
            encoded = encode_state(state, created_at=created_at)
            if self.path.exists() or self.path.is_symlink():
                current = decode_state(self._read_bounded_regular_file())
                self._remember(current)
                self._require_retained(current, state, created_at=created_at)
            if self.watermark_path.exists() or self.watermark_path.is_symlink():
                durable = decode_state(self._read_bounded_regular_file(self.watermark_path))
                self._remember(durable)
                self._require_retained(durable, state, created_at=created_at)
            self._check_watermarks(state)
            ensure_private_directory(self.path.parent)
            secure_write_private(self.path, encoded)
            secure_write_private(self.watermark_path, encoded)
            self._remember(state)

    def _remember(self, state: FederationState) -> None:
        for item in state.accepted:
            self._watermarks[item.key] = (item.generation, item.sequence, item.object_digest)

    def _check_watermarks(self, state: FederationState) -> None:
        values = {item.key: (item.generation, item.sequence, item.object_digest) for item in state.accepted}
        for key, watermark in self._watermarks.items():
            candidate = values.get(key)
            if candidate is None or candidate[:2] < watermark[:2] or (candidate[:2] == watermark[:2] and candidate[2] != watermark[2]):
                raise FederationSnapshotRejected("snapshot rollback rejected")

    @staticmethod
    def _same_or_higher_watermarks(candidate: FederationState, current: FederationState) -> bool:
        values = {item.key: (item.generation, item.sequence) for item in candidate.accepted}
        return all(values.get(item.key, (0, 0)) >= (item.generation, item.sequence) for item in current.accepted)

    @staticmethod
    def _require_retained(current: FederationState, candidate: FederationState, *, created_at: int) -> None:
        if not set(current.tombstones) <= set(candidate.tombstones):
            raise FederationSnapshotRejected("snapshot removed retained tombstone")
        candidate_quarantine = dict(candidate.quarantine)
        for key, evidence in current.quarantine:
            if not set(evidence) <= set(candidate_quarantine.get(key, ())):
                raise FederationSnapshotRejected("snapshot removed retained quarantine evidence")
        candidate_replay = dict(candidate.replay)
        for digest, seen in current.replay:
            if digest not in candidate_replay and created_at - seen <= FederationProfile.replay_retention_min_seconds:
                raise FederationSnapshotRejected("snapshot removed retained replay state")

    def _read_bounded_regular_file(self, path: Path | None = None) -> bytes:
        target = self.path if path is None else path
        try:
            before = target.lstat()
            if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
                raise FederationSnapshotRejected("snapshot path is not a regular file")
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(target, flags)
        except (OSError, ValueError) as exc:
            raise FederationSnapshotRejected("snapshot file is unavailable") from exc
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise FederationSnapshotRejected("snapshot file changed during open")
            data = os.read(descriptor, MAX_FEDERATION_SNAPSHOT_BYTES + 1)
            if len(data) != opened.st_size or len(data) > MAX_FEDERATION_SNAPSHOT_BYTES:
                raise FederationSnapshotRejected("snapshot file is partial or oversized")
            return data
        finally:
            os.close(descriptor)
