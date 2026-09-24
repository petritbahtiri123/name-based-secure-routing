"""Read-only matched native post-close observer qualification, not capacity."""

import argparse
import json
from pathlib import Path
import statistics

from scripts.performance.linux_b5_ceiling import identity, require
from scripts.performance.linux_b5_reference import finish_record
from scripts.performance.linux_loopback import digest
from scripts.performance.linux_native_lifecycle_control import decode_object
from scripts.performance.linux_native_pair import analyze_pair, read


def placement_identity(env):
    return dict(linux=identity(env['linux_environment']), bind=env['bind'],
                binary_sha256=env['binary_sha256'])


def qualify(manifest_path, *, source_sha):
    path = Path(manifest_path)
    original_hash = digest(path)
    try:
        with path.open('rb') as stream:
            manifest = decode_object(stream.read(65537))
        require(set(manifest) == {'schema', 'attempts', 'interruptions'}
                and manifest['schema'] == 'nbsr-native-observer-v1', 'invalid observer manifest')
        attempts, interruptions = manifest['attempts'], manifest['interruptions']
        require(type(attempts) is list and 10 <= len(attempts) <= 20 and len(attempts) % 2 == 0,
                'five to ten complete observer pairs required')
        require(type(interruptions) is list and len(interruptions) <= 20
                and all(type(value) is str and 0 < len(value) <= 1024 for value in interruptions),
                'invalid interruption declarations')
        rows, seen_roots, seen_indexes, stable_identities = [], set(), set(), {}
        shape = None
        for sequence, entry in enumerate(attempts):
            require(type(entry) is dict and set(entry) == {'repeat', 'observer', 'source', 'destination'},
                    'invalid observer attempt')
            repeat = sequence // 2 + 1
            order = ('off', 'on') if repeat % 2 else ('on', 'off')
            require(type(entry['repeat']) is int and entry['repeat'] == repeat
                    and entry['observer'] == order[sequence % 2], 'observer repeat/order mismatch')
            roots = {}
            for role in ('source', 'destination'):
                require(type(entry[role]) is str and entry[role], 'missing peer path')
                root = (path.parent / entry[role]).resolve()
                require(root not in seen_roots, 'duplicate observer peer root')
                seen_roots.add(root)
                roots[role] = root
            pair = analyze_pair(roots['source'], roots['destination'], source_sha=source_sha)
            cell = pair['cell']
            require(set(cell) == {'path', 'cores', 'payload_bytes', 'streams', 'outstanding'}
                    and cell['path'] == 'nbsr' and cell['cores'] == 1,
                    'only unpaced single-core NBSR observer workload supported')
            shape = cell if shape is None else shape
            require(cell == shape, 'observer workload mismatch')
            certs = {}
            for role, root in roots.items():
                index = pair[role + '_index_sha256']
                require(index not in seen_indexes, 'duplicate observer evidence bytes')
                seen_indexes.add(index)
                env = read(root, 'environment.json')
                require(env.get('post_close_reports', False) is (entry['observer'] == 'on')
                        and env.get('live_socket_observer', False) is False
                        and env.get('phase_control_endpoint') is None, 'observer mode mismatch')
                current = placement_identity(env)
                require(role not in stable_identities or stable_identities[role] == current,
                        'observer build/placement mismatch')
                stable_identities[role] = current
                certs[role] = env['certificates_sha256']
            record = read(roots['source'], 'validated-result.json')
            finish_record(cell, repeat, record, cleanup_pass=True)
            rows.append(dict(repeat=repeat, observer=entry['observer'],
                gbps=pair['application_gbps'], p99_ns=record['p99_latency_ns'],
                source_index_sha256=pair['source_index_sha256'],
                destination_index_sha256=pair['destination_index_sha256'], certificates=certs))
        changes = []
        for offset in range(0, len(rows), 2):
            pair = {row['observer']: row for row in rows[offset:offset+2]}
            off, on = pair['off'], pair['on']
            require(off['certificates'] == on['certificates'], 'paired authority mismatch')
            changes.append(dict(repeat=off['repeat'],
                goodput_percent=100 * (on['gbps'] / off['gbps'] - 1),
                p99_percent=100 * (on['p99_ns'] / off['p99_ns'] - 1)))
        medians = {key: statistics.median(row[key] for row in changes)
                   for key in ('goodput_percent', 'p99_percent')}
        cvs = {}
        for mode in ('off', 'on'):
            rates = [row['gbps'] for row in rows if row['observer'] == mode]
            cvs[mode] = statistics.stdev(rates) / statistics.mean(rates)
        effects_pass = all(abs(value) <= 5 for value in medians.values())
        dispersion_pass = all(value <= .05 for value in cvs.values())
        require(digest(path) == original_hash, 'manifest changed during validation')
        return dict(schema='nbsr-native-observer-qualification-v1', source_sha=source_sha,
            manifest_sha256=original_hash, shape=shape, identities=stable_identities,
            qualified=effects_pass and dispersion_pass and not interruptions,
            effect_gate_pass=effects_pass, dispersion_gate_pass=dispersion_pass,
            interruptions=interruptions, pairs=len(changes), attempts=rows,
            paired_changes=changes, median_changes_percent=medians, throughput_cv=cvs,
            strict_stable_capacity='NOT_PROVEN', external_hardware='NOT_PROVEN',
            coverage='all listed attempts; undeclared attempts and interruptions cannot be detected',
            ordering='declared counterbalanced order; not independently timestamp-attested',
            authenticity='checksums and observed placement are not remote host attestation')
    except (KeyError, IndexError, TypeError, OSError, ZeroDivisionError) as error:
        raise ValueError('incomplete/malformed observer evidence: ' + str(error)) from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    args = parser.parse_args()
    result = qualify(args.manifest, source_sha=args.source_sha)
    print(json.dumps(result, indent=2))
    if not result['qualified']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
