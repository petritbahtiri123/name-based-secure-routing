"""Independent retained sequential-cycle evidence gate; diagnostic scope only."""

import json

from scripts.performance.linux_b5_ceiling import require
from scripts.performance.linux_native_cycle_coordinator import CycleLedger, sequence
from scripts.performance.linux_native_cycle_limits import validate_shape, validate_active_shape
from scripts.performance.linux_native_lifecycle_pair import check_peer
from scripts.performance.linux_native_pair import read, verify_index
from scripts.performance.linux_socket_ownership import validate_binding


def check_events(path, role, cycles):
    ledger = CycleLedger(cycles)
    with path.open('rb') as stream:
        for _ in sequence(role, cycles):
            wire = stream.readline(65537)
            require(0 < len(wire) <= 65536 and wire.endswith(b'\n'), 'bounded complete cycle event required')
            ledger.accept(role, wire)
        require(not stream.read(1), 'excess cycle event input')
    ledger.eof(role)
    values = {key: value for (peer, key), value in ledger.received.items() if peer == role}
    for cycle in range(cycles):
        require(values['released', cycle]['timestamp_ns'] - values['active', cycle]['timestamp_ns'] >= 2_000_000_000,
                'cycle local hold too short')
        if cycle:
            previous = 'acked' if role == 'source' else 'released'
            require(values['started', cycle]['timestamp_ns'] - values[previous, cycle - 1]['timestamp_ns'] >= 2_000_000_000,
                    'cycle local cooldown too short')
    previous = 'acked' if role == 'source' else 'report_ready'
    require(values['final_released', cycles - 1]['timestamp_ns'] - values[previous, cycles - 1]['timestamp_ns'] >= 2_000_000_000,
            'final cycle cooldown too short')
    return values


def check_endpoint(root, role, cycles, *, streams=1, channels=1):
    total = validate_shape(streams, channels)
    index = verify_index(root)
    require(not any((root / n).exists() for n in ('failure.json', 'marker-preservation-error.json')), 'failed cycle endpoint')
    controller, result = read(root, 'controller.json'), read(root, 'result.json')
    require(controller['schema'] == 'nbsr-native-cycle-control-v1' and controller['role'] == result['role'] == role
            and type(controller['count']) is int and controller['count'] == cycles
            and controller['hold_seconds'] == controller['cooldown_seconds'] == 2
            and type(controller.get('channels', 1)) is int and controller.get('channels', 1) == channels
            and type(controller.get('streams', 1)) is int and controller.get('streams', 1) == streams
            and result['status'] == 'PASS_FUNCTIONAL_ENDPOINT', 'cycle endpoint contract mismatch')
    events = check_events(root / 'events.ndjson', role, cycles)
    prefix = 'connection' if role == 'source' else 'destination'
    expected = {f'{prefix}-{i}.active' for i in range(cycles)}
    expected |= {f'connection-{i}.release' for i in range(cycles)}
    if role == 'source':
        expected |= {f'connection-{i}.{suffix}' for i in range(cycles) for suffix in ('start', 'ack')}
        expected.add('source.final-release')
    else:
        expected |= {'destination.report-ready', 'destination.report-release'}
    require({p.name for p in (root / 'markers').iterdir()} == expected
            and all((root / 'markers' / n).is_file() for n in expected), 'cycle marker set mismatch')
    if role == 'destination' and total > 1:
        for cycle in range(cycles):
            validate_active_shape(read(root / 'markers', f'destination-{cycle}.active'), streams, channels)
    peer = root / 'peer'
    pid, command = read(peer, 'pid.json'), read(peer, 'command.json')
    with (peer / 'resources.ndjson').open() as stream:
        first = json.loads(stream.readline())
    require(first['pid'] == pid['pid'], 'cycle resource/PID identity mismatch')
    for cycle in range(cycles):
        binding = read(root, f'socket-binding-{cycle}.json')
        require(len(binding['sockets']) == 1 and first['timestamp_ns'] <= binding['started_ns']
                <= binding['finished_ns'] <= events['active', cycle]['timestamp_ns']
                and binding['started_ns'] >= events['started', cycle]['timestamp_ns'],
                'cycle socket observation outside local active preparation')
        validate_binding(binding, pid=pid['pid'], start_ticks=first['start_ticks'], binary=command['argv'][3],
                         local=binding['sockets'][0]['local'])
    return dict(index_sha256=index, events=events)


def analyze(source, destination, *, source_sha, count, streams=1, channels=1):
    total = validate_shape(streams, channels)
    require(source.resolve() != destination.resolve(), 'distinct cycle peer roots required')
    peers = {role: check_peer(root, role, source_sha, count, cycles=count, streams=streams, channels=channels)
             for role, root in (('source', source), ('destination', destination))}
    for field in ('count', 'cycles', 'binary_sha256', 'fixture_sha256'):
        require(peers['source']['environment'][field] == peers['destination']['environment'][field], 'cycle paired identity mismatch')
    require(peers['source']['readiness'] == peers['destination']['readiness'], 'cycle readiness mismatch')
    return dict(status='PASS_FUNCTIONAL_CYCLE_PEERS', source_sha=source_sha, cycles=count,
        successful_connections=count, same_process_epochs='VERIFIED_FROM_RETAINED_RESOURCE_SAMPLES',
        source_cleanup=peers['source']['outcome']['ownership'], destination_cleanup=peers['destination']['outcome']['ownership'],
        memory_cost='NOT_QUALIFIED', sustainable_capacity='NOT_ESTABLISHED', physical_hardware='NOT_PROVEN',
        **({'streams_per_channel': streams, 'successful_operations': count * total} if total > 1 else {}),
        **({'channels_per_session': channels} if channels > 1 else {}))
