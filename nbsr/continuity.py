"""Storage-neutral WP6 continuity state.

This is an internal deterministic prototype, not a wire or consensus protocol.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import StrEnum


MAX_UINT64 = 2**64 - 1
MAX_TIMESTAMP = 253_402_300_799
MAX_RECORDS = 4096
_TEXT_ID = re.compile(r"[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*\Z")
_OBJECT_ID = re.compile(r"[0-9a-f]{2,64}\Z")
_RECORD_DOMAIN = "nbsr-continuity-record-v1"


class StateRejected(ValueError):
    """A continuity candidate cannot be accepted safely."""


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
