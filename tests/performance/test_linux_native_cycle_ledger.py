import importlib
import json

import pytest


def module():
    return importlib.import_module('scripts.performance.linux_native_cycle_coordinator')


def event(role, name, timestamp, cycle=None):
    value = dict(schema='nbsr-native-cycle-control-v1', role=role, event=name, timestamp_ns=timestamp)
    if cycle is not None:
        value['cycle'] = cycle
    if name == 'ready':
        value['value'] = {'endpoint': '192.0.2.2:1234', 'alpn': 'nbsr-quic-1'}
    return json.dumps(value).encode()


def transcript(role, cycles=2):
    initial = ['prepared', 'readiness_transferred'] if role == 'source' else ['ready']
    result = [(name, None) for name in initial]
    for cycle in range(cycles):
        result.extend((name, cycle) for name in ('started', 'active', 'released'))
        if role == 'source':
            result.append(('acked', cycle))
    if role == 'destination':
        result.append(('report_ready', cycles - 1))
    result.extend([('final_released', cycles - 1), ('complete', None)])
    return result


@pytest.mark.parametrize('role', ['source', 'destination'])
def test_full_transcript_is_indexed_by_cycle_without_overwriting(role):
    ledger = module().CycleLedger(2)
    for timestamp, (name, cycle) in enumerate(transcript(role)):
        value = ledger.accept(role, event(role, name, timestamp, cycle))
        assert value['event'] == name
    ledger.eof(role)
    assert ledger.received[role, ('active', 0)]['cycle'] == 0
    assert ledger.received[role, ('active', 1)]['cycle'] == 1
    with pytest.raises(ValueError):
        ledger.accept(role, event(role, 'complete', 999))


@pytest.mark.parametrize('wrong', [1, True, '0', -1])
def test_cycle_identity_is_exact_and_ordered(wrong):
    ledger = module().CycleLedger(2)
    ledger.accept('source', event('source', 'prepared', 0))
    ledger.accept('source', event('source', 'readiness_transferred', 1))
    with pytest.raises(ValueError):
        ledger.accept('source', event('source', 'started', 2, wrong))


def test_replay_clock_regression_extra_fields_and_eof_fail():
    ledger = module().CycleLedger(2)
    wire = event('destination', 'ready', 10)
    value = json.loads(wire)
    value['extra'] = True
    with pytest.raises(ValueError):
        ledger.accept('destination', json.dumps(value).encode())
    ledger.accept('destination', wire)
    with pytest.raises(ValueError):
        ledger.accept('destination', wire)
    with pytest.raises(ValueError):
        ledger.accept('destination', event('destination', 'started', 9, 0))
    with pytest.raises(InterruptedError):
        ledger.eof('destination')


def test_driver_starts_next_only_after_source_ack_and_cooldown():
    calls = []
    def wait(role, name):
        calls.append(('wait', role, name))
        return {'value': {'endpoint': '192.0.2.2:1234'}}
    module().drive_cycles(2,
        lambda role: calls.append(('launch', role)), wait,
        lambda role, value: calls.append(('send', role, value)),
        lambda role: calls.append(('finish', role)),
        sleep=lambda seconds: calls.append(('sleep', seconds)))
    ack = calls.index(('wait', 'source', ('acked', 0)))
    next_start = calls.index(('send', 'destination', {'op': 'start', 'cycle': 1}))
    assert calls[ack + 1] == ('sleep', 2)
    assert next_start > ack + 1
    dest_release = calls.index(('send', 'destination', {'op': 'release', 'cycle': 0}))
    src_release = calls.index(('send', 'source', {'op': 'release', 'cycle': 0}))
    assert dest_release < src_release
    assert calls.count(('launch', 'source')) == calls.count(('launch', 'destination')) == 1
    assert calls[-2:] == [('finish', 'source'), ('finish', 'destination')]
