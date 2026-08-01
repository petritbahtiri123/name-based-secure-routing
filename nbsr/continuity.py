"""Storage-neutral WP6 continuity state.

This is an internal deterministic prototype, not a wire or consensus protocol.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from nbsr.secure_files import secure_write_private


MAX_UINT64 = 2**64 - 1
MAX_TIMESTAMP = 253_402_300_799
MAX_RECORDS = 4096
MAX_REPLICAS = 32
MAX_SNAPSHOT_BYTES = 256 * 1024
_TEXT_ID = re.compile(r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*\Z")
_OBJECT_ID = re.compile(r"[0-9a-f]{2,64}\Z")
_RECORD_DOMAIN = "nbsr-continuity-record-v1"
_SNAPSHOT_SCHEMA = "nbsr-continuity-snapshot-v1"


class StateRejected(ValueError):
    """A continuity candidate cannot be accepted safely."""


class SnapshotRejected(StateRejected):
    """A snapshot cannot be trusted or decoded safely."""


class QuorumRejected(StateRejected):
    """Replica evidence cannot support an unambiguous fail-closed read."""


class ContinuityDenied(StateRejected):
    """Replicated state does not authorize local continuity."""


class StateKind(StrEnum):
    ORIGIN = "origin"
    POLICY = "policy"
    REVOCATION = "revocation"
    REPLAY = "replay"
    TOMBSTONE = "tombstone"
    GRANT = "grant"
    CHANNEL = "channel"


def _text_id(value: object) -> str:
    if type(value) is not str or len(value) > 64 or _TEXT_ID.fullmatch(value) is None:
        raise StateRejected("invalid state key")
    return value


def _uint(name: str, value: object, *, minimum: int = 0, maximum: int = MAX_UINT64) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise StateRejected(f"{name} is outside its accepted range")
    return value


def _digest(name: str, value: object, *, optional: bool = False) -> bytes | None:
    if optional and value is None:
        return None
    if type(value) is not bytes or len(value) != 32:
        raise StateRejected(f"{name} must be a 32-byte digest")
    return bytes(value)


@dataclass(frozen=True, slots=True, order=True)
class StateKey:
    tenant_id: str
    service_id: str
    kind: StateKind | str
    object_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenant_id", _text_id(self.tenant_id))
        object.__setattr__(self, "service_id", _text_id(self.service_id))
        try:
            kind = self.kind if isinstance(self.kind, StateKind) else StateKind(self.kind)
        except (TypeError, ValueError) as exc:
            raise StateRejected("invalid state key") from exc
        if type(self.object_id) is not str or _OBJECT_ID.fullmatch(self.object_id) is None:
            raise StateRejected("invalid state key")
        object.__setattr__(self, "kind", kind)

    def canonical_value(self) -> list[str]:
        return [self.tenant_id, self.service_id, self.kind.value, self.object_id]


@dataclass(frozen=True, slots=True)
class ContinuityRecord:
    key: StateKey
    generation: int
    sequence: int
    authority_digest: bytes
    previous_digest: bytes | None
    expires_at: int
    retained_until: int
    terminal: bool
    content_digest: bytes = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if type(self.key) is not StateKey:
            raise StateRejected("key must be a StateKey")
        object.__setattr__(self, "generation", _uint("generation", self.generation, minimum=1))
        object.__setattr__(self, "sequence", _uint("sequence", self.sequence, minimum=1))
        object.__setattr__(self, "authority_digest", _digest("authority_digest", self.authority_digest))
        object.__setattr__(self, "previous_digest", _digest("previous_digest", self.previous_digest, optional=True))
        object.__setattr__(self, "expires_at", _uint("expires_at", self.expires_at, maximum=MAX_TIMESTAMP))
        object.__setattr__(self, "retained_until", _uint("retained_until", self.retained_until, maximum=MAX_TIMESTAMP))
        if self.retained_until < self.expires_at:
            raise StateRejected("retained_until cannot precede expires_at")
        if type(self.terminal) is not bool:
            raise StateRejected("terminal must be a boolean")
        object.__setattr__(self, "content_digest", hashlib.sha256(self.canonical_bytes()).digest())

    @property
    def version(self) -> tuple[int, int]:
        return (self.generation, self.sequence)

    def canonical_value(self) -> list[object]:
        return [
            _RECORD_DOMAIN,
            self.key.canonical_value(),
            self.generation,
            self.sequence,
            self.authority_digest.hex(),
            self.previous_digest.hex() if self.previous_digest is not None else None,
            self.expires_at,
            self.retained_until,
            self.terminal,
        ]

    def canonical_bytes(self) -> bytes:
        return json.dumps(self.canonical_value(), ensure_ascii=True, separators=(",", ":")).encode("ascii")


@dataclass(frozen=True, slots=True)
class ContinuityState:
    tenant_id: str
    records: tuple[ContinuityRecord, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenant_id", _text_id(self.tenant_id))
        if type(self.records) not in (tuple, list) or len(self.records) > MAX_RECORDS:
            raise StateRejected("state exceeds record capacity")
        if any(type(item) is not ContinuityRecord for item in self.records):
            raise StateRejected("state contains an invalid record")
        ordered = tuple(sorted(self.records, key=lambda item: item.key))
        if any(item.key.tenant_id != self.tenant_id for item in ordered):
            raise StateRejected("record tenant does not match state tenant")
        if len({item.key for item in ordered}) != len(ordered):
            raise StateRejected("state contains duplicate keys")
        object.__setattr__(self, "records", ordered)

    @classmethod
    def empty(cls, tenant_id: str) -> ContinuityState:
        return cls(tenant_id)

    def get(self, key: StateKey) -> ContinuityRecord | None:
        if type(key) is not StateKey or key.tenant_id != self.tenant_id:
            return None
        return next((item for item in self.records if item.key == key), None)

    def apply(self, candidate: ContinuityRecord) -> ContinuityState:
        if type(candidate) is not ContinuityRecord:
            raise StateRejected("candidate must be a ContinuityRecord")
        if candidate.key.tenant_id != self.tenant_id:
            raise StateRejected("candidate tenant does not match state tenant")
        current = self.get(candidate.key)
        if current is None:
            if candidate.previous_digest is not None:
                raise StateRejected("initial candidate has an unavailable previous digest")
            if len(self.records) >= MAX_RECORDS:
                raise StateRejected("state is at capacity")
            return ContinuityState(self.tenant_id, (*self.records, candidate))
        if candidate.generation < current.generation or candidate.sequence < current.sequence:
            raise StateRejected("stale candidate would roll state back")
        if candidate.version == current.version:
            if candidate.content_digest != current.content_digest:
                raise StateRejected("same-version equivocation")
            return self
        if current.terminal and not candidate.terminal:
            raise StateRejected("terminal state cannot be resurrected")
        if candidate.previous_digest != current.content_digest:
            raise StateRejected("candidate previous digest does not match retained state")
        updated = tuple(item for item in self.records if item.key != candidate.key)
        return ContinuityState(self.tenant_id, (*updated, candidate))


@dataclass(frozen=True, slots=True)
class ReplicaConfig:
    tenant_id: str
    replica_set_id: str
    replica_ids: tuple[str, ...]
    quorum: int

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "tenant_id", _text_id(self.tenant_id))
            object.__setattr__(self, "replica_set_id", _text_id(self.replica_set_id))
            if type(self.replica_ids) not in (tuple, list) or not 1 <= len(self.replica_ids) <= MAX_REPLICAS:
                raise SnapshotRejected("replica count is outside bounds")
            if any(type(item) is not str for item in self.replica_ids):
                raise SnapshotRejected("replica identity is invalid")
            checked = tuple(sorted(_text_id(item) for item in self.replica_ids))
            if len(set(checked)) != len(checked):
                raise SnapshotRejected("replica identities must be unique")
            object.__setattr__(self, "replica_ids", checked)
            quorum = _uint("quorum", self.quorum, minimum=1, maximum=len(checked))
            if quorum <= len(checked) // 2:
                raise SnapshotRejected("quorum must be a strict majority")
            object.__setattr__(self, "quorum", quorum)
        except StateRejected as exc:
            if isinstance(exc, SnapshotRejected):
                raise
            raise SnapshotRejected(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class ContinuitySnapshot:
    config: ReplicaConfig
    generation: int
    created_at: int
    state: ContinuityState
    snapshot_digest: bytes = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if type(self.config) is not ReplicaConfig or type(self.state) is not ContinuityState:
            raise SnapshotRejected("snapshot context is invalid")
        if self.config.tenant_id != self.state.tenant_id:
            raise SnapshotRejected("snapshot tenant contexts do not match")
        try:
            object.__setattr__(self, "generation", _uint("snapshot generation", self.generation, minimum=1))
            object.__setattr__(self, "created_at", _uint("created_at", self.created_at, maximum=MAX_TIMESTAMP))
        except StateRejected as exc:
            raise SnapshotRejected(str(exc)) from exc
        object.__setattr__(self, "snapshot_digest", hashlib.sha256(_snapshot_payload_bytes(self)).digest())


def _record_object(item: ContinuityRecord) -> dict[str, object]:
    return {
        "authority_digest": item.authority_digest.hex(),
        "expires_at": item.expires_at,
        "generation": item.generation,
        "key": item.key.canonical_value(),
        "previous_digest": item.previous_digest.hex() if item.previous_digest is not None else None,
        "retained_until": item.retained_until,
        "sequence": item.sequence,
        "terminal": item.terminal,
    }


def _snapshot_payload(snapshot: ContinuitySnapshot) -> dict[str, object]:
    return {
        "created_at": snapshot.created_at,
        "generation": snapshot.generation,
        "quorum": snapshot.config.quorum,
        "records": [_record_object(item) for item in snapshot.state.records],
        "replica_ids": list(snapshot.config.replica_ids),
        "replica_set_id": snapshot.config.replica_set_id,
        "schema": _SNAPSHOT_SCHEMA,
        "tenant_id": snapshot.config.tenant_id,
    }


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")


def _snapshot_payload_bytes(snapshot: ContinuitySnapshot) -> bytes:
    return _canonical_json(_snapshot_payload(snapshot))


def encode_snapshot(snapshot: ContinuitySnapshot) -> bytes:
    if type(snapshot) is not ContinuitySnapshot:
        raise SnapshotRejected("snapshot must be a ContinuitySnapshot")
    value = _snapshot_payload(snapshot)
    value["snapshot_digest"] = snapshot.snapshot_digest.hex()
    encoded = _canonical_json(value) + b"\n"
    if len(encoded) > MAX_SNAPSHOT_BYTES:
        raise SnapshotRejected("snapshot exceeds encoded size limit")
    return encoded


def _closed(value: object, fields: frozenset[str], name: str) -> dict[str, object]:
    if type(value) is not dict or frozenset(value) != fields:
        raise SnapshotRejected(f"{name} has unknown or missing fields")
    return value


def _hex_digest(value: object, name: str) -> bytes:
    if type(value) is not str or len(value) != 64:
        raise SnapshotRejected(f"{name} is invalid")
    try:
        decoded = bytes.fromhex(value)
    except ValueError as exc:
        raise SnapshotRejected(f"{name} is invalid") from exc
    if len(decoded) != 32 or value != decoded.hex():
        raise SnapshotRejected(f"{name} is invalid")
    return decoded


def decode_snapshot(data: bytes) -> ContinuitySnapshot:
    if type(data) is not bytes or not data or len(data) > MAX_SNAPSHOT_BYTES:
        raise SnapshotRejected("snapshot input size is invalid")
    try:
        value = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SnapshotRejected("snapshot is not valid JSON") from exc
    root = _closed(
        value,
        frozenset(
            {
                "created_at",
                "generation",
                "quorum",
                "records",
                "replica_ids",
                "replica_set_id",
                "schema",
                "snapshot_digest",
                "tenant_id",
            },
        ),
        "snapshot",
    )
    if root["schema"] != _SNAPSHOT_SCHEMA:
        raise SnapshotRejected("snapshot schema is unsupported")
    if type(root["records"]) is not list or len(root["records"]) > MAX_RECORDS:
        raise SnapshotRejected("snapshot record count is invalid")
    config = ReplicaConfig(root["tenant_id"], root["replica_set_id"], root["replica_ids"], root["quorum"])  # type: ignore[arg-type]
    if root["replica_ids"] != list(config.replica_ids):
        raise SnapshotRejected("replica identities are not canonical")
    records: list[ContinuityRecord] = []
    record_fields = frozenset(
        {"authority_digest", "expires_at", "generation", "key", "previous_digest", "retained_until", "sequence", "terminal"},
    )
    for raw in root["records"]:
        item = _closed(raw, record_fields, "record")
        key_value = item["key"]
        if type(key_value) is not list or len(key_value) != 4:
            raise SnapshotRejected("record key is invalid")
        previous = item["previous_digest"]
        records.append(
            ContinuityRecord(
                StateKey(*key_value),
                item["generation"],
                item["sequence"],
                _hex_digest(item["authority_digest"], "authority_digest"),
                None if previous is None else _hex_digest(previous, "previous_digest"),
                item["expires_at"],
                item["retained_until"],
                item["terminal"],
            ),
        )
    try:
        state = ContinuityState(config.tenant_id, tuple(records))
    except StateRejected as exc:
        raise SnapshotRejected(str(exc)) from exc
    if records != list(state.records):
        raise SnapshotRejected("snapshot records are not canonical")
    snapshot = ContinuitySnapshot(config, root["generation"], root["created_at"], state)  # type: ignore[arg-type]
    supplied = _hex_digest(root["snapshot_digest"], "snapshot_digest")
    if supplied != snapshot.snapshot_digest:
        raise SnapshotRejected("snapshot digest mismatch")
    if data != encode_snapshot(snapshot):
        raise SnapshotRejected("snapshot encoding is not canonical")
    return snapshot


class SnapshotRepository:
    """Private-file adapter for one deterministic snapshot."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def load(self, *, minimum_generation: int = 1) -> ContinuitySnapshot:
        checked_minimum = _uint("minimum_generation", minimum_generation, minimum=1)
        snapshot = decode_snapshot(self._read_bounded_regular_file())
        if snapshot.generation < checked_minimum:
            raise SnapshotRejected("snapshot rollback rejected")
        return snapshot

    def save(self, snapshot: ContinuitySnapshot) -> None:
        encoded = encode_snapshot(snapshot)
        if self.path.exists() or self.path.is_symlink():
            current = self.load()
            if snapshot.config != current.config:
                raise SnapshotRejected("snapshot context mismatch")
            if snapshot.generation < current.generation:
                raise SnapshotRejected("snapshot rollback rejected")
            if snapshot.generation == current.generation and snapshot.snapshot_digest != current.snapshot_digest:
                raise SnapshotRejected("snapshot generation equivocation")
        secure_write_private(self.path, encoded)

    def _read_bounded_regular_file(self) -> bytes:
        try:
            before = self.path.lstat()
            if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
                raise SnapshotRejected("snapshot path is not a regular file")
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(self.path, flags)
        except (OSError, ValueError) as exc:
            raise SnapshotRejected("snapshot file is unavailable") from exc
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise SnapshotRejected("snapshot file changed during open")
            if opened.st_size > MAX_SNAPSHOT_BYTES:
                raise SnapshotRejected("snapshot file exceeds size limit")
            data = os.read(descriptor, MAX_SNAPSHOT_BYTES + 1)
            if len(data) != opened.st_size or len(data) > MAX_SNAPSHOT_BYTES:
                raise SnapshotRejected("snapshot file is partial or oversized")
            return data
        finally:
            os.close(descriptor)


@dataclass(frozen=True, slots=True)
class ReplicaObservation:
    replica_id: str
    snapshot: ContinuitySnapshot | None
    complete: bool

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "replica_id", _text_id(self.replica_id))
        except StateRejected as exc:
            raise QuorumRejected("replica identity is invalid") from exc
        if self.snapshot is not None and type(self.snapshot) is not ContinuitySnapshot:
            raise QuorumRejected("replica snapshot is invalid")
        if type(self.complete) is not bool:
            raise QuorumRejected("replica completeness is invalid")


@dataclass(frozen=True, slots=True)
class QuorumView:
    snapshot: ContinuitySnapshot
    replica_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.snapshot) is not ContinuitySnapshot:
            raise QuorumRejected("quorum snapshot is invalid")
        if type(self.replica_ids) is not tuple or self.replica_ids != tuple(sorted(set(self.replica_ids))):
            raise QuorumRejected("quorum replica identities are invalid")


def resolve_quorum(
    config: ReplicaConfig,
    observations: tuple[ReplicaObservation, ...] | list[ReplicaObservation],
    *,
    minimum_generation: int,
) -> QuorumView:
    if type(config) is not ReplicaConfig or type(observations) not in (tuple, list):
        raise QuorumRejected("quorum input is invalid")
    try:
        checked_minimum = _uint("minimum_generation", minimum_generation, minimum=1)
    except StateRejected as exc:
        raise QuorumRejected(str(exc)) from exc
    if any(type(item) is not ReplicaObservation for item in observations):
        raise QuorumRejected("replica observation is invalid")
    identities = [item.replica_id for item in observations]
    if len(set(identities)) != len(identities):
        raise QuorumRejected("duplicate replica identity")
    if any(identity not in config.replica_ids for identity in identities):
        raise QuorumRejected("unknown replica identity")

    complete: list[ReplicaObservation] = []
    for item in observations:
        if not item.complete:
            if item.snapshot is not None:
                raise QuorumRejected("partial replica state")
            continue
        if item.snapshot is None:
            raise QuorumRejected("partial replica state")
        if item.snapshot.config != config:
            raise QuorumRejected("replica snapshot context mismatch")
        if item.snapshot.generation < checked_minimum:
            raise QuorumRejected("stale replica snapshot")
        complete.append(item)
    if len(complete) < config.quorum:
        raise QuorumRejected("replica quorum is unavailable")

    groups: dict[tuple[int, bytes], list[ReplicaObservation]] = {}
    for item in complete:
        assert item.snapshot is not None
        groups.setdefault((item.snapshot.generation, item.snapshot.snapshot_digest), []).append(item)
    if len(groups) != 1:
        raise QuorumRejected("conflicting replica snapshots")
    agreed = next(iter(groups.values()))
    if len(agreed) < config.quorum:
        raise QuorumRejected("replica quorum is unavailable")
    snapshot = agreed[0].snapshot
    assert snapshot is not None
    return QuorumView(snapshot, tuple(sorted(item.replica_id for item in agreed)))


MAX_FAILOVER_MILLISECONDS = 5_000
MAX_DRAIN_SECONDS = 30


def bounded_failover(
    config: ReplicaConfig,
    observations: tuple[ReplicaObservation, ...] | list[ReplicaObservation],
    *,
    minimum_generation: int,
    elapsed_ms: int,
) -> QuorumView:
    if type(elapsed_ms) is not int or not 0 <= elapsed_ms <= MAX_FAILOVER_MILLISECONDS:
        raise QuorumRejected("failover elapsed time is invalid or exceeds the bound")
    return resolve_quorum(config, observations, minimum_generation=minimum_generation)


@dataclass(frozen=True, slots=True)
class ContinuityPermit:
    tenant_id: str
    service_id: str
    channel_digest: bytes
    policy_fingerprint: bytes
    snapshot_digest: bytes


def _required_record(state: ContinuityState, key: StateKey, *, now: int) -> ContinuityRecord:
    item = state.get(key)
    if item is None:
        raise ContinuityDenied("required continuity state is missing")
    if item.terminal:
        raise ContinuityDenied("required continuity state is terminal")
    if now >= item.expires_at:
        raise ContinuityDenied("required continuity state is expired")
    return item


def evaluate_continuity(
    *,
    view: QuorumView,
    tenant_id: str,
    service_id: str,
    channel_id: str,
    grant_id: str,
    replay_id: str,
    policy_fingerprint: bytes,
    now: int,
) -> ContinuityPermit:
    if type(view) is not QuorumView:
        raise ContinuityDenied("quorum view is invalid")
    try:
        checked_tenant = _text_id(tenant_id)
        checked_service = _text_id(service_id)
        checked_now = _uint("now", now, maximum=MAX_TIMESTAMP)
        checked_policy = _digest("policy_fingerprint", policy_fingerprint)
        assert checked_policy is not None
        policy_key = StateKey(checked_tenant, checked_service, StateKind.POLICY, "00")
        channel_key = StateKey(checked_tenant, checked_service, StateKind.CHANNEL, channel_id)
        grant_key = StateKey(checked_tenant, checked_service, StateKind.GRANT, grant_id)
        replay_key = StateKey(checked_tenant, checked_service, StateKind.REPLAY, replay_id)
    except StateRejected as exc:
        raise ContinuityDenied("continuity input context is invalid") from exc
    snapshot = view.snapshot
    if snapshot.config.tenant_id != checked_tenant or snapshot.state.tenant_id != checked_tenant:
        raise ContinuityDenied("continuity tenant context mismatch")
    terminal_kinds = {StateKind.REVOCATION, StateKind.TOMBSTONE}
    if any(
        item.key.service_id == checked_service and item.key.kind in terminal_kinds and item.terminal and checked_now < item.retained_until
        for item in snapshot.state.records
    ):
        raise ContinuityDenied("terminal revocation or tombstone state denies continuity")
    policy = _required_record(snapshot.state, policy_key, now=checked_now)
    if policy.authority_digest != checked_policy:
        raise ContinuityDenied("policy fingerprint does not match current state")
    channel = _required_record(snapshot.state, channel_key, now=checked_now)
    _required_record(snapshot.state, grant_key, now=checked_now)
    _required_record(snapshot.state, replay_key, now=checked_now)
    return ContinuityPermit(
        checked_tenant,
        checked_service,
        channel.authority_digest,
        checked_policy,
        snapshot.snapshot_digest,
    )


def drain_deadline(*, now: int, requested_seconds: int, authority_expires_at: int) -> int:
    try:
        checked_now = _uint("now", now, maximum=MAX_TIMESTAMP)
        checked_request = _uint("requested_seconds", requested_seconds, maximum=MAX_TIMESTAMP)
        checked_expiry = _uint("authority_expires_at", authority_expires_at, maximum=MAX_TIMESTAMP)
    except StateRejected as exc:
        raise ContinuityDenied("drain timing is invalid") from exc
    if checked_expiry < checked_now:
        raise ContinuityDenied("drain authority is expired")
    return min(checked_now + min(checked_request, MAX_DRAIN_SECONDS), checked_expiry)
