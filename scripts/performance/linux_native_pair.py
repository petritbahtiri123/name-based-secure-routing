"""Read-only integrity/join gate for transferred finite native peer evidence.

Checksums detect corruption; they are not signatures or remote attestation.
This gate neither authenticates a host nor classifies sustainable capacity.
"""

import argparse
import json
import math
from pathlib import Path, PurePosixPath
import re

from scripts.performance.linux_b5_ceiling import NAMES, require
from scripts.performance.linux_loopback import digest, validate_matrix
from scripts.performance.linux_native_peer import validate_endpoint
from scripts.performance.p2a_established import validate_repeat


def read(root, name):
    return json.loads((root / name).read_bytes())


def verify_index(root):
    require(not root.is_symlink(), 'symlink evidence root')
    root = root.resolve()
    files = set()
    for path in root.rglob('*'):
        require(not path.is_symlink(), 'symlink evidence entry')
        if path.is_file() and path.name != 'checksums.sha256':
            files.add(path.relative_to(root).as_posix())
        elif path.is_file() and path.parent != root:
            files.add(path.relative_to(root).as_posix())
    indexed = set()
    for line in (root / 'checksums.sha256').read_text().splitlines():
        expected, separator, name = line.partition('  ')
        relative = PurePosixPath(name)
        require(separator and re.fullmatch('[0-9a-f]{64}', expected)
                and name and not relative.is_absolute() and '..' not in relative.parts
                and '\\' not in name and ':' not in name and relative.as_posix() == name
                and name not in indexed and name != 'checksums.sha256', 'invalid/duplicate checksum entry')
        path = (root / name).resolve()
        require(path.is_relative_to(root) and path.is_file() and digest(path) == expected,
                'checksum mismatch: ' + name)
        indexed.add(name)
    require(indexed == files and indexed, 'checksum index is not a complete inventory')
    return digest(root / 'checksums.sha256')


def check_peer(root, role, source_sha):
    index = verify_index(root)
    require(not any((root / n).exists() for n in ('failure.json', 'forced-cleanup.json')),
            'failed/forced peer cannot be accepted')
    env, result, build = (read(root, n) for n in ('environment.json', 'result.json', 'build-manifest.json'))
    require(env['role'] == result['role'] == role and env['repository_sha'] == source_sha,
            'peer role/source mismatch')
    cell = env['cell']
    require(cell['path'] in ('direct', 'nbsr'), 'unknown path')
    validate_matrix(dict(schema='nbsr-linux-loopback-v1', cores=[cell['cores']],
        workloads=[{k: cell[k] for k in ('payload_bytes', 'streams', 'outstanding')}],
        warmup_seconds=env['warmup_seconds'], duration_seconds=env['duration_seconds']))
    require(env['warmup_seconds'] == 3 and env['duration_seconds'] == 20, 'finite duration mismatch')
    require(build['source_sha'] == source_sha and build['build_profile'] == 'release'
            and build['binary_sha256'] == env['binary_sha256'] and build['build_commands']
            and build['toolchains'], 'release manifest mismatch')
    require(set(env['binary_sha256']) == set(NAMES.values())
            and all(re.fullmatch('[0-9a-f]{64}', h) for h in env['binary_sha256'].values()),
            'invalid binary hashes')
    certs = env['certificates_sha256']
    require(set(certs) == {'ca.der', role + '.der'}
            and all(re.fullmatch('[0-9a-f]{64}', h) for h in certs.values()), 'invalid certificate hashes')
    name = NAMES['direct'] if cell['path'] == 'direct' else NAMES['nbsr' if role == 'source' else 'server']
    require(digest(root / 'executed-binary') == env['binary_sha256'][name], 'executed binary mismatch')
    command = read(root, 'command.json')
    argv = command['argv']
    cpus = env['linux_environment']['selected_cpus']
    require(len(cpus) == cell['cores'] and len(set(cpus)) == len(cpus), 'CPU pool mismatch')
    require(len(argv) > 4 and PurePosixPath(argv[0]).name == 'taskset'
            and argv[1:3] == ['--cpu-list', ','.join(map(str, cpus))]
            and PurePosixPath(argv[3]).name == name, 'executable/affinity command mismatch')
    def option(key, expected):
        require(argv.count(key) == 1 and argv.index(key) + 1 < len(argv)
                and argv[argv.index(key) + 1] == str(expected), 'command mismatch: ' + key)
    option('--p2a-runtime-workers', cell['cores'])
    option('--benchmark-client-bind' if role == 'source' else '--benchmark-listen', env['bind'])
    validate_endpoint(env['bind'], allow_zero=True)
    overrides = {'NBSR_P2A_STREAMS': str(cell['streams'])} if role == 'destination' and cell['path'] == 'nbsr' else {}
    require(command['environment_overrides'] == overrides, 'experiment overrides mismatch')
    if role == 'source':
        for key, value in {'--endpoint': env['endpoint'], '--payload-bytes': cell['payload_bytes'],
                '--p2a-streams': cell['streams'], '--p2a-outstanding-per-stream': cell['outstanding'],
                '--p2a-warmup-seconds': 3, '--p2a-duration-seconds': 20}.items():
            option(key, value)
    elif cell['path'] == 'direct':
        option('--p2a-streams', cell['streams'])
    exit_record, pid = read(root, 'exit.json'), read(root, 'pid.json')
    require(result['status'] == 'PASS_FINITE_PEER' and result['exit_code'] == exit_record['exit_code'] == 0
            and result['final_sample'] == exit_record['final_sample'] and pid['owns_process_group'] is True,
            'peer exit contract failed')
    first = previous = last = None
    with (root / 'resources.ndjson').open() as stream:
        for line in stream:
            sample = json.loads(line)
            identity = sample['pid'], sample['start_ticks']
            first = identity if first is None else first
            require(sample['pid'] == pid['pid'] and identity == first, 'sample PID identity mismatch')
            require(type(sample['cpu_ns']) is int and sample['cpu_ns'] >= 0
                    and (previous is None or sample['cpu_ns'] >= previous), 'CPU counter regressed')
            require(sample['affinity'] == cpus, 'sample affinity mismatch')
            require(last is None or last['state'] != 'Z', 'sample after terminal exit')
            previous, last = sample['cpu_ns'], sample
    require(last is not None and last['state'] == 'Z' and last == exit_record['final_sample'],
            'terminal sample mismatch')
    return env, result, index


def analyze_pair(source, destination, *, source_sha):
    require(re.fullmatch('[0-9a-f]{40}', source_sha), 'full expected source SHA required')
    source, destination = Path(source), Path(destination)
    require(source.resolve() != destination.resolve(), 'distinct peer roots required')
    try:
        src, result, src_index = check_peer(source, 'source', source_sha)
        dst, _, dst_index = check_peer(destination, 'destination', source_sha)
        require(src['cell'] == dst['cell'] and src['binary_sha256'] == dst['binary_sha256']
                and src['certificates_sha256']['ca.der'] == dst['certificates_sha256']['ca.der'],
                'peer workload/build/authority mismatch')
        ready = read(destination, 'ready.json')
        address, _ = validate_endpoint(ready['endpoint'], allow_zero=False)
        require(ready == read(source, 'input-readiness.json') and ready['alpn'] == 'nbsr-quic-1'
                and address == validate_endpoint(dst['bind'], allow_zero=True)[0]
                and src['endpoint'] == ready['endpoint'] and dst['endpoint'] is None,
                'readiness/endpoint mismatch')
        row = read(source, 'validated-result.json')
        require(row == json.loads((source / 'stdout').read_text().strip().splitlines()[-1])
                and validate_repeat(row), 'source result mismatch/invalid')
        cell = src['cell']
        require(all(row[k] == cell[k] for k in ('path', 'payload_bytes', 'streams'))
                and row['outstanding_per_stream'] == cell['outstanding']
                and type(row['measured_ns']) is int and row['measured_ns'] > 0
                and row['completed_operations'] == result['completed_operations'], 'source workload/count mismatch')
        gbps = 16 * cell['payload_bytes'] * row['completed_operations'] / row['measured_ns']
        require(math.isclose(result['application_gbps'], gbps, rel_tol=1e-12), 'goodput arithmetic mismatch')
        if cell['path'] == 'direct':
            require((destination / 'completion.ack').is_file(), 'missing Direct completion ACK')
        else:
            server = read(destination, 'server-result.json')
            require(server['status'] == 'PASS' and server['streams'] == cell['streams'], 'server result mismatch')
        return dict(status='PASS_FINITE_PAIR_INTEGRITY', source_sha=source_sha, cell=cell,
            source_index_sha256=src_index, destination_index_sha256=dst_index, application_gbps=gbps,
            strict_stable_capacity='NOT_PROVEN', external_hardware='NOT_PROVEN',
            observer_qualification='NOT_PROVEN', runtime_ownership_cleanup='NOT_MEASURED',
            authenticity='checksums are not signatures or remote attestation')
    except (KeyError, IndexError, TypeError, OSError) as error:
        raise ValueError('incomplete/malformed native pair: ' + str(error)) from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    args = parser.parse_args()
    print(json.dumps(analyze_pair(args.source, args.destination, source_sha=args.source_sha), indent=2))


if __name__ == '__main__':
    main()
