"""Independent functional gate for retained native endpoint barriers."""

import json

from scripts.performance.linux_b5_ceiling import require
from scripts.performance.linux_native_lifecycle_coordinator import EventLedger
from scripts.performance.linux_native_pair import read, verify_index
from scripts.performance.linux_socket_ownership import validate_binding


def check_events(path, role, count):
    ledger = EventLedger(count)
    with path.open('rb') as stream:
        for _ in range(7):
            wire = stream.readline(65537)
            if not wire:
                break
            require(len(wire) <= 65536 and wire.endswith(b'\n'), 'bounded event required')
            ledger.accept(role, wire)
        require(not stream.read(1), 'excess event input')
    ledger.eof(role)
    values = {name: value for (peer, name), value in ledger.received.items() if peer == role}
    require(values['released']['timestamp_ns'] - values['active']['timestamp_ns'] >= 2_000_000_000,
            'local active hold too short')
    if role == 'destination':
        require(values['report_released']['timestamp_ns'] - values['report_ready']['timestamp_ns'] >= 2_000_000_000,
                'local cooldown too short')
    return values


def check_endpoint(root, role, count, *, memory_observer=False):
    require(type(memory_observer) is bool, 'boolean memory observer required')
    index = verify_index(root)
    require(not any((root / name).exists() for name in ('failure.json', 'marker-preservation-error.json')),
            'failed endpoint cannot pass')
    controller, result = read(root, 'controller.json'), read(root, 'result.json')
    require(controller['schema'] == 'nbsr-native-lifecycle-control-v1'
            and controller['role'] == result['role'] == role and type(controller['count']) is int
            and type(controller.get('memory_observer', False)) is bool and controller.get('memory_observer', False) == memory_observer
            and controller['count'] == count and controller['hold_seconds'] == controller['cooldown_seconds'] == 2
            and result['status'] == 'PASS_FUNCTIONAL_ENDPOINT', 'endpoint contract mismatch')
    events = check_events(root / 'events.ndjson', role, count)
    expected = {f'connection-{i}.release' for i in range(count)}
    prefix = 'connection' if role == 'source' else 'destination'
    expected |= {f'{prefix}-{i}.active' for i in range(count)}
    if role == 'source':
        expected |= {f'connection-{i}.{suffix}' for i in range(count) for suffix in ('start', 'ack')}
    else:
        expected |= {'destination.report-ready', 'destination.report-release'}
    require({p.name for p in (root / 'markers').iterdir()} == expected, 'marker set mismatch')
    require(all((root / 'markers' / name).is_file() for name in expected), 'marker is not file')
    peer = root / 'peer'
    binding, pid, command = read(root, 'socket-binding.json'), read(peer, 'pid.json'), read(peer, 'command.json')
    with (peer / 'resources.ndjson').open() as stream:
        first = json.loads(stream.readline())
    require(first['pid'] == pid['pid'] and len(binding['sockets']) == (count if role == 'source' else 1)
            and len({s['inode'] for s in binding['sockets']}) == len(binding['sockets']), 'socket count/identity mismatch')
    require(first['timestamp_ns'] <= binding['started_ns'] <= binding['finished_ns'] <= events['active']['timestamp_ns'],
            'socket observation outside active interval')
    for socket in binding['sockets']:
        validate_binding(binding, pid=pid['pid'], start_ticks=first['start_ticks'], binary=command['argv'][3], local=socket['local'])
    return dict(index_sha256=index, events=events)
