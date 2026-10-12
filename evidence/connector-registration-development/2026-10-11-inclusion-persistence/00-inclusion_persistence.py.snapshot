"""Storage-neutral inclusion conformance; no filesystem adapter or runtime trust.

An injected backend must own serialization and atomic replacement. Tests use
memory only. Neither local hashes nor this coordinator establish durable trust.
"""

from __future__ import annotations

import hashlib
import json
import threading
from contextlib import contextmanager
from dataclasses import dataclass, replace
from typing import ContextManager, Protocol

from nbsr.federation.store import MAX_FEDERATION_RECORDS, MAX_FEDERATION_SNAPSHOT_BYTES
from nbsr.protocol.cbor import encode_deterministic
from scripts.revocation_inclusion_v2 import AMENDMENT, PROFILE, FixtureState, parse_record, verify_package

FORMAT = "nbsr-inclusion-local-snapshot-v1"
PRIMARY = "inclusion.json"
WATERMARK = ".inclusion.json.watermark"


class SnapshotRejected(ValueError):
    pass


class StorageUnavailable(RuntimeError):
    pass


class Storage(Protocol):
    """No provided filesystem implementation. Missing reads return None.

    exclusive must serialize all cooperating instances without nested entry;
    replace must replace the whole value or raise (possibly after replacement).
    A real adapter additionally needs the approved private-write/path contract.
    """

    def exclusive(self) -> ContextManager[None]: ...
    def read(self, name: str) -> bytes | None: ...
    def replace(self, name: str, data: bytes) -> None: ...


def _canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")


def _bytes(value, minimum=32, maximum=32):
    if type(value) is not bytes or not minimum <= len(value) <= maximum:
        raise SnapshotRejected("invalid binary field")
    return value


def _hex(value, minimum=32, maximum=32):
    if type(value) is not str:
        raise SnapshotRejected("invalid hex")
    try:
        data = bytes.fromhex(value)
    except ValueError as exc:
        raise SnapshotRejected("invalid hex") from exc
    if data.hex() != value:
        raise SnapshotRejected("noncanonical hex")
    return _bytes(data, minimum, maximum)


@dataclass(frozen=True)
class Snapshot:
    state: FixtureState
    context_binding: bytes
    amendment_sha256: bytes
    transaction: int
    previous_snapshot_digest: bytes | None

    @property
    def digest(self):
        return hashlib.sha256(_canonical(_value(self))).digest()


def _value(snapshot):
    if type(snapshot) is not Snapshot or type(snapshot.state) is not FixtureState:
        raise SnapshotRejected("snapshot type")
    state = snapshot.state
    if type(snapshot.transaction) is not int or snapshot.transaction < 1:
        raise SnapshotRejected("transaction")
    if snapshot.transaction == 1:
        if snapshot.previous_snapshot_digest is not None:
            raise SnapshotRejected("initial predecessor")
    else:
        _bytes(snapshot.previous_snapshot_digest)
    _bytes(state.floor)
    _bytes(state.record, 1, 32768)
    try:
        record = parse_record(state.record)
    except (ValueError, TypeError, KeyError) as exc:
        raise SnapshotRejected("record") from exc
    if type(state.retained_revocations) is not frozenset or type(state.requests) is not tuple:
        raise SnapshotRejected("state containers")
    if 1 + len(state.retained_revocations) + len(state.requests) > MAX_FEDERATION_RECORDS:
        raise SnapshotRejected("record capacity")
    for digest in state.retained_revocations:
        _bytes(digest)
    if hashlib.sha256(state.record).digest() not in state.retained_revocations:
        raise SnapshotRejected("missing retained record")
    events = set()
    for pair in state.requests:
        if type(pair) is not tuple or len(pair) != 2:
            raise SnapshotRejected("request shape")
        event, digest = pair
        _bytes(event, 16, 64)
        _bytes(digest)
        if event in events or digest not in state.retained_revocations:
            raise SnapshotRejected("request binding")
        events.add(event)
    if not events:
        raise SnapshotRejected("missing request")
    return {
        "format": FORMAT,
        "schema": 1,
        "profile": PROFILE,
        "amendment_sha256": _bytes(snapshot.amendment_sha256).hex(),
        "context_binding": _bytes(snapshot.context_binding).hex(),
        "transaction": snapshot.transaction,
        "previous_snapshot_digest": None if snapshot.previous_snapshot_digest is None else snapshot.previous_snapshot_digest.hex(),
        "state": {
            "log_id": record[39][1].hex(),
            "scope_cbor": encode_deterministic(record[33]).hex(),
            "target_cbor": encode_deterministic(record[32]).hex(),
            "floor": state.floor.hex(),
            "record": state.record.hex(),
            "retained_revocations": sorted(d.hex() for d in state.retained_revocations),
            "requests": [[e.hex(), d.hex()] for e, d in sorted(state.requests)],
        },
    }


def encode(snapshot):
    root = _value(snapshot)
    root["snapshot_digest"] = hashlib.sha256(_canonical(root)).hexdigest()
    data = _canonical(root) + b"\n"
    if len(data) > MAX_FEDERATION_SNAPSHOT_BYTES:
        raise SnapshotRejected("snapshot capacity")
    return data


def _closed_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SnapshotRejected("duplicate field")
        result[key] = value
    return result


def decode(data):
    if type(data) is not bytes or not 0 < len(data) <= MAX_FEDERATION_SNAPSHOT_BYTES:
        raise SnapshotRejected("snapshot size")
    try:
        root = json.loads(data, object_pairs_hook=_closed_pairs)
        state = root["state"]
        snapshot = Snapshot(
            FixtureState(
                _hex(state["floor"]),
                _hex(state["record"], 1, 32768),
                frozenset(_hex(x) for x in state["retained_revocations"]),
                tuple((_hex(e, 16, 64), _hex(d)) for e, d in state["requests"]),
            ),
            _hex(root["context_binding"]),
            _hex(root["amendment_sha256"]),
            root["transaction"],
            None if root["previous_snapshot_digest"] is None else _hex(root["previous_snapshot_digest"]),
        )
        if encode(snapshot) != data:
            raise SnapshotRejected("noncanonical or mismatched snapshot")
        return snapshot
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
        raise SnapshotRejected("invalid snapshot") from exc


def _successor(previous, candidate):
    if (
        candidate.context_binding != previous.context_binding
        or candidate.amendment_sha256 != previous.amendment_sha256
        or candidate.transaction != previous.transaction + 1
        or candidate.previous_snapshot_digest != previous.digest
    ):
        raise SnapshotRejected("snapshot lineage/context")
    old, new = previous.state, candidate.state
    old_requests, new_requests = dict(old.requests), dict(new.requests)
    if any(new_requests.get(e) != d for e, d in old_requests.items()) or len(new_requests) != len(old_requests) + 1:
        raise SnapshotRejected("retained event binding")
    added = set(new.requests) - set(old.requests)
    digest = hashlib.sha256(new.record).digest()
    if len(added) != 1 or next(iter(added))[1] != digest:
        raise SnapshotRejected("new event binding")
    if old.record == new.record:
        if old.floor != new.floor or old.retained_revocations != new.retained_revocations:
            raise SnapshotRejected("idempotent floor/markers")
        return
    a, b = parse_record(old.record), parse_record(new.record)
    if (
        a[35]
        or a[32] != b[32]
        or a[33] != b[33]
        or a[39][1] != b[39][1]
        or b[4] != a[4]
        or b[5] != a[5] + 1
        or b.get(8) != hashlib.sha256(old.record).digest()
        or b[39][2] != old.floor
        or new.floor == old.floor
        or new.retained_revocations != old.retained_revocations | {digest}
    ):
        raise SnapshotRejected("record lineage/floor/markers")


class Repository:
    """Local coordinator. Expected digests and context provenance stay external.

    Storage failure latches this instance; construct a fresh instance to recover.
    No method invokes a filesystem writer, private ACL helper or runtime action.
    """

    def __init__(self, storage: Storage, *, context_binding: bytes):
        self.storage = storage
        self.context_binding = _bytes(context_binding)
        self.amendment = hashlib.sha256(AMENDMENT.read_bytes()).digest()
        self._mutex = threading.RLock()
        self._unavailable = False
        self._write_attempted = False
        self._active = False

    def _ready(self):
        if self._active:
            raise StorageUnavailable("reentrant repository operation")
        if self._unavailable:
            raise StorageUnavailable("uncertain commit; fresh instance required")

    def _read(self, name):
        data = self.storage.read(name)
        if data is None:
            return None
        snapshot = decode(data)
        if snapshot.context_binding != self.context_binding or snapshot.amendment_sha256 != self.amendment:
            raise SnapshotRejected("independent context mismatch")
        return snapshot

    def _write(self, name, data):
        self._write_attempted = True
        try:
            self.storage.replace(name, data)
        except Exception as exc:
            self._unavailable = True
            raise StorageUnavailable("uncertain storage commit") from exc

    @contextmanager
    def _owned(self):
        self._active = True
        self._write_attempted = False
        completed = False
        try:
            with self.storage.exclusive():
                yield
            completed = True
        except Exception as exc:
            if self._write_attempted:
                raise StorageUnavailable("uncertain commit or ownership release") from exc
            raise
        finally:
            # Also latch on interruption; never suppress KeyboardInterrupt/SystemExit.
            if self._write_attempted and not completed:
                self._unavailable = True
            self._active = False

    def _load(self, expected):
        _bytes(expected)
        primary, watermark = self._read(PRIMARY), self._read(WATERMARK)
        if watermark is None:
            raise SnapshotRejected("missing retained copy")
        if primary is not None and primary != watermark:
            _successor(primary, watermark)
        if watermark.digest != expected:
            raise SnapshotRejected("independent expected digest mismatch")
        if primary != watermark:
            self._write(PRIMARY, encode(watermark))
        return watermark

    def load(self, expected):
        with self._mutex:
            self._ready()
            with self._owned():
                return self._load(expected)

    def _commit(self, snapshot):
        data = encode(snapshot)  # Complete validation/capacity rejection before any write.
        self._write(WATERMARK, data)
        self._write(PRIMARY, data)

    def initialize(self, raw, context, initial):
        """Explicit fixture bootstrap only; never called automatically by load."""
        with self._mutex:
            self._ready()
            with self._owned():
                if self.storage.read(PRIMARY) is not None or self.storage.read(WATERMARK) is not None:
                    raise SnapshotRejected("bootstrap cannot replace existing state")
                if type(initial) is not FixtureState or initial.record is not None or initial.requests or initial.retained_revocations:
                    raise SnapshotRejected("nonempty bootstrap")
                result, state = verify_package(raw, context, initial)
                if result["decision"] != "ACCEPT":
                    return result, None
                state = replace(state, requests=tuple(sorted(state.requests)))
                snapshot = Snapshot(state, self.context_binding, self.amendment, 1, None)
                self._commit(snapshot)
                return result, snapshot

    def apply(self, raw, context, expected):
        with self._mutex:
            self._ready()
            with self._owned():
                previous = self._load(expected)
                result, state = verify_package(raw, context, previous.state)
                if state == previous.state:
                    return result, previous
                state = replace(state, requests=tuple(sorted(state.requests)))
                snapshot = Snapshot(state, self.context_binding, self.amendment, previous.transaction + 1, previous.digest)
                _successor(previous, snapshot)
                self._commit(snapshot)
                return result, snapshot
