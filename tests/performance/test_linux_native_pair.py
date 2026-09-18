import hashlib
import json
from pathlib import Path

import pytest

from scripts.performance.linux_b5_placement import seal_output
from scripts.performance.linux_native_peer import native_command


SHA = 'a' * 40


def put(root, name, value):
    (root / name).write_text(json.dumps(value))


def fixture(tmp_path, mode='nbsr'):
    cell = dict(path=mode, cores=1, payload_bytes=1024, streams=64, outstanding=1)
    names = ('perf_direct_peer', 'perf_rust_source', 'wp8_interop_server')
    hashes = {n: hashlib.sha256(n.encode()).hexdigest() for n in names}
    ready = dict(endpoint='192.0.2.11:4444', alpn='nbsr-quic-1')
    dirs = []
    for role, address in (('source', '192.0.2.10'), ('destination', '192.0.2.11')):
        root = tmp_path / role
        root.mkdir()
        dirs.append(root)
        env = dict(role=role, cell=cell, repository_sha=SHA, binary_sha256=hashes,
                   certificates_sha256={'ca.der': 'b' * 64, role + '.der': 'c' * 64},
                   bind=address + ':0', endpoint=ready['endpoint'] if role == 'source' else None,
                   warmup_seconds=3, duration_seconds=20,
                   linux_environment={'selected_cpus': [0]})
        put(root, 'environment.json', env)
        put(root, 'build-manifest.json', dict(source_sha=SHA, build_profile='release',
            binary_sha256=hashes, build_commands=['cargo build --release'], toolchains={'rust': 'fixture'}))
        argv, overrides = native_command(cell, role, Path('/bins'), Path('/private'), root,
                                        bind=env['bind'], endpoint=env['endpoint'])
        argv = [arg.replace('\\', '/') for arg in argv]  # Linux evidence, including on Windows test hosts.
        put(root, 'command.json', dict(argv=['taskset', '--cpu-list', '0', *argv], environment_overrides=overrides))
        binary = names[0] if mode == 'direct' else names[1 if role == 'source' else 2]
        (root / 'executed-binary').write_bytes(binary.encode())
        sample = dict(pid=123, start_ticks=10, state='Z', cpu_ns=1000, affinity=[0])
        (root / 'resources.ndjson').write_text(json.dumps(sample) + '\n')
        put(root, 'pid.json', dict(pid=123, owns_process_group=True))
        put(root, 'exit.json', dict(exit_code=0, final_sample=sample))
        result = dict(status='PASS_FINITE_PEER', role=role, exit_code=0, final_sample=sample)
        if role == 'source':
            row = dict(path=mode, payload_bytes=1024, streams=64, outstanding_per_stream=1,
                       completed_operations=100, measured_ns=20000000000,
                       errors=0, missing=0, duplicates=0, corrupt=0, wrong_request=0,
                       transport_sessions_created_delta=0, service_channels_created_delta=0,
                       application_streams_created_delta=0, replay_entries_delta=0)
            put(root, 'validated-result.json', row)
            (root / 'stdout').write_text(json.dumps(row) + '\n')
            result.update(completed_operations=100, application_gbps=16 * 1024 * 100 / row['measured_ns'])
            put(root, 'input-readiness.json', ready)
        else:
            put(root, 'ready.json', ready)
            if mode == 'direct':
                (root / 'completion.ack').touch()
            else:
                put(root, 'server-result.json', dict(status='PASS', streams=64))
        put(root, 'result.json', result)
        seal_output(root)
    return dirs


@pytest.mark.parametrize('mode', ['direct', 'nbsr'])
def test_valid_pair_is_integrity_only_not_capacity_or_external_hardware(tmp_path, mode):
    from scripts.performance.linux_native_pair import analyze_pair
    source, destination = fixture(tmp_path, mode)
    result = analyze_pair(source, destination, source_sha=SHA)
    assert result['status'] == 'PASS_FINITE_PAIR_INTEGRITY'
    assert result['strict_stable_capacity'] == result['external_hardware'] == 'NOT_PROVEN'


@pytest.mark.parametrize('fault', ['unindexed', 'duplicate-index', 'path-traversal', 'tamper',
    'sha', 'ca', 'ready', 'workload', 'exit', 'pid', 'terminal', 'source-row', 'forced-cleanup', 'binary',
    'command', 'override', 'goodput', 'manifest', 'cpu-regression'])
def test_pair_refuses_corrupt_stale_or_incompatible_evidence(tmp_path, fault):
    from scripts.performance.linux_native_pair import analyze_pair
    source, destination = fixture(tmp_path)
    if fault == 'unindexed':
        (source / 'extra.txt').write_text('not sealed')
    elif fault == 'duplicate-index':
        p = source / 'checksums.sha256'
        p.write_text(p.read_text() + p.read_text().splitlines()[0] + '\n')
    elif fault == 'path-traversal':
        with (source / 'checksums.sha256').open('a') as f:
            f.write('0' * 64 + '  ../outside\n')
    elif fault == 'tamper':
        (source / 'stdout').write_text('changed after seal')
    else:
        if fault in ('sha', 'ca', 'workload'):
            p = destination / 'environment.json'
            v = json.loads(p.read_text())
            if fault == 'sha':
                v['repository_sha'] = 'd' * 40
            elif fault == 'ca':
                v['certificates_sha256']['ca.der'] = 'd' * 64
            else:
                v['cell']['streams'] = 32
            put(destination, p.name, v)
        elif fault == 'ready':
            put(source, 'input-readiness.json', dict(endpoint='192.0.2.11:4445', alpn='nbsr-quic-1'))
        elif fault == 'forced-cleanup':
            put(source, 'forced-cleanup.json', dict(valid=False))
        elif fault == 'binary':
            (source / 'executed-binary').write_bytes(b'wrong executable')
        elif fault in ('command', 'override'):
            v = json.loads((source / 'command.json').read_text())
            if fault == 'command':
                i = v['argv'].index('--payload-bytes')
                v['argv'][i + 1] = '16384'
            else:
                v['environment_overrides']['NBSR_UNEXPECTED'] = '1'
            put(source, 'command.json', v)
        elif fault == 'goodput':
            v = json.loads((source / 'result.json').read_text())
            v['application_gbps'] *= 2
            put(source, 'result.json', v)
        elif fault == 'manifest':
            v = json.loads((source / 'build-manifest.json').read_text())
            v['build_profile'] = 'debug'
            put(source, 'build-manifest.json', v)
        elif fault == 'cpu-regression':
            p = source / 'resources.ndjson'
            v = json.loads(p.read_text())
            v.update(state='S', cpu_ns=1001)
            p.write_text(json.dumps(v) + '\n' + p.read_text())
        elif fault == 'source-row':
            p = source / 'validated-result.json'
            v = json.loads(p.read_text())
            v['completed_operations'] += 1
            put(source, p.name, v)
        else:
            p = source / ('exit.json' if fault == 'exit' else 'pid.json' if fault == 'pid' else 'resources.ndjson')
            v = json.loads(p.read_text())
            if fault == 'exit':
                v['exit_code'] = 1
            elif fault == 'pid':
                v['pid'] = 124
            else:
                v['state'] = 'S'
            put(source, p.name, v)
        seal_output(source)
        seal_output(destination)
    with pytest.raises(ValueError):
        analyze_pair(source, destination, source_sha=SHA)
