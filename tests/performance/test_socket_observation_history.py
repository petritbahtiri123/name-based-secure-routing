import json

import pytest

from scripts.performance.linux_b5_placement import seal_output
from scripts.performance.linux_native_pair import analyze_pair
from tests.performance.test_linux_native_pair import SHA, fixture, put


def instrumented_pair(tmp_path):
    roots = fixture(tmp_path)
    for root in roots:
        env = json.loads((root / 'environment.json').read_text())
        put(root, 'environment.json', env | {'live_socket_observer': True})
        final = json.loads((root / 'exit.json').read_text())['final_sample'] | {'timestamp_ns': 1000}
        initial = final | {'state': 'S', 'cpu_ns': 0, 'timestamp_ns': 100}
        (root / 'resources.ndjson').write_text(json.dumps(initial) + '\n' + json.dumps(final) + '\n')
        put(root, 'exit.json', dict(exit_code=0, final_sample=final))
        result = json.loads((root / 'result.json').read_text())
        put(root, 'result.json', result | {'final_sample': final})
        observation = dict(schema='nbsr-linux-live-socket-v1', status='MEASURED_LIVE_SOCKET_SNAPSHOT',
            pid=123, start_ticks=10, binary=json.loads((root / 'command.json').read_text())['argv'][3],
            started_ns=200, finished_ns=300,
            sockets=[dict(fd=3, inode=99, local=[env['bind'].rsplit(':', 1)[0], 4444])])
        put(root, 'socket-ownership.json', observation)
        (root / 'socket-observations.ndjson').write_text(json.dumps(observation) + '\n')
        seal_output(root)
    return roots


def test_valid_observation_history(tmp_path):
    assert analyze_pair(*instrumented_pair(tmp_path), source_sha=SHA)['status'] == 'PASS_FINITE_PAIR_INTEGRITY'


def test_failed_attempt_before_success_is_retained_and_accepted(tmp_path):
    source, destination = instrumented_pair(tmp_path)
    observed = json.loads((source / 'socket-ownership.json').read_text())
    failed = observed | {'status': 'UNAVAILABLE', 'started_ns': 110, 'finished_ns': 120}
    (source / 'socket-observations.ndjson').write_text(json.dumps(failed) + '\n' + json.dumps(observed) + '\n')
    seal_output(source)
    assert analyze_pair(source, destination, source_sha=SHA)['status'] == 'PASS_FINITE_PAIR_INTEGRITY'


@pytest.mark.parametrize('fault', ['observed-port', 'ready-port'])
def test_destination_owned_socket_must_match_announced_port(tmp_path, fault):
    source, destination = instrumented_pair(tmp_path)
    if fault == 'observed-port':
        observed = json.loads((destination / 'socket-ownership.json').read_text())
        observed['sockets'][0]['local'][1] = 5555
        put(destination, 'socket-ownership.json', observed)
        (destination / 'socket-observations.ndjson').write_text(json.dumps(observed) + '\n')
    else:
        ready = json.loads((destination / 'ready.json').read_text())
        ready['endpoint'] = ready['endpoint'].replace(':4444', ':5555')
        put(destination, 'ready.json', ready)
        put(source, 'input-readiness.json', ready)
        env = json.loads((source / 'environment.json').read_text())
        put(source, 'environment.json', env | {'endpoint': ready['endpoint']})
        command = json.loads((source / 'command.json').read_text())
        command['argv'][command['argv'].index('--endpoint') + 1] = ready['endpoint']
        put(source, 'command.json', command)
    for root in (source, destination):
        seal_output(root)
    with pytest.raises(ValueError, match='readiness socket'):
        analyze_pair(source, destination, source_sha=SHA)


def test_readiness_match_is_not_assumed_to_be_first_socket(tmp_path):
    source, destination = instrumented_pair(tmp_path)
    observed = json.loads((destination / 'socket-ownership.json').read_text())
    observed['sockets'].insert(0, dict(fd=4, inode=100, local=[observed['sockets'][0]['local'][0], 5555]))
    put(destination, 'socket-ownership.json', observed)
    (destination / 'socket-observations.ndjson').write_text(json.dumps(observed) + '\n')
    seal_output(destination)
    assert analyze_pair(source, destination, source_sha=SHA)['status'] == 'PASS_FINITE_PAIR_INTEGRITY'


@pytest.mark.parametrize('fault', ['before', 'after', 'missing', 'mismatch', 'extra-success',
                                  'too-many', 'reversed-attempts', 'other-pid', 'boolean-time',
                                  'resource-clock-regression'])
def test_resealed_stale_or_inconsistent_history_rejects(tmp_path, fault):
    source, destination = instrumented_pair(tmp_path)
    observed = json.loads((source / 'socket-ownership.json').read_text())
    history = [observed.copy()]
    if fault == 'before':
        observed.update(started_ns=1, finished_ns=2)
        history = [observed]
    elif fault == 'after':
        observed.update(started_ns=1100, finished_ns=1200)
        history = [observed]
    elif fault == 'missing':
        (source / 'socket-observations.ndjson').unlink()
    elif fault == 'mismatch':
        history[0]['finished_ns'] = 301
    elif fault == 'extra-success':
        history.append(observed.copy())
    elif fault == 'too-many':
        history = [observed | {'status': 'UNAVAILABLE'}] * 20 + [observed]
    elif fault == 'reversed-attempts':
        history.insert(0, observed | {'status': 'UNAVAILABLE', 'started_ns': 400, 'finished_ns': 500})
    elif fault == 'other-pid':
        history.insert(0, observed | {'status': 'UNAVAILABLE', 'pid': 999, 'started_ns': 101, 'finished_ns': 102})
    elif fault == 'boolean-time':
        observed['started_ns'] = True
        history = [observed]
    else:
        values = [json.loads(line) for line in (source / 'resources.ndjson').read_text().splitlines()]
        values.insert(1, values[0] | {'timestamp_ns': 90})
        (source / 'resources.ndjson').write_text(''.join(json.dumps(v) + '\n' for v in values))
    put(source, 'socket-ownership.json', observed)
    if fault != 'missing':
        (source / 'socket-observations.ndjson').write_text(''.join(json.dumps(v) + '\n' for v in history))
    seal_output(source)
    with pytest.raises(ValueError):
        analyze_pair(source, destination, source_sha=SHA)
