import copy
import json

import pytest

from scripts.performance.linux_native_lifecycle_coordinator import EventLedger, drive, validate_config


def config():
    value = dict(schema='nbsr-native-lifecycle-coordinator-v1', source_sha='a' * 40, count=16, rate=100, shards=2)
    for role, ip in [('source', '192.0.2.1'), ('destination', '192.0.2.2')]:
        value[role] = dict(transport='ssh', host='bench@' + role, checkout='/srv/nbsr',
            binaries='/srv/bin', build_manifest='/srv/build.json', authority='/srv/private/tls',
            lifecycle='/srv/private/lifecycle', output='/srv/evidence/run', bind=ip + ':0', cores=1)
    return value


def test_config_requires_exact_bounded_workload_and_disjoint_paths():
    assert validate_config(config()) == config()
    changes = [('count', True), ('count', 1024), ('rate', 0), ('shards', 3),
               ('source_sha', 'not-a-sha'), ('schema', 'unknown'), ('extra', 1)]
    for key, value in changes:
        bad = config()
        bad[key] = value
        with pytest.raises(ValueError):
            validate_config(bad)
    for field, value in [('output', '/srv/nbsr/out'), ('output', '/srv/private'),
                         ('output', '/srv/private/tls/out'), ('bind', '192.0.2.1:1234'),
                         ('host', '-oBad'), ('cores', True), ('lifecycle', '/srv/../private')]:
        bad = config()
        bad['source'][field] = value
        with pytest.raises(ValueError):
            validate_config(bad)


def test_coordinator_prepares_before_listening_and_preserves_all_barriers():
    events = []
    ready = dict(endpoint='192.0.2.2:1234', alpn='nbsr-quic-1')

    def wait(role, event):
        events.append(('wait', role, event))
        return dict(value=ready) if event == 'ready' else dict(event=event, count=16)

    drive(lambda role: events.append(('start', role)), wait,
          lambda role, message: events.append(('send', role, message)),
          lambda role: events.append(('finish', role)), sleep=lambda seconds: events.append(('hold', seconds)))
    assert events[:4] == [('start', 'source'), ('wait', 'source', 'prepared'),
                         ('start', 'destination'), ('wait', 'destination', 'ready')]
    assert ('send', 'source', dict(op='readiness', value=ready)) in events
    active = events.index(('wait', 'destination', 'active'))
    assert events[active + 1:active + 5] == [('hold', 2), ('send', 'destination', dict(op='release')),
        ('wait', 'destination', 'released'), ('send', 'source', dict(op='release'))]
    report = events.index(('wait', 'destination', 'report_ready'))
    assert events[report + 1:report + 3] == [('hold', 2), ('send', 'destination', dict(op='report_release'))]
    assert events[-2:] == [('finish', 'source'), ('finish', 'destination')]


def test_missing_destination_active_never_releases_either_peer():
    sent = []

    def wait(role, event):
        if role == 'destination' and event == 'active':
            raise TimeoutError('missing destination active')
        return dict(value={})

    with pytest.raises(TimeoutError):
        drive(lambda role: None, wait, lambda role, value: sent.append(value), lambda role: None,
              sleep=lambda _: pytest.fail('hold must not start before both active'))
    assert sent == [dict(op='readiness', value={})]


def event(role, name, timestamp=1, **fields):
    return dict(schema='nbsr-native-lifecycle-control-v1', role=role, event=name, timestamp_ns=timestamp, **fields)


def test_event_ledger_rejects_wrong_role_schema_count_clock_and_order():
    ledger = EventLedger(16)
    ledger.accept('source', json.dumps(event('source', 'prepared')).encode())
    ledger.accept('source', json.dumps(event('source', 'readiness_transferred', 2)).encode())
    valid = event('source', 'active', 3, count=16)
    for changes in [dict(role='destination'), dict(schema='bad'), dict(count=True), dict(count=15),
                    dict(timestamp_ns=0), dict(event='complete'), dict(extra=1)]:
        with pytest.raises(ValueError):
            copy.deepcopy(ledger).accept('source', json.dumps(valid | changes).encode())
    assert ledger.accept('source', json.dumps(valid).encode()) == valid
    with pytest.raises(ValueError):
        ledger.accept('source', json.dumps(valid).encode())
    with pytest.raises(InterruptedError, match='EOF'):
        ledger.eof('source')


def test_ledger_accepts_independent_host_clocks_and_eof_only_after_completion():
    ledger = EventLedger(16)
    sequences = dict(source=['prepared', 'readiness_transferred', 'active', 'released', 'acked', 'complete'],
                    destination=['ready', 'active', 'released', 'report_ready', 'report_released', 'complete'])
    for role, names in sequences.items():
        for i, name in enumerate(names):
            fields = dict(count=16) if name in ('active', 'released', 'acked', 'complete') else {}
            if name == 'ready':
                fields['value'] = dict(endpoint='192.0.2.2:1234', alpn='nbsr-quic-1')
            ledger.accept(role, json.dumps(event(role, name, (1000000 if role == 'source' else 1) + i, **fields)).encode())
        ledger.eof(role)
