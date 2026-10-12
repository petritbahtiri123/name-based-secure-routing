"""Deterministic test events only: no signed receipt producer or real clocks."""

from dataclasses import replace
import importlib
import importlib.util
import inspect

import pytest

from nbsr.connector_control_model import Binding, CompletionGrace, Model, Permission
from nbsr.federation.registry import EnforcementMode as Mode


class Clock:
    now = 10
    failure = False
    samples = None
    calls = 0

    def __call__(self):
        self.calls += 1
        if self.failure:
            raise RuntimeError("fixture clock unavailable")
        if self.samples:
            return self.samples.pop(0)
        return self.now


class Transport:
    closed = False
    session = None

    def __init__(self):
        self.session = object()

    def close(self):
        self.closed = True


def setup_model(*, lease=100, active=200):
    clock = Clock()
    binding = Binding("connector", "service", "gateway", "operator", "issuer", 1, "register")
    permission = Permission(binding, 200, active, CompletionGrace("timer-test-only", 20))
    model = Model(binding, lambda *_: permission, clock, lease=lease, attempts=2, retry_delay=0)
    owner = model.begin(Transport(), binding)
    assert model.authenticate(owner)
    ticket = model.register(owner)
    assert model.confirm(owner, ticket)
    work = model.admit_work(owner, deadline=180)
    return clock, model, owner, work


def test_delayed_enforcement_anchors_grace_at_effective_time():
    clock, model, owner, work = setup_model()
    clock.now = 35
    assert "effective_at" in inspect.signature(model.enforce).parameters
    model.enforce(owner, Mode.DENY_NEW_USE, effective_at=20)
    assert work.drain_started == 20 and work.deadline == 40
    assert not work.cancelled and model.select() is None
    clock.now = 40
    model.poll()
    assert work.cancelled and owner.transport.closed


@pytest.fixture
def api():
    assert importlib.util.find_spec("nbsr.connector_authority_timer_offline") is not None, "offline timer adapter missing"
    return importlib.import_module("nbsr.connector_authority_timer_offline")


def rig(api, **limits):
    clock, model, owner, work = setup_model(**limits)
    timer = api.OfflineAuthorityTimer(model, owner, context_digest=b"C" * 32, dependencies=frozenset({b"D" * 32}), revision=1, max_events=8)
    event = api.SimulatedAuthorityEvent(b"E" * 32, b"C" * 32, frozenset({b"D" * 32}), 1, 20, Mode.DENY_NEW_USE)
    return clock, model, owner, work, timer, event


def test_future_dispatch_exact_boundary_and_duplicate_do_not_restart(api):
    clock, model, owner, work, timer, event = rig(api)
    assert timer.schedule(event)
    assert not timer.schedule(event)
    clock.now = 19
    assert timer.poll() == 0 and model.select() is owner
    clock.now = 20
    assert timer.poll() == 1 and model.select() is None
    assert work.deadline == 40 and not work.cancelled
    clock.now = 30
    assert timer.schedule(replace(event, event_id=b"F" * 32, effective_at=30))
    assert timer.poll() == 1 and work.deadline == 40
    assert not timer.schedule(event)
    clock.now = 40
    timer.poll()
    assert work.cancelled and owner.transport.closed


def test_late_poll_does_not_grant_fresh_grace(api):
    clock, _, owner, work, timer, event = rig(api)
    timer.schedule(event)
    clock.now = 45
    assert timer.poll() == 1
    assert work.cancelled and work.drain_started == 20 and owner.transport.closed


def test_registration_expiry_preserves_work_until_independent_bound(api):
    clock, model, owner, work, timer, _ = rig(api, lease=5)
    clock.now = 15
    timer.poll()
    assert model.select() is None and not work.cancelled
    assert work.drain_started == 15 and work.deadline == 35
    clock.now = 34
    timer.poll()
    assert not work.cancelled
    clock.now = 35
    timer.poll()
    assert work.cancelled and owner.transport.closed


def test_active_authority_expiry_precedes_grace(api):
    clock, _, _, work, timer, event = rig(api, active=25)
    timer.schedule(event)
    clock.now = 20
    timer.poll()
    assert work.deadline == 25
    clock.now = 25
    timer.poll()
    assert work.cancelled


def test_terminate_overrides_drain_and_leaves_unrelated_owner_intact(api):
    clock, _, owner, work, timer, event = rig(api)
    other_clock, other_model, other_owner, other_work, other, _ = rig(api)
    unrelated = replace(event, dependencies=frozenset({b"X" * 32}), mode=Mode.TERMINATE_ACTIVE_USE)
    assert not other.schedule(unrelated)
    timer.schedule(event)
    timer.schedule(replace(event, event_id=b"T" * 32, effective_at=25, mode=Mode.TERMINATE_ACTIVE_USE))
    clock.now = other_clock.now = 25
    assert timer.poll() == 2 and other.poll() == 0
    assert work.cancelled and owner.transport.closed
    assert not other_work.cancelled and other_model.select() is other_owner


def test_revision_is_rechecked_at_dispatch_and_never_resurrects(api):
    clock, model, owner, work, timer, event = rig(api)
    timer.schedule(event)
    timer.advance_revision(2)
    clock.now = 20
    assert timer.poll() == 0 and model.select() is owner
    assert not timer.schedule(event)
    assert timer.schedule(replace(event, event_id=b"F" * 32, revision=2))
    assert timer.poll() == 1
    timer.advance_revision(3)
    assert model.select() is None and work.deadline == 40


@pytest.mark.parametrize("bad", [9, True, None])
def test_clock_rollback_or_invalid_time_latches_closed(api, bad):
    clock, model, owner, work, timer, event = rig(api)
    timer.schedule(event)
    timer.poll()
    clock.now = bad
    with pytest.raises(ValueError, match="clock"):
        timer.poll()
    assert work.cancelled and owner.transport.closed
    clock.now = 30
    with pytest.raises(ValueError, match="clock"):
        timer.poll()
    assert model.select() is None


def test_stale_owner_and_changed_session_cannot_receive_events(api):
    clock, model, owner, _, timer, event = rig(api)
    timer.schedule(event)
    model.stop(owner)
    replacement = model.begin(Transport(), model.binding)
    clock.now = 20
    assert timer.poll() == 0 and not replacement.transport.closed
    _, _, owner, _, timer, event = rig(api)
    owner.transport.session = object()
    assert not timer.schedule(event)


def test_event_inventory_is_bounded_no_eviction_or_equivocation(api):
    _, _, _, _, timer, event = rig(api)
    assert timer.schedule(event)
    with pytest.raises(ValueError, match="conflict"):
        timer.schedule(replace(event, effective_at=21))
    for number in range(7):
        assert timer.schedule(replace(event, event_id=bytes([number]) * 32))
    with pytest.raises(ValueError, match="bound"):
        timer.schedule(replace(event, event_id=b"Z" * 32))


@pytest.mark.parametrize(
    "changes", [{"revision": True}, {"effective_at": True}, {"mode": 1}, {"dependencies": frozenset()}, {"event_id": b"x"}]
)
def test_untyped_or_malformed_events_reject(api, changes):
    _, _, _, _, timer, event = rig(api)
    with pytest.raises(ValueError):
        timer.schedule(replace(event, **changes))


@pytest.mark.parametrize("effective", [True, -1, 11])
def test_invalid_or_future_direct_enforcement_does_not_latch(effective):
    _, model, owner, work = setup_model()
    with pytest.raises(ValueError):
        model.enforce(owner, Mode.DENY_NEW_USE, effective_at=effective)
    assert model.select() is owner and not work.cancelled


def test_wrong_context_revision_and_bare_inputs_are_not_events(api):
    clock, model, owner, _, timer, event = rig(api)
    assert not timer.schedule(replace(event, context_digest=b"X" * 32))
    assert not timer.schedule(replace(event, revision=2))
    with pytest.raises(ValueError):
        timer.schedule(object())
    with pytest.raises(ValueError):
        timer.advance_revision(True)
    with pytest.raises(ValueError):
        timer.advance_revision(1)
    clock.now = 20
    assert timer.poll() == 0 and model.select() is owner


def test_failed_close_keeps_owner_until_explicit_retry(api):
    clock, model, owner, work, timer, event = rig(api)
    real_close = owner.transport.close
    owner.transport.close = lambda: None
    timer.schedule(replace(event, mode=Mode.TERMINATE_ACTIVE_USE))
    clock.now = 20
    assert timer.poll() == 1 and work.cancelled
    assert model.health() == {"ready": False, "owned": 1}
    assert timer.poll() == 0 and model._current is owner
    replacement = Transport()
    assert model.begin(replacement, model.binding) is None and replacement.closed
    owner.transport.close = real_close
    model.stop(owner)
    assert model.health() == {"ready": False, "owned": 0}


@pytest.mark.parametrize(
    "changes", [{"max_events": True}, {"max_events": 65}, {"revision": 0}, {"dependencies": frozenset()}, {"context_digest": b"x"}]
)
def test_timer_requires_bounded_explicit_fixture_configuration(api, changes):
    _, model, owner, _ = setup_model()
    config = dict(context_digest=b"C" * 32, dependencies=frozenset({b"D" * 32}), revision=1, max_events=8)
    with pytest.raises(ValueError):
        api.OfflineAuthorityTimer(model, owner, **(config | changes))


def test_clock_exception_is_latched_and_does_not_create_authority(api):
    clock, _, owner, work, timer, _ = rig(api)
    clock.failure = True
    with pytest.raises(ValueError, match="clock"):
        timer.poll()
    assert work.cancelled and owner.transport.closed


def test_one_clock_sample_per_poll_prevents_crossing_due_boundary(api):
    clock, model, owner, work, timer, event = rig(api)
    timer.schedule(event)
    clock.samples = [19, 20]
    before = clock.calls
    assert timer.poll() == 0
    assert clock.calls == before + 1
    assert model.select() is owner  # Still the explicit poll's time 19.
    assert timer.poll() == 1
    assert work.drain_started == 20 and model.select() is None


def test_clock_rollback_cannot_discard_pending_event_and_restore_admission(api):
    clock, model, owner, work, timer, event = rig(api)
    timer.schedule(replace(event, effective_at=30))
    clock.samples = [30, 29, 30]
    assert timer.poll() == 1
    assert work.drain_started == 30 and model.select() is None
    with pytest.raises(ValueError, match="clock"):
        timer.poll()
    assert work.cancelled and owner.transport.closed
    with pytest.raises(ValueError, match="clock"):
        timer.poll()


def test_same_model_cannot_acquire_two_clock_schedulers(api):
    _, model, owner, _, _, _ = rig(api)
    with pytest.raises(ValueError, match="fixture"):
        api.OfflineAuthorityTimer(model, owner, context_digest=b"C" * 32, dependencies=frozenset({b"D" * 32}), revision=1, max_events=8)
