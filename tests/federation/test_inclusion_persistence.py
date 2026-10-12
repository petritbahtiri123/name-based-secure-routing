"""Storage-neutral tests; the memory backend makes no filesystem durability claim."""

import hashlib
import json
from contextlib import contextmanager
from dataclasses import replace

import pytest

from scripts import inclusion_persistence as store
from scripts.revocation_inclusion_v2 import make_fixture


class MemoryStorage:
    def __init__(self):
        self.files = {}
        self.owned = False
        self.writes = []
        self.fail = None
        self.hook = None
        self.fail_release = False

    @contextmanager
    def exclusive(self):
        if self.owned:
            raise store.StorageUnavailable("owned")
        self.owned = True
        try:
            yield
        finally:
            self.owned = False
            if self.fail_release:
                raise OSError("ownership release failed")

    def read(self, name):
        return self.files.get(name)

    def replace(self, name, data):
        self.writes.append(name)
        if self.hook:
            self.hook()
        if self.fail == (name, "before"):
            raise OSError("before replace")
        self.files[name] = data
        if self.fail == (name, "after"):
            raise OSError("after replace")


def repository(backend):
    return store.Repository(backend, context_binding=b"C" * 32)


def initialized():
    backend = MemoryStorage()
    repo = repository(backend)
    raw, context, initial = make_fixture()
    decision, snapshot = repo.initialize(raw, context, initial)
    assert decision["decision"] == "ACCEPT"
    return backend, repo, raw, context, snapshot


def test_roundtrip_reopen_and_idempotent_retry():
    backend, _, raw, context, snapshot = initialized()
    assert store.decode(store.encode(snapshot)) == snapshot
    reopened = repository(backend)
    assert reopened.load(snapshot.digest) == snapshot
    writes = list(backend.writes)
    result, repeated = reopened.apply(raw, context, snapshot.digest)
    assert result["decision"] == "IDEMPOTENT"
    assert repeated == snapshot
    assert backend.writes == writes


@pytest.mark.parametrize("name", [store.WATERMARK, store.PRIMARY])
@pytest.mark.parametrize("stage", ["before", "after"])
def test_uncertain_write_latches_and_recovers_only_exact_expected(name, stage):
    backend, repo, raw, _, first = initialized()
    raw2, context2, _ = make_fixture(previous_package=raw, event_id=b"2" * 32)
    backend.fail = (name, stage)
    with pytest.raises(store.StorageUnavailable):
        repo.apply(raw2, context2, first.digest)
    assert not backend.owned
    with pytest.raises(store.StorageUnavailable):
        repo.load(first.digest)
    backend.fail = None
    candidate = store.decode(backend.files[store.WATERMARK])
    if candidate != first:
        with pytest.raises(store.SnapshotRejected):
            repository(backend).load(first.digest)
    assert repository(backend).load(candidate.digest) == candidate
    assert backend.files[store.PRIMARY] == backend.files[store.WATERMARK]


def test_event_binding_survives_reopen_and_rejects_successor_reuse():
    backend, repo, raw, _, first = initialized()
    raw_again, context_again, _ = make_fixture(event_id=b"2" * 32)
    result, second = repo.apply(raw_again, context_again, first.digest)
    assert result["decision"] == "IDEMPOTENT"
    assert second.transaction == first.transaction + 1
    assert second.state.record == first.state.record
    next_raw, next_context, _ = make_fixture(previous_package=raw, event_id=b"2" * 32)
    before = dict(backend.files)
    result, unchanged = repository(backend).apply(next_raw, next_context, second.digest)
    assert result["decision"] == "REJECT"
    assert unchanged == second and backend.files == before


def test_joint_rollback_needs_independent_expected_digest():
    backend, repo, raw, _, first = initialized()
    old = dict(backend.files)
    raw2, context2, _ = make_fixture(previous_package=raw, event_id=b"2" * 32)
    _, second = repo.apply(raw2, context2, first.digest)
    backend.files = old
    with pytest.raises(store.SnapshotRejected):
        repository(backend).load(second.digest)
    assert repository(backend).load(first.digest) == first  # Explicit trust limitation.


def test_two_instances_cannot_enter_during_commit():
    backend, repo, raw, _, first = initialized()
    other = repository(backend)

    def concurrent():
        with pytest.raises(store.StorageUnavailable):
            other.load(first.digest)

    backend.hook = concurrent
    raw2, context2, _ = make_fixture(previous_package=raw, event_id=b"2" * 32)
    _, second = repo.apply(raw2, context2, first.digest)
    assert second.state.record != first.state.record
    assert not backend.owned


@pytest.mark.parametrize("name", [store.PRIMARY, store.WATERMARK])
@pytest.mark.parametrize("bad", [b"", b"{", b"x" * 262145], ids=["empty", "truncated", "oversized"])
def test_corrupt_copies_never_fallback(name, bad):
    backend, _, _, _, snapshot = initialized()
    backend.files[name] = bad
    before = dict(backend.files)
    with pytest.raises(store.SnapshotRejected):
        repository(backend).load(snapshot.digest)
    assert backend.files == before


def test_missing_state_never_automatically_bootstraps():
    backend = MemoryStorage()
    with pytest.raises(store.SnapshotRejected):
        repository(backend).load(b"X" * 32)
    assert backend.files == {}


def test_exact_original_record_digest_is_retained():
    _, _, _, _, snapshot = initialized()
    assert hashlib.sha256(snapshot.state.record).digest() in snapshot.state.retained_revocations


def tampered(snapshot, change):
    value = json.loads(store.encode(snapshot))
    change(value)
    value.pop("snapshot_digest")

    def canonical(v):
        return json.dumps(v, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")

    value["snapshot_digest"] = hashlib.sha256(canonical(value)).hexdigest()
    return canonical(value) + b"\n"


@pytest.mark.parametrize(
    "change",
    [
        lambda v: v.update(schema=True),
        lambda v: v.update(format="other"),
        lambda v: v.update(profile="other"),
        lambda v: v.update(transaction=True),
        lambda v: v.update(transaction=0),
        lambda v: v.update(extra=0),
        lambda v: v.pop("profile"),
        lambda v: v["state"].update(extra=0),
        lambda v: v["state"].update(log_id="00"),
        lambda v: v["state"].update(target_cbor="00"),
        lambda v: v["state"].update(scope_cbor="00"),
        lambda v: v["state"].update(floor="AA" * 32),
        lambda v: v["state"].update(retained_revocations=[]),
        lambda v: v["state"].update(requests=[]),
        lambda v: v["state"]["requests"].append(v["state"]["requests"][0]),
        lambda v: v["state"]["requests"][0].__setitem__(1, "ab" * 32),
    ],
)
def test_closed_codec_rejects_even_rehashed_invalid_semantics(change):
    _, _, _, _, snapshot = initialized()
    with pytest.raises(store.SnapshotRejected):
        store.decode(tampered(snapshot, change))


def test_duplicate_fields_noncanonical_encoding_and_digest_corruption():
    _, _, _, _, snapshot = initialized()
    data = store.encode(snapshot)
    for bad in (b'{"schema":1,' + data[1:], data + b" ", data.replace(b'"transaction":1', b'"transaction":2')):
        with pytest.raises(store.SnapshotRejected):
            store.decode(bad)


@pytest.mark.parametrize("name", [store.PRIMARY, store.WATERMARK])
def test_missing_copy_requires_exact_expectation_or_rejects(name):
    backend, _, _, _, snapshot = initialized()
    del backend.files[name]
    before = dict(backend.files)
    with pytest.raises(store.SnapshotRejected):
        repository(backend).load(b"X" * 32)
    assert backend.files == before
    if name == store.PRIMARY:
        assert repository(backend).load(snapshot.digest) == snapshot
    else:
        with pytest.raises(store.SnapshotRejected):
            repository(backend).load(snapshot.digest)


def test_repair_failure_latches_and_retains_candidate():
    backend, _, _, _, snapshot = initialized()
    del backend.files[store.PRIMARY]
    backend.fail = (store.PRIMARY, "after")
    repo = repository(backend)
    with pytest.raises(store.StorageUnavailable):
        repo.load(snapshot.digest)
    with pytest.raises(store.StorageUnavailable):
        repo.load(snapshot.digest)
    assert store.decode(backend.files[store.WATERMARK]) == snapshot
    assert not backend.owned


def test_rebootstrap_and_stale_lock_cannot_replace_owned_state():
    backend, repo, raw, context, snapshot = initialized()
    _, _, initial = make_fixture()
    before = dict(backend.files)
    with pytest.raises(store.SnapshotRejected):
        repo.initialize(raw, context, initial)
    backend.owned = True
    with pytest.raises(store.StorageUnavailable):
        repo.apply(raw, context, snapshot.digest)
    assert backend.owned and backend.files == before


@pytest.mark.parametrize(
    "change",
    [
        lambda s: replace(s, transaction=s.transaction + 2),
        lambda s: replace(s, previous_snapshot_digest=b"X" * 32),
        lambda s: replace(s, context_binding=b"X" * 32),
        lambda s: replace(s, amendment_sha256=b"X" * 32),
        lambda s: replace(s, state=replace(s.state, requests=s.state.requests[1:])),
        lambda s: replace(s, state=replace(s.state, floor=b"X" * 32)),
    ],
)
def test_recovery_rejects_gap_context_and_retained_fact_drift(change):
    backend, repo, _, _, first = initialized()
    raw2, context2, _ = make_fixture(event_id=b"2" * 32)
    _, second = repo.apply(raw2, context2, first.digest)
    bad = change(second)
    backend.files[store.PRIMARY] = store.encode(first)
    backend.files[store.WATERMARK] = store.encode(bad)
    before = dict(backend.files)
    with pytest.raises(store.SnapshotRejected):
        repository(backend).load(bad.digest)
    assert backend.files == before


def test_primary_ahead_never_promotes_or_rolls_back():
    backend, repo, raw, _, first = initialized()
    raw2, context2, _ = make_fixture(previous_package=raw, event_id=b"2" * 32)
    _, second = repo.apply(raw2, context2, first.digest)
    backend.files[store.WATERMARK] = store.encode(first)
    with pytest.raises(store.SnapshotRejected):
        repository(backend).load(second.digest)


def test_terminal_record_remains_terminal_after_reopen():
    backend = MemoryStorage()
    raw, context, initial = make_fixture(terminal=True)
    _, first = repository(backend).initialize(raw, context, initial)
    raw2, context2, _ = make_fixture(previous_package=raw, event_id=b"2" * 32)
    before = dict(backend.files)
    result, same = repository(backend).apply(raw2, context2, first.digest)
    assert result["decision"] == "REJECT" and same == first
    assert backend.files == before


def test_codec_capacity_limits_preserve_existing_state():
    backend, _, _, _, snapshot = initialized()
    digest = hashlib.sha256(snapshot.state.record).digest()
    # Byte ceiling can bind before the aggregate entry ceiling.
    for count in (3000, 4095):
        state = replace(snapshot.state, requests=tuple((i.to_bytes(16, "big"), digest) for i in range(count)))
        with pytest.raises(store.SnapshotRejected):
            store.encode(replace(snapshot, state=state))
    assert store.decode(backend.files[store.PRIMARY]) == snapshot


def test_wrong_predecessor_never_writes():
    backend, repo, raw, context, _ = initialized()
    before = dict(backend.files)
    with pytest.raises(store.SnapshotRejected):
        repo.apply(raw, context, b"X" * 32)
    assert backend.files == before


@pytest.mark.parametrize("operation", ["initialize", "apply", "repair"])
def test_post_write_release_failure_latches_uncertain_commit(operation):
    backend, repo, raw, context, first = initialized()
    if operation == "initialize":
        backend.files.clear()
        _, _, initial = make_fixture()

        def action():
            return repo.initialize(raw, context, initial)
    elif operation == "repair":
        del backend.files[store.PRIMARY]

        def action():
            return repo.load(first.digest)
    else:
        raw2, context2, _ = make_fixture(event_id=b"2" * 32)

        def action():
            return repo.apply(raw2, context2, first.digest)

    backend.fail_release = True
    with pytest.raises(store.StorageUnavailable):
        action()
    backend.fail_release = False
    candidate = store.decode(backend.files[store.WATERMARK])
    with pytest.raises(store.StorageUnavailable):
        repo.load(candidate.digest)
    assert repository(backend).load(candidate.digest) == candidate


def test_reentrant_callback_cannot_clear_uncertain_commit_tracking():
    backend, repo, _, _, first = initialized()

    def callback():
        with pytest.raises(store.StorageUnavailable):
            repo.load(first.digest)

    backend.hook = callback
    backend.fail_release = True
    raw2, context2, _ = make_fixture(event_id=b"2" * 32)
    with pytest.raises(store.StorageUnavailable):
        repo.apply(raw2, context2, first.digest)
    backend.fail_release = False
    backend.hook = None
    with pytest.raises(store.StorageUnavailable):
        repo.load(store.decode(backend.files[store.WATERMARK]).digest)
