"""Read-only finite native comparison integrity; never a capacity acceptance."""

import argparse
import json
from pathlib import Path
import statistics

from scripts.performance.linux_b5_ceiling import require
from scripts.performance.linux_loopback import digest
from scripts.performance.linux_native_pair import analyze_pair


def cv(values):
    return statistics.stdev(values) / statistics.mean(values)


def comparison_identity(env):
    linux = env['linux_environment']
    cgroup = linux.get('cgroup_observed', {})
    return dict(binary_sha256=env['binary_sha256'], certificates_sha256=env['certificates_sha256'],
        live_socket_observer=env.get('live_socket_observer', False),
        post_close_reports=env.get('post_close_reports', False),
        source_live_guard=env.get('source_live_guard', False),
        phase_observer=env.get('phase_control_endpoint') is not None,
        bind=env['bind'], source_sha256=env.get('source_sha256'),
        placement={k: linux.get(k) for k in ('kernel', 'python', 'topology', 'selected_cpus',
                                           'inherited_cpus', 'taskset_version', 'lscpu_version')},
        cgroup={k: cgroup.get('/sys/fs/cgroup/' + k)
                for k in ('cpu.max', 'cpuset.cpus.effective', 'memory.max', 'pids.max')})


def analyze_cohort(manifest_path, *, source_sha):
    manifest_path = Path(manifest_path)
    try:
        manifest = json.loads(manifest_path.read_bytes())
        require(set(manifest) == {'schema', 'attempts'} and manifest['schema'] == 'nbsr-native-cohort-v1',
                'unknown cohort schema')
        entries = manifest['attempts']
        require(type(entries) is list and len(entries) in (6, 10), 'three or five complete pairs required')
        rows, seen_roots, seen_indices, identities = [], set(), set(), {}
        shape = None
        for sequence, entry in enumerate(entries):
            require(set(entry) == {'source', 'destination', 'path', 'repeat'}, 'invalid attempt fields')
            repeat = sequence // 2 + 1
            order = ('direct', 'nbsr') if repeat % 2 else ('nbsr', 'direct')
            require(type(entry['repeat']) is int and entry['repeat'] == repeat
                    and entry['path'] == order[sequence % 2], 'declared order/repeat is not counterbalanced')
            roots = {}
            for role in ('source', 'destination'):
                require(type(entry[role]) is str and bool(entry[role]), 'missing peer directory')
                root = (manifest_path.parent / entry[role]).resolve()
                require(root not in seen_roots, 'duplicate peer directory')
                seen_roots.add(root)
                roots[role] = root
            row = analyze_pair(roots['source'], roots['destination'], source_sha=source_sha)
            require(row['cell']['path'] == entry['path'], 'declared path differs from retained workload')
            current_shape = {k: v for k, v in row['cell'].items() if k != 'path'}
            shape = current_shape if shape is None else shape
            require(shape == current_shape, 'cohort workload/CPU shape mismatch')
            for role, root in roots.items():
                index = row[role + '_index_sha256']
                require(index not in seen_indices, 'duplicate evidence bytes reused as a repeat')
                seen_indices.add(index)
                env = json.loads((root / 'environment.json').read_bytes())
                current = comparison_identity(env)
                require(role not in identities or identities[role] == current,
                        'cohort build/authority/placement mismatch')
                identities[role] = current
            rows.append(dict(sequence=sequence + 1, repeat=repeat, **row))
        values = {mode: [r['application_gbps'] for r in rows if r['cell']['path'] == mode]
                  for mode in ('direct', 'nbsr')}
        first = {mode: cv(v[:3]) for mode, v in values.items()}
        repeats = len(entries) // 2
        require('operations_per_stream' not in shape or repeats == 5,
                'fixed-work packet comparison requires five complete pairs')
        require(repeats == 5 or all(value <= .05 for value in first.values()),
                'first-three goodput dispersion requires five repeats of both paths')
        final = {mode: cv(v) for mode, v in values.items()}
        return dict(status='PASS_FINITE_COHORT_INTEGRITY', source_sha=source_sha,
            manifest_sha256=digest(manifest_path), shape=shape, repeats_per_path=repeats,
            attempts=rows, first_three_cv=first, final_cv=final,
            dispersion_unresolved=any(v > .05 for v in final.values()),
            median_application_gbps={mode: statistics.median(v) for mode, v in values.items()},
            paired_goodput_delta_percent=[100 * (n / d - 1) for d, n in zip(values['direct'], values['nbsr'])],
            ordering='declared counterbalanced schedule; not independently timestamp-verified',
            coverage='all listed attempts; cannot detect undisclosed attempts outside the manifest',
            strict_stable_capacity='NOT_PROVEN', external_hardware='NOT_PROVEN',
            observer_qualification='NOT_PROVEN', runtime_ownership_cleanup='NOT_MEASURED',
            authenticity='checksums are not signatures or remote attestation')
    except (KeyError, IndexError, TypeError, OSError, json.JSONDecodeError) as error:
        raise ValueError('incomplete/malformed native cohort: ' + str(error)) from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    args = parser.parse_args()
    print(json.dumps(analyze_cohort(args.manifest, source_sha=args.source_sha), indent=2))


if __name__ == '__main__':
    main()
