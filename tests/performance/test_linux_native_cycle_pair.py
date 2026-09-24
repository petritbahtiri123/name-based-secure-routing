import json
from pathlib import PurePosixPath

import pytest

from scripts.performance import linux_native_lifecycle_pair as pair
from scripts.performance.linux_native_lifecycle import cycle_command, validate_result
from scripts.performance.linux_b5_placement import seal_output
from scripts.performance.post_close_cleanup import FIELDS
from tests.performance.test_linux_native_lifecycle_pair import peers, SHA, write


def cycle_peers(tmp_path):
    roots = peers(tmp_path)
    for role, root in zip(('source', 'destination'), roots, strict=True):
        env = json.loads((root / 'environment.json').read_bytes())
        env.update(count=2, cycles=2, offered_rate=None, source_shards=None, workload_mode='same_process_sequential')
        write(root, 'environment.json', env)
        argv, overrides = cycle_command(role=role, cycles=2, binaries=PurePosixPath('/bins'),
            authority=PurePosixPath('/private/tls'), lifecycle=PurePosixPath('/private/lifecycle'),
            output=PurePosixPath('/output'), bind='192.0.2.1:0' if role == 'source' else '192.0.2.2:0',
            endpoint='192.0.2.2:4444' if role == 'source' else None)
        write(root, 'command.json', dict(argv=['/usr/bin/taskset', '--cpu-list', '0', *argv], environment_overrides=overrides))
        final = dict(phase='lifecycle_cleanup', **dict.fromkeys(FIELDS, 0))
        rows = []
        server = None
        if role == 'source':
            for cycle in range(2):
                rows.extend([dict(success=True, logical_client_id=cycle, bytes_transmitted=1024, bytes_received=1024),
                    dict(phase=f'lifecycle_cycle_{cycle}_closed', **dict.fromkeys(FIELDS, 0))])
        else:
            server = dict(status='PASS', connections=2, samples=[{}, {}])
            write(root, 'server-result.json', server)
        rows.append(final)
        (root / ('stdout' if role == 'source' else 'diagnostics.ndjson')).write_text(''.join(json.dumps(r) + '\n' for r in rows))
        result = json.loads((root / 'result.json').read_bytes())
        result.update(validate_result(role, 2, rows, server))
        write(root, 'result.json', result)
        seal_output(root)
    return roots


def test_cycle_peer_gate_requires_same_process_and_exact_sequential_command(tmp_path):
    source, _ = cycle_peers(tmp_path)
    result = pair.check_peer(source, 'source', SHA, 2, cycles=2)
    assert result['outcome']['successful'] == 2
    assert result['environment']['workload_mode'] == 'same_process_sequential'


@pytest.mark.parametrize('mutation', ['missing-cycle', 'duplicate-cycle', 'mode', 'epoch'])
def test_cycle_peer_rejects_incomplete_or_replaced_process(tmp_path, mutation):
    source, _ = cycle_peers(tmp_path)
    if mutation in ('missing-cycle', 'duplicate-cycle'):
        rows = [json.loads(r) for r in (source / 'stdout').read_text().splitlines()]
        if mutation == 'missing-cycle':
            rows.pop(1)
        else:
            rows.insert(1, rows[1])
        (source / 'stdout').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    elif mutation == 'mode':
        value = json.loads((source / 'environment.json').read_bytes())
        value['workload_mode'] = 'bundles'
        write(source, 'environment.json', value)
    else:
        rows = [json.loads(r) for r in (source / 'resources.ndjson').read_text().splitlines()]
        rows[-1]['start_ticks'] += 1
        (source / 'resources.ndjson').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    seal_output(source)
    with pytest.raises(ValueError):
        pair.check_peer(source, 'source', SHA, 2, cycles=2)
