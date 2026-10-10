"""Mock-only contract model tests; numbers are fixture inputs, not protocol limits."""

from dataclasses import replace
import importlib
import importlib.util

import pytest

from nbsr.federation.registry import EnforcementMode
from nbsr.protocol.models import RevocationMode


def test_model_is_available():
    assert importlib.util.find_spec("nbsr.connector_control_model") is not None, "mock control model is missing"


@pytest.fixture
def api():
    return importlib.import_module("nbsr.connector_control_model")


class Clock:
    now = 10

    def __call__(self):
        return self.now


class Transport:
    def __init__(self):
        self.session = object()
        self.closed = False
        self.controls = 0

    def close(self):
        self.closed = True


class Verifier:
    def __init__(self, permission):
        self.permission = permission
        self.fresh = True
        self.revoked = False
        self.calls = 0

    def __call__(self, binding, session, now):
        self.calls += 1
        if not self.fresh or self.revoked or binding != self.permission.binding:
            return None
        return self.permission if now < self.permission.expires else None


@pytest.fixture
def rig(api):
    binding = api.Binding("connector", "service", "gateway", "operator", "issuer", 3, "register")
    clock = Clock()
    verifier = Verifier(api.Permission(binding, 30))
    model = api.Model(binding, verifier, clock, lease=8, attempts=3, retry_delay=2)
    return api, model, clock, verifier, binding


def ready(rig):
    _, model, _, _, binding = rig
    attempt = model.begin(Transport(), binding)
    assert model.authenticate(attempt)
    ticket = model.register(attempt)
    assert ticket is not None
    assert model.confirm(attempt, ticket)
    return attempt, ticket


def test_c01_two_exchanges_same_session(rig):
    _, model, _, _, _ = rig
    attempt, ticket = ready(rig)
    assert model.renew(attempt, ticket)
    assert model.select() is attempt
    assert model.health() == {"ready": True, "owned": 1}
    model.stop(attempt)
    assert model.health() == {"ready": False, "owned": 0}
    assert attempt.transport.closed


@pytest.mark.parametrize(
    "field,value",
    [
        ("connector", "other"),
        ("gateway", "other"),
        ("operator", "other"),
        ("issuer", "other"),
        ("service", "other"),
        ("generation", 2),
        ("role", "publish"),
    ],
)
def test_c02_c03_wrong_binding_never_registers(rig, field, value):
    _, model, _, _, binding = rig
    attempt = model.begin(Transport(), replace(binding, **{field: value}))
    assert not model.authenticate(attempt)
    assert model.register(attempt) is None
    assert model.select() is None
    assert attempt.transport.closed
    assert model.health()["owned"] == 0


@pytest.mark.parametrize("now,allowed", [(29, True), (30, False), (31, False)])
def test_c04_permission_boundary_and_lease_cap(rig, now, allowed):
    _, model, clock, _, binding = rig
    clock.now = now
    attempt = model.begin(Transport(), binding)
    assert model.authenticate(attempt) is allowed
    ticket = model.register(attempt)
    assert (ticket is not None) is allowed
    if allowed:
        assert ticket.expires == 30
        clock.now = 30
        assert model.select() is None
        assert attempt.transport.closed


def test_c05_old_ticket_cannot_confirm_or_renew_new_attempt(rig):
    _, model, clock, _, binding = rig
    old, ticket = ready(rig)
    model.stop(old)
    clock.now += 2
    new = model.begin(Transport(), binding)
    assert model.authenticate(new)
    new_ticket = model.register(new)
    assert not model.confirm(new, ticket)
    assert not model.renew(new, ticket)
    assert model.confirm(new, new_ticket)


def test_c06_duplicate_rejected_and_stale_cleanup_safe(rig):
    _, model, clock, _, binding = rig
    old, _ = ready(rig)
    duplicate = Transport()
    assert model.begin(duplicate, binding) is None
    assert duplicate.closed
    assert model.select() is old
    model.stop(old)
    clock.now += 2
    new, _ = ready(rig)
    model.stop(old)
    assert model.select() is new
    assert not new.transport.closed


def test_c07_unconfirmed_acceptance_expires(rig):
    _, model, clock, _, binding = rig
    attempt = model.begin(Transport(), binding)
    assert model.authenticate(attempt)
    assert model.register(attempt)
    assert not model.health()["ready"]
    clock.now += 8
    model.poll()
    assert model.select() is None
    assert attempt.transport.closed


def test_c08_disconnect_fresh_reconnect_revalidates(rig):
    _, model, clock, verifier, binding = rig
    old, _ = ready(rig)
    old.transport.closed = True
    assert model.select() is None
    clock.now += 2
    verifier.revoked = True
    new = model.begin(Transport(), binding)
    assert new.transport.session is not old.transport.session
    assert not model.authenticate(new)
    assert model.select() is None


@pytest.mark.parametrize("phase", ["connecting", "authenticated", "registered", "ready"])
@pytest.mark.parametrize("event", ["cancel", "revoke", "unfresh"])
def test_c09_c10_cleanup_at_every_model_phase(rig, phase, event):
    _, model, _, verifier, binding = rig
    attempt = model.begin(Transport(), binding)
    if phase != "connecting":
        assert model.authenticate(attempt)
    if phase in ("registered", "ready"):
        ticket = model.register(attempt)
        if phase == "ready":
            assert model.confirm(attempt, ticket)
    if event == "cancel":
        model.stop(attempt)
    else:
        if event == "revoke":
            verifier.revoked = True
        else:
            verifier.fresh = False
        model.poll()
    assert model.select() is None
    assert attempt.transport.closed
    assert model.health()["owned"] == 0
    assert attempt.phase == "terminal"


def test_c11_no_pending_queue_when_slot_occupied(rig):
    _, model, _, _, binding = rig
    current, _ = ready(rig)
    for _ in range(20):
        transport = Transport()
        assert model.begin(transport, binding) is None
        assert transport.closed
    assert model.health()["owned"] == 1
    assert model.select() is current


def test_c12_retry_delay_budget_and_permanent_rejection(rig):
    _, model, clock, _, binding = rig
    for _ in range(3):
        attempt = model.begin(Transport(), binding)
        assert attempt is not None
        model.stop(attempt)
        rejected = Transport()
        assert model.begin(rejected, binding) is None
        assert rejected.closed
        clock.now += 2
    assert model.begin(Transport(), binding) is None


def test_c12_authorization_rejection_halts_retry(rig):
    _, model, clock, verifier, binding = rig
    verifier.revoked = True
    attempt = model.begin(Transport(), binding)
    assert not model.authenticate(attempt)
    clock.now += 2
    verifier.revoked = False
    assert model.begin(Transport(), binding) is None


def test_c13_new_model_does_not_restore_registration(rig):
    api, old_model, clock, verifier, binding = rig
    _, ticket = ready(rig)
    fresh = api.Model(binding, verifier, clock, lease=8, attempts=3, retry_delay=2)
    assert fresh.select() is None
    new = fresh.begin(Transport(), binding)
    assert fresh.authenticate(new)
    assert fresh.register(new)
    assert not fresh.confirm(new, ticket)
    old_model.stop(old_model.select())


@pytest.mark.parametrize("event", ["expiry", "revoke", "unfresh"])
def test_c14_invalidation_before_renewal_or_selection(rig, event):
    _, model, clock, verifier, _ = rig
    attempt, ticket = ready(rig)
    if event == "expiry":
        clock.now = ticket.expires
    elif event == "revoke":
        verifier.revoked = True
    else:
        verifier.fresh = False
    assert not model.renew(attempt, ticket)
    assert model.select() is None
    assert attempt.transport.closed


def test_c15_backward_clock_latches_closed(rig):
    _, model, clock, _, binding = rig
    attempt, _ = ready(rig)
    clock.now -= 1
    assert model.select() is None
    assert attempt.transport.closed
    clock.now = 20
    assert model.begin(Transport(), binding) is None


@pytest.mark.parametrize("field,value", [("lease", 0), ("attempts", 0), ("retry_delay", -1), ("lease", True)])
def test_c16_invalid_limits_have_no_verification_effects(rig, field, value):
    api, _, clock, verifier, binding = rig
    limits = dict(lease=8, attempts=3, retry_delay=2)
    limits[field] = value
    with pytest.raises(ValueError):
        api.Model(binding, verifier, clock, **limits)
    assert verifier.calls == 0


def test_session_changes_cannot_keep_acceptance(rig):
    _, model, _, _, _ = rig
    attempt, ticket = ready(rig)
    attempt.transport.session = object()
    assert not model.renew(attempt, ticket)
    assert attempt.transport.closed
    assert model.select() is None


def test_verifier_exception_releases_attempt(rig):
    _, model, _, _, binding = rig

    def broken(*args):
        raise RuntimeError("unavailable")

    model.verifier = broken
    attempt = model.begin(Transport(), binding)
    assert not model.authenticate(attempt)
    assert attempt.transport.closed
    assert model.select() is None


def test_renewal_returns_fresh_ticket_capped_by_permission(rig):
    _, model, clock, _, _ = rig
    attempt, ticket = ready(rig)
    clock.now = 15
    renewed = model.renew(attempt, ticket)
    assert renewed.expires == 23
    assert not model.renew(attempt, ticket)
    clock.now = 22
    capped = model.renew(attempt, renewed)
    assert capped.expires == 30
    clock.now = 30
    assert model.select() is None


def test_duplicate_same_transport_does_not_close_current_owner(rig):
    _, model, _, _, binding = rig
    attempt, _ = ready(rig)
    assert model.begin(attempt.transport, binding) is None
    assert model.select() is attempt
    assert not attempt.transport.closed


def test_stop_backoff_begins_at_stop_time(rig):
    _, model, clock, _, binding = rig
    attempt, _ = ready(rig)
    clock.now = 14
    model.stop(attempt)
    assert model.begin(Transport(), binding) is None
    clock.now = 16
    assert model.begin(Transport(), binding) is not None


def test_successful_reconnect_uses_new_owner_and_session(rig):
    _, model, clock, verifier, _ = rig
    old, ticket = ready(rig)
    old.transport.closed = True
    model.poll()
    clock.now += 2
    calls = verifier.calls
    new, new_ticket = ready(rig)
    assert new is not old
    assert new.session is not old.session
    assert new_ticket is not ticket
    assert verifier.calls > calls
    assert model.select() is new


@pytest.mark.parametrize("failure", ["raise", "stay_open"])
def test_close_failure_retains_visible_owner_and_blocks_retry(rig, failure):
    _, model, clock, _, binding = rig
    attempt, _ = ready(rig)

    def failed_close():
        if failure == "raise":
            raise RuntimeError("fake close failed")

    attempt.transport.close = failed_close
    model.stop(attempt)
    assert model.health() == {"ready": False, "owned": 1}
    clock.now += 2
    assert model.begin(Transport(), binding) is None
    attempt.transport.close = lambda: setattr(attempt.transport, "closed", True)
    model.stop(attempt)
    assert model.health() == {"ready": False, "owned": 0}


def test_renewal_cannot_cross_expiry_between_clock_samples(rig):
    _, model, _, _, _ = rig
    attempt, ticket = ready(rig)
    samples = iter((17, 18))
    model.clock = lambda: next(samples, 18)
    assert model.renew(attempt, ticket) is None
    assert model.select() is None
    assert attempt.transport.closed


def active(rig, *, deadline=25, lease_bounds_active=False):
    _, model, _, _, _ = rig
    attempt, ticket = ready(rig)
    assert hasattr(model, "admit_work"), "active-work model is missing"
    work = model.admit_work(attempt, deadline=deadline, lease_bounds_active=lease_bounds_active)
    assert work is not None
    return attempt, ticket, work


def test_deny_blocks_new_use_but_keeps_authorized_active_work(rig):
    _, model, clock, _, binding = rig
    attempt, ticket, work = active(rig)
    model.enforce(attempt, EnforcementMode.DENY_NEW_USE)
    assert model.select() is None
    assert not model.renew(attempt, ticket)
    assert model.register(attempt) is None
    assert not model.confirm(attempt, ticket)
    assert model.admit_work(attempt, deadline=26, lease_bounds_active=False) is None
    assert model.begin(Transport(), binding) is None
    clock.now = 24
    model.poll()
    assert not work.cancelled and not attempt.transport.closed
    assert model.health() == {"ready": False, "owned": 1}
    clock.now = 25
    model.poll()
    assert work.cancelled and attempt.transport.closed
    assert model.health()["owned"] == 0
    clock.now = 27
    assert model.begin(Transport(), binding) is None


@pytest.mark.parametrize("lease_bounds_active,expected", [(False, 25), (True, 18)])
def test_active_deadline_policy_is_explicit_and_never_extended(rig, lease_bounds_active, expected):
    _, model, clock, _, _ = rig
    attempt, ticket, work = active(rig, lease_bounds_active=lease_bounds_active)
    assert work.deadline == expected
    clock.now = 15
    assert model.renew(attempt, ticket)
    assert work.deadline == expected
    model.enforce(attempt, EnforcementMode.DENY_NEW_USE)
    clock.now = expected - 1
    model.poll()
    assert not work.cancelled
    clock.now = expected
    model.poll()
    assert work.cancelled


def test_active_deadline_is_capped_by_existing_permission(rig):
    _, model, clock, _, _ = rig
    attempt, _, work = active(rig, deadline=50)
    assert work.deadline == 30
    model.enforce(attempt, EnforcementMode.DENY_NEW_USE)
    clock.now = 30
    model.poll()
    assert work.cancelled and attempt.transport.closed


@pytest.mark.parametrize("failure", ["none", "raise", "stay_open"])
def test_terminate_cancels_work_but_releases_only_confirmed_cleanup(rig, failure):
    _, model, clock, _, binding = rig
    attempt, ticket, work = active(rig)

    def close():
        if failure == "raise":
            raise RuntimeError("fake close failure")
        if failure == "none":
            attempt.transport.closed = True

    attempt.transport.close = close
    model.enforce(attempt, EnforcementMode.TERMINATE_ACTIVE_USE)
    assert work.cancelled
    assert model.select() is None
    assert model.renew(attempt, ticket) is None
    assert model.health()["owned"] == (0 if failure == "none" else 1)
    model.enforce(attempt, EnforcementMode.DENY_NEW_USE)
    assert work.cancelled and model.select() is None
    clock.now += 2
    assert model.begin(Transport(), binding) is None
    attempt.transport.close = lambda: setattr(attempt.transport, "closed", True)
    model.stop(attempt)
    assert model.health()["owned"] == 0
    assert model.begin(Transport(), binding) is None


def test_repeat_deny_then_terminate_never_downgrades(rig):
    _, model, _, _, _ = rig
    attempt, _, work = active(rig)
    for _ in range(2):
        model.enforce(attempt, EnforcementMode.DENY_NEW_USE)
        assert not work.cancelled
    model.enforce(attempt, EnforcementMode.TERMINATE_ACTIVE_USE)
    model.enforce(attempt, EnforcementMode.TERMINATE_ACTIVE_USE)
    assert work.cancelled and model.health()["owned"] == 0


def test_stale_work_and_revoke_cannot_touch_successor(rig):
    _, model, clock, _, _ = rig
    old, _, old_work = active(rig)
    model.stop(old)
    clock.now += 2
    new, _, new_work = active(rig)
    model.enforce(old, EnforcementMode.TERMINATE_ACTIVE_USE)
    model.finish_work(old_work)
    model.stop(old)
    assert model.select() is new
    assert not new_work.cancelled and not new.transport.closed


def test_finish_denied_work_releases_owner_without_reconnect(rig):
    _, model, clock, _, binding = rig
    attempt, _, work = active(rig)
    model.enforce(attempt, EnforcementMode.DENY_NEW_USE)
    model.finish_work(work)
    assert work.completed and not work.cancelled
    assert attempt.transport.closed and model.health()["owned"] == 0
    clock.now += 2
    assert model.begin(Transport(), binding) is None


@pytest.mark.parametrize("mode", [1, 2, RevocationMode.TERMINATE_ACTIVE_USE, EnforcementMode.REAUTHENTICATE])
def test_enforcement_rejects_ambiguous_numeric_or_unsupported_modes(rig, mode):
    _, model, _, _, _ = rig
    attempt, _, work = active(rig)
    with pytest.raises(ValueError):
        model.enforce(attempt, mode)
    assert model.select() is attempt and not work.cancelled


def test_one_active_slot_and_early_completion(rig):
    _, model, _, _, _ = rig
    attempt, _, work = active(rig)
    assert model.admit_work(attempt, deadline=22, lease_bounds_active=False) is None
    model.finish_work(work)
    assert work.completed and not work.cancelled
    assert model.select() is attempt


def test_deny_without_active_work_closes_and_halts(rig):
    _, model, clock, _, binding = rig
    attempt, _ = ready(rig)
    assert hasattr(model, "enforce"), "typed enforcement is missing"
    model.enforce(attempt, EnforcementMode.DENY_NEW_USE)
    assert attempt.transport.closed and model.select() is None
    clock.now += 2
    assert model.begin(Transport(), binding) is None


@pytest.mark.parametrize("mode", [EnforcementMode.DENY_NEW_USE, EnforcementMode.TERMINATE_ACTIVE_USE])
@pytest.mark.parametrize("event", ["lease_expiry", "work_expiry", "disconnect"])
def test_revoke_current_owner_at_cleanup_boundary_still_blocks_reconnect(rig, mode, event):
    _, model, clock, _, binding = rig
    if event == "work_expiry":
        attempt, _, _ = active(rig, deadline=18)
    else:
        attempt, _ = ready(rig)
    clock.now = 18
    if event == "disconnect":
        attempt.transport.closed = True
    model.enforce(attempt, mode)
    clock.now = 20
    assert model.begin(Transport(), binding) is None


def test_renewal_at_lease_boundary_preserves_independently_bounded_work(rig):
    _, model, clock, _, _ = rig
    attempt, ticket, work = active(rig)
    samples = iter((17, 18))
    model.clock = lambda: next(samples, 18)
    assert model.renew(attempt, ticket) is None
    assert not work.cancelled and not attempt.transport.closed
    assert model.select() is None
    model.clock = clock
    clock.now = 25
    model.poll()
    assert work.cancelled and attempt.transport.closed
