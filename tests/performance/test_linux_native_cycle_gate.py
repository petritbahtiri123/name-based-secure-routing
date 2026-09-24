import importlib
import json

import pytest

from scripts.performance.linux_native_cycle_coordinator import sequence


def values(role):
    result = []
    for i, (name, cycle) in enumerate(sequence(role, 2)):
        value = dict(schema='nbsr-native-cycle-control-v1', role=role, event=name, timestamp_ns=i * 2_000_000_000)
        if cycle is not None:
            value['cycle'] = cycle
        if name == 'ready':
            value['value'] = {}
        result.append(value)
    return result


def write(path, rows):
    path.write_text(''.join(json.dumps(r) + '\n' for r in rows))


@pytest.mark.parametrize('role', ['source', 'destination'])
def test_cycle_replay_requires_every_local_hold_and_cooldown(tmp_path, role):
    gate = importlib.import_module('scripts.performance.linux_native_cycle_gate')
    path = tmp_path / 'events.ndjson'
    rows = values(role)
    write(path, rows)
    checked = gate.check_events(path, role, 2)
    assert ('active', 1) in checked and 'complete' in checked
    active = next(r for r in rows if r['event'] == 'active' and r['cycle'] == 1)
    release = next(r for r in rows if r['event'] == 'released' and r['cycle'] == 1)
    release['timestamp_ns'] = active['timestamp_ns'] + 1
    write(path, rows)
    with pytest.raises(ValueError, match='hold'):
        gate.check_events(path, role, 2)


def test_next_cycle_cannot_skip_source_cooldown(tmp_path):
    gate = importlib.import_module('scripts.performance.linux_native_cycle_gate')
    rows = values('source')
    ack = next(r for r in rows if r['event'] == 'acked' and r['cycle'] == 0)
    start = next(r for r in rows if r['event'] == 'started' and r['cycle'] == 1)
    start['timestamp_ns'] = ack['timestamp_ns'] + 1
    path = tmp_path / 'events.ndjson'
    write(path, rows)
    with pytest.raises(ValueError, match='cooldown'):
        gate.check_events(path, 'source', 2)
