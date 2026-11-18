"""Source-only control-plane model, not native owner authentication."""
import threading

import pytest

from scripts.performance.viewer_owner_observation import ObservationSlot


def slot():
    return ObservationSlot(('run', 'request-pin', 'ready-pin'), anchor=10., deadline=125.)


def test_fresh_sequence_and_revalidation():
    view = slot()
    sequence = view.request(now=11.)
    assert view.pending(now=11.) == sequence
    view.answer(sequence, owned=True, now=12.)
    proof = view.take(sequence, now=13.)
    assert proof.identity == ('run', 'request-pin', 'ready-pin')
    assert proof.observed_at == 12.
    view.revalidate(proof, now=14.)
    assert view.request(now=15.) > sequence


def test_cancel_after_observation_permanently_revokes():
    view = slot()
    sequence = view.request(now=11.)
    view.answer(sequence, owned=True, now=12.)
    proof = view.take(sequence, now=13.)
    view.revoke()
    with pytest.raises(ValueError):
        view.revalidate(proof, now=14.)
    with pytest.raises(ValueError):
        view.request(now=14.)


@pytest.mark.parametrize('now', [9., 125., float('nan'), True])
def test_invalid_clock_latches(now):
    view = slot()
    with pytest.raises(ValueError):
        view.request(now=now)
    with pytest.raises(ValueError):
        view.request(now=11.)


def test_stale_reply_and_overflow_fail_closed():
    view = slot()
    sequence = view.request(now=11.)
    with pytest.raises(ValueError):
        view.answer(sequence + 1, owned=True, now=12.)
    with pytest.raises(ValueError):
        view.answer(sequence, owned=True, now=12.)
    other = slot()
    other.request(now=11.)
    with pytest.raises(ValueError):
        other.request(now=12.)


def test_exit_answer_is_not_ownership():
    view = slot()
    sequence = view.request(now=11.)
    with pytest.raises(ValueError):
        view.answer(sequence, owned=False, now=12.)
    with pytest.raises(ValueError):
        view.take(sequence, now=13.)


def test_consumed_reply_cannot_be_taken_again():
    view = slot()
    sequence = view.request(now=11.)
    view.answer(sequence, owned=True, now=12.)
    view.take(sequence, now=13.)
    with pytest.raises(ValueError):
        view.take(sequence, now=14.)


def test_blocked_publisher_does_not_hold_monitor_lock():
    view = slot()
    sequence = view.request(now=11.)
    view.answer(sequence, owned=True, now=12.)
    proof = view.take(sequence, now=13.)
    entered = threading.Event()
    release = threading.Event()

    def publisher():
        view.revalidate(proof, now=14.)
        entered.set()
        release.wait(1.)  # Publication is deliberately outside the slot.

    worker = threading.Thread(target=publisher)
    worker.start()
    try:
        assert entered.wait(1.)
        view.revoke()  # Native monitor can revoke without waiting for publication.
        with pytest.raises(ValueError):
            view.revalidate(proof, now=15.)
    finally:
        release.set()
        worker.join(1.)
    assert not worker.is_alive()


def test_prior_reply_cannot_authorize_new_sequence():
    view = slot()
    sequence = view.request(now=11.)
    view.answer(sequence, owned=True, now=12.)
    proof = view.take(sequence, now=13.)
    view.request(now=14.)
    with pytest.raises(ValueError):
        view.revalidate(proof, now=15.)


def test_equal_forged_reply_is_not_the_monitor_reply():
    from dataclasses import replace
    view = slot()
    sequence = view.request(now=11.)
    view.answer(sequence, owned=True, now=12.)
    proof = view.take(sequence, now=13.)
    with pytest.raises(ValueError):
        view.revalidate(replace(proof), now=14.)


def test_ci_selects_source_only_observation_model():
    from scripts.ci.check import command_groups
    assert any('tests/performance/test_viewer_owner_observation.py' in c.argv
               for c in command_groups('python-core'))
