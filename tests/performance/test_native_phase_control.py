import socket

import pytest

from scripts.analyze_b1_v2_capture import PHASE_NAMES
from scripts.performance.native_phase_control import PhaseControl


def send(control, message):
    with socket.create_connection(control.endpoint, timeout=2) as stream:
        stream.sendall(message)
        stream.shutdown(socket.SHUT_WR)
        return stream.recv(512)


def test_ordered_transitions_and_owned_cleanup():
    observed = []
    with PhaseControl(observed.append) as control:
        for name in PHASE_NAMES:
            assert send(control, (name + '\n').encode()).startswith(b'{"status":"ok"')
    assert observed == list(PHASE_NAMES)
    assert not control.thread.is_alive()
    assert control.completed


@pytest.mark.parametrize('message', [b'measurement-start\n', b'unknown\n', b'x' * 129, b'setup-complete'])
def test_invalid_transition_fails_closed(message):
    observed = []
    with pytest.raises(ValueError):
        with PhaseControl(observed.append) as control:
            assert not send(control, message).startswith(b'{"status":"ok"')
    assert observed == []
    assert not control.thread.is_alive()


def test_marker_failure_is_not_acknowledged():
    def broken(_):
        raise OSError('fixture marker failed')
    with pytest.raises(ValueError, match='fixture marker failed'):
        with PhaseControl(broken) as control:
            assert not send(control, b'setup-complete\n').startswith(b'{"status":"ok"')
    assert not control.completed


def test_missing_transitions_reject_without_hanging():
    with pytest.raises(ValueError, match='incomplete'):
        with PhaseControl(lambda _: None) as control:
            pass
    assert not control.thread.is_alive()


def test_duplicate_is_rejected():
    with pytest.raises(ValueError):
        with PhaseControl(lambda _: None) as control:
            assert send(control, b'setup-complete\n').startswith(b'{"status":"ok"')
            assert not send(control, b'setup-complete\n').startswith(b'{"status":"ok"')
