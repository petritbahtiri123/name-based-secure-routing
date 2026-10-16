"""Unsigned recovery composition; supplied accepted state is a fixture assumption."""

from contextlib import contextmanager
from dataclasses import replace
import hashlib
import json

import pytest

from nbsr.protocol.cbor import decode_deterministic
from scripts import inclusion_persistence as store
from scripts import inclusion_recovery_harness as harness
from scripts.revocation_inclusion_v2 import FixtureState, VECTORS


class MemoryStorage:
    def __init__(self, first, second):
        self.files = {store.PRIMARY: store.encode(first), store.WATERMARK: store.encode(second)}
        self.fail = None
        self.owned = False

    @contextmanager
    def exclusive(self):
        assert not self.owned
        self.owned = True
        try:
            yield
        finally:
            self.owned = False

    def read(self, name):
        return self.files.get(name)

    def replace(self, name, data):
        if self.fail == "before":
            raise OSError("before replacement")
        self.files[name] = data
        if self.fail == "after":
            raise OSError("after replacement")


@pytest.fixture
def rig():
    # No fixture builders/signers. These are assumed accepted storage inputs,
    # not newly authenticated authority. Full record bytes remain unchanged.
    case = json.loads(VECTORS.read_text())["cases"][0]
    raw = bytes.fromhex(case["package_hex"])
    assert hashlib.sha256(raw).hexdigest() == case["sha256"]
    package = decode_deterministic(raw)
    record = package[3]
    digest = hashlib.sha256(record).digest()
    checkpoint = decode_deterministic(package[5][1:])[2]
    state = FixtureState(hashlib.sha256(checkpoint).digest(), record, frozenset({digest}), ((b"a" * 16, digest),))
    first = store.Snapshot(state, b"C" * 32, hashlib.sha256(store.AMENDMENT.read_bytes()).digest(), 1, None)
    second = replace(
        first, state=replace(state, requests=state.requests + ((b"b" * 16, digest),)), transaction=2, previous_snapshot_digest=first.digest
    )
    backend = MemoryStorage(first, second)
    owner = object()
    controller = harness.Controller(backend, context_binding=first.context_binding, expected=second.digest, owner=owner)
    return controller, backend, owner, first, second


def disposed(rig):
    controller, _, owner, _, _ = rig
    ticket = controller.begin_disposal(owner)
    assert controller.confirm_disposal(ticket, success=True)
    return controller


def test_replacement_waits_for_exact_disposal(rig):
    controller, backend, owner, _, second = rig
    before = dict(backend.files)
    with pytest.raises(harness.RecoveryBlocked):
        controller.restore()
    assert backend.files == before
    with pytest.raises(harness.RecoveryBlocked):
        controller.begin_disposal(object())
    ticket = controller.begin_disposal(owner)
    assert controller.begin_disposal(owner) is ticket
    assert not controller.confirm_disposal(object(), success=True)
    assert controller.confirm_disposal(ticket, success=True)
    worker = controller.restore()
    assert worker.snapshot == second
    assert worker.registration is None
    assert backend.files[store.PRIMARY] == backend.files[store.WATERMARK]
    with pytest.raises(harness.RecoveryBlocked):
        controller.restore()


@pytest.mark.parametrize("expected", [None, b"X" * 32])
def test_missing_or_wrong_independent_expectation_rejects(rig, expected):
    _, backend, _, first, _ = rig
    controller = harness.Controller(backend, context_binding=first.context_binding, expected=expected, owner=object())
    ticket = controller.begin_disposal(controller.owner)
    controller.confirm_disposal(ticket, success=True)
    before = dict(backend.files)
    with pytest.raises((harness.RecoveryBlocked, store.SnapshotRejected)):
        controller.restore()
    assert controller.owner is None
    assert backend.files == before


def test_joint_rollback_rejected(rig):
    controller, backend, _, first, _ = rig
    disposed(rig)
    backend.files = {name: store.encode(first) for name in backend.files}
    with pytest.raises(store.SnapshotRejected):
        controller.restore()
    assert controller.owner is None


@pytest.mark.parametrize("failure", ["before", "after"])
def test_interrupted_repair_never_publishes_worker(rig, failure):
    controller, backend, _, _, second = rig
    disposed(rig)
    backend.fail = failure
    with pytest.raises(store.StorageUnavailable):
        controller.restore()
    assert controller.owner is None
    assert not backend.owned
    backend.fail = None
    worker = controller.restore()
    assert worker.snapshot == second and worker.registration is None


def test_failed_disposal_requires_explicit_retry_and_stale_completion_is_harmless(rig):
    controller, _, owner, _, _ = rig
    old = controller.begin_disposal(owner)
    assert not controller.confirm_disposal(old, success=False)
    assert controller.owner is owner
    assert not controller.confirm_disposal(old, success=True)
    with pytest.raises(harness.RecoveryBlocked):
        controller.restore()
    current = controller.retry_disposal(old)
    assert not controller.confirm_disposal(old, success=True)
    assert controller.confirm_disposal(current, success=True)
    worker = controller.restore()
    assert not controller.confirm_disposal(current, success=True)
    assert controller.owner is worker


@pytest.mark.parametrize("success", [None, 1, "yes"])
def test_uncertain_or_nonboolean_disposal_never_releases(rig, success):
    controller, _, owner, _, _ = rig
    ticket = controller.begin_disposal(owner)
    with pytest.raises(ValueError):
        controller.confirm_disposal(ticket, success=success)
    assert controller.owner is owner


@pytest.mark.parametrize("boundary", ["before-watermark", "after-watermark", "before-primary", "after-primary"])
def test_interrupted_write_states_require_controller_selected_candidate(rig, boundary):
    _, backend, owner, first, second = rig
    # The test controller selects the permitted candidate independently. No
    # file contents are used to choose the recovery expectation.
    candidate = first if boundary == "before-watermark" else second
    primary = second if boundary == "after-primary" else first
    backend.files = {store.PRIMARY: store.encode(primary), store.WATERMARK: store.encode(candidate)}
    controller = harness.Controller(backend, context_binding=first.context_binding, expected=candidate.digest, owner=owner)
    ticket = controller.begin_disposal(owner)
    controller.confirm_disposal(ticket, success=True)
    worker = controller.restore()
    assert worker.snapshot == candidate and worker.registration is None
    assert worker.snapshot.state.record == first.state.record
    assert worker.snapshot.state.retained_revocations == first.state.retained_revocations
    assert set(first.state.requests) <= set(worker.snapshot.state.requests)


@pytest.mark.parametrize("invalid", ["context", "corrupt", "missing-watermark"])
def test_invalid_recovery_never_publishes_or_falls_back(rig, invalid):
    _, backend, owner, first, second = rig
    context = b"X" * 32 if invalid == "context" else first.context_binding
    if invalid == "corrupt":
        backend.files[store.WATERMARK] = b"broken"
    elif invalid == "missing-watermark":
        del backend.files[store.WATERMARK]
    controller = harness.Controller(backend, context_binding=context, expected=second.digest, owner=owner)
    ticket = controller.begin_disposal(owner)
    controller.confirm_disposal(ticket, success=True)
    before = dict(backend.files)
    with pytest.raises(store.SnapshotRejected):
        controller.restore()
    assert controller.owner is None and backend.files == before


def test_retry_requires_exact_failed_attempt(rig):
    controller, _, owner, _, _ = rig
    ticket = controller.begin_disposal(owner)
    with pytest.raises(harness.RecoveryBlocked):
        controller.retry_disposal(ticket)
    controller.confirm_disposal(ticket, success=False)
    with pytest.raises(harness.RecoveryBlocked):
        controller.retry_disposal(object())
    current = controller.retry_disposal(ticket)
    with pytest.raises(harness.RecoveryBlocked):
        controller.retry_disposal(ticket)
    assert not controller.confirm_disposal(ticket, success=True)
    assert controller.confirm_disposal(current, success=True)


def test_reentrant_restore_cannot_publish_an_undisposed_worker(rig):
    controller, backend, _, _, second = rig
    disposed(rig)
    original = backend.exclusive

    @contextmanager
    def reentrant_exclusive():
        backend.exclusive = original
        with pytest.raises(harness.RecoveryBlocked):
            controller.restore()
        with original():
            yield

    backend.exclusive = reentrant_exclusive
    worker = controller.restore()
    assert controller.owner is worker and worker.snapshot == second
