import json

import pytest

from tests.performance.test_linux_native_finite_control import wire
from tests.performance.test_linux_native_paced import transcript


def ledger():
    from scripts.performance.linux_native_live_relay import LiveLedger
    result = LiveLedger(payload_bytes=1024)
    result.accept('source', wire('source', 'owned'))
    result.accept('source', wire('source', 'readiness_transferred'))
    return result


def telemetry(row):
    event = 'paced_final' if row['schema'].endswith('final-v1') else 'paced_progress'
    return wire('source', event, value=row)


def test_live_ledger_requires_all_telemetry_before_completion():
    value = ledger()
    with pytest.raises(ValueError):
        value.accept('source', wire('source', 'complete'))
    for row in transcript():
        value.accept('source', telemetry(row))
    value.accept('source', wire('source', 'complete'))
    value.eof('source')
    assert len(value.telemetry) == 5


@pytest.mark.parametrize('fault', ['early', 'wrong-role', 'duplicate', 'after-final', 'bad-count', 'clock', 'extra'])
def test_malformed_or_misordered_telemetry_rejected(fault):
    from scripts.performance.linux_native_live_relay import LiveLedger
    value = ledger() if fault != 'early' else LiveLedger(payload_bytes=1024)
    row = transcript()[0]
    role = 'source'
    frame = json.loads(telemetry(row))
    if fault == 'wrong-role':
        role = frame['role'] = 'destination'
    elif fault == 'duplicate':
        value.accept('source', telemetry(row))
    elif fault == 'after-final':
        for entry in transcript():
            value.accept('source', telemetry(entry))
    elif fault == 'bad-count':
        frame['value']['completed'] += 1
    elif fault == 'clock':
        frame['timestamp_ns'] = 0
    elif fault == 'extra':
        frame['extra'] = 1
    with pytest.raises(ValueError):
        value.accept(role, json.dumps(frame).encode())


def test_early_eof_still_fails_after_telemetry_final():
    value = ledger()
    for row in transcript():
        value.accept('source', telemetry(row))
    with pytest.raises(InterruptedError):
        value.eof('source')


def test_manager_forwards_only_after_ledger_acceptance(tmp_path):
    from scripts.performance.linux_native_lifecycle_coordinator import Manager
    from scripts.performance.linux_native_finite_control import FiniteLedger
    received = []
    manager = Manager(None, tmp_path, ledger=FiniteLedger(), on_receive=lambda role, value: received.append((role, value)))
    try:
        manager.messages.put(('source', wire('source', 'owned')))
        manager.pump()
        assert received[0][1]['event'] == 'owned'
        manager.messages.put(('source', wire('source', 'complete')))
        with pytest.raises(ValueError):
            manager.pump()
        assert len(received) == 1
    finally:
        manager.close()


def test_callback_failure_propagates_for_owned_cleanup(tmp_path):
    from scripts.performance.linux_native_lifecycle_coordinator import Manager
    from scripts.performance.linux_native_finite_control import FiniteLedger
    def broken(role, value):
        raise InterruptedError('destination relay failed')
    manager = Manager(None, tmp_path, ledger=FiniteLedger(), on_receive=broken)
    try:
        manager.messages.put(('source', wire('source', 'owned')))
        with pytest.raises(InterruptedError, match='relay failed'):
            manager.pump()
    finally:
        manager.close()


def test_delayed_writer_cannot_be_overtaken_by_reentrant_forwarding(tmp_path):
    from types import SimpleNamespace
    import time
    from scripts.performance.linux_native_lifecycle_coordinator import Manager
    written = []
    class Sink:
        def write(self, data):
            op = json.loads(bytes(data))['op']
            if op == 'first':
                time.sleep(.1)
            written.append(op)
            return len(data)
        def flush(self):
            pass
    accepted = SimpleNamespace(accept=lambda role, frame: json.loads(frame))
    manager = Manager(None, tmp_path, ledger=accepted)
    manager.children['destination'] = SimpleNamespace(stdin=Sink())
    manager.on_receive = lambda role, value: manager.send('destination', {'op': 'second'})
    manager.messages.put(('source', b'{"event":"forward"}\n'))
    try:
        manager.send('destination', {'op': 'first'})
        manager.pump(0)
        assert written == ['first', 'second']
    finally:
        manager.children.clear()  # In-memory sink, not an owned subprocess.
        manager.close()
