import json

import pytest

from scripts.performance import linux_native_lifecycle_gate as gate
from scripts.performance.linux_native_lifecycle_coordinator import SEQUENCES


def events(role):
    values = []
    for i, name in enumerate(SEQUENCES[role]):
        value = dict(schema='nbsr-native-lifecycle-control-v1', role=role,
                     event=name, timestamp_ns=i * 2_000_000_000)
        if name in ('active', 'released', 'acked', 'complete'):
            value['count'] = 16
        if name == 'ready':
            value['value'] = dict(endpoint='192.0.2.2:1234', alpn='nbsr-quic-1')
        values.append(value)
    return values


def write(path, values):
    path.write_text(''.join(json.dumps(v) + '\n' for v in values))


@pytest.mark.parametrize('role', ['source', 'destination'])
def test_gate_requires_complete_ordered_events_and_local_hold(tmp_path, role):
    path = tmp_path / 'events.ndjson'
    values = events(role)
    write(path, values)
    assert gate.check_events(path, role, 16)['complete']['count'] == 16
    write(path, values[:-1])
    with pytest.raises(InterruptedError):
        gate.check_events(path, role, 16)
    release = next(v for v in values if v['event'] == 'released')
    active = next(v for v in values if v['event'] == 'active')
    release['timestamp_ns'] = active['timestamp_ns'] + 1
    write(path, values)
    with pytest.raises(ValueError, match='hold'):
        gate.check_events(path, role, 16)


def test_gate_rejects_early_destination_cooldown(tmp_path):
    path = tmp_path / 'events.ndjson'
    values = events('destination')
    values[4]['timestamp_ns'] = values[3]['timestamp_ns'] + 1
    write(path, values)
    with pytest.raises(ValueError, match='cooldown'):
        gate.check_events(path, 'destination', 16)
