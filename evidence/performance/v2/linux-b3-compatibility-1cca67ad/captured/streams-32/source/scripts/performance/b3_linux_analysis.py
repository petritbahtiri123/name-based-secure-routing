"""Linux B3 memory summaries; private resident is not Windows private commit."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import statistics

from scripts.performance.b3_v2_analysis import slope

FIELDS = ('private_resident_bytes', 'rss_bytes', 'pss_bytes', 'private_hugetlb_bytes', 'fd_count', 'thread_count')


def validate(cell, *, cycles=False):
    cleanup = cell.get('cleanup', {})
    if type(cleanup.get('all_zero')) is not bool:
        raise ValueError('incomplete ownership evidence')
    if cycles and type(cleanup.get('source_cycle_all_zero')) is not bool:
        raise ValueError('incomplete cycle ownership evidence')
    identities = {}
    for row in cell['samples']:
        role = row.get('role')
        if role not in ('source', 'destination') or row.get('platform') != 'linux' or row.get('memory_basis') != 'linux_smaps_rollup':
            raise ValueError('Linux role/memory evidence required')
        processes = row.get('processes', [])
        count = row.get('process_count')
        if type(count) is not int or count < 1 or count != len(processes) or (cycles and count != 1):
            raise ValueError('invalid process count')
        identity = tuple((p.get('pid'), p.get('start_ticks')) for p in processes)
        if (any(type(pid) is not int or pid <= 0 or type(start) is not int or start < 0 for pid, start in identity)
                or len({pid for pid, _ in identity}) != count
                or role in identities and identity != identities[role]):
            raise ValueError('process identity changed')
        identities[role] = identity
        if row.get('memory_state') == 'UNAVAILABLE_EXPECTED_EXIT':
            if (cycles or role != 'source' or row.get('phase') != 'cooldown'
                    or cell.get('kind') != 'sessions' or cell.get('sessions', 0) <= 1
                    or any(row.get(field) is not None for field in FIELDS)
                    or not any(p.get('state') == 'EXITED' and p.get('exit_code') == 0
                               and p.get('memory_state') == 'UNAVAILABLE_EXPECTED_EXIT' for p in processes)
                    or any(p.get('memory_state') != 'MEASURED' and not (
                        p.get('state') == 'EXITED' and p.get('exit_code') == 0
                        and p.get('memory_state') == 'UNAVAILABLE_EXPECTED_EXIT'
                        and all(p.get(field) is None for field in FIELDS)) for p in processes)):
                raise ValueError('invalid expected post-close unavailable evidence')
            continue
        for field in FIELDS:
            values = [len(p['thread_ids']) if field == 'thread_count' else p.get(field) for p in processes]
            if (any(type(v) is not int or v < 0 for v in values)
                    or type(row.get(field)) is not int or row[field] != sum(values)):
                raise ValueError('invalid Linux metric aggregate')
    if set(identities) != {'source', 'destination'}:
        raise ValueError('missing process role')


def analyze_cycles(cell):
    validate(cell, cycles=True)
    expected = list(range(cell['cycles']))
    roles = {}
    for role in ('source', 'destination'):
        samples = [s for s in cell['samples'] if s['role'] == role]
        for phase in ('active', 'cooldown'):
            if sorted({s['cycle'] for s in samples if s['phase'] == phase}) != expected:
                raise ValueError(f'incomplete {role} {phase} series')
        if not any(s['phase'] == 'idle' and s['cycle'] == 0 for s in samples):
            raise ValueError('missing initial idle')
        points = [dict(cycle=cycle, **{f: statistics.median(s[f] for s in samples
            if s['phase'] == 'cooldown' and s['cycle'] == cycle) for f in FIELDS}) for cycle in expected]
        private = [(p['cycle'], p['private_resident_bytes']) for p in points]
        roles[role] = dict(cycle_medians=points,
            private_resident_slope_bytes_per_cycle=slope(private),
            second_half_private_resident_slope_bytes_per_cycle=slope(private[len(private)//2:]),
            private_resident_first_to_last_delta=private[-1][1] - private[0][1],
            fd_first_to_last_delta=points[-1]['fd_count'] - points[0]['fd_count'],
            thread_first_to_last_delta=points[-1]['thread_count'] - points[0]['thread_count'])
    return dict(name=cell['name'], cycles=cell['cycles'], roles=roles, memory_cause='INCONCLUSIVE',
        ownership='CLEAN' if cell['cleanup']['all_zero'] and cell['cleanup']['source_cycle_all_zero'] else 'RESOURCE_GROWTH',
        materialized_streams=cell.get('materialized_streams', False),
        limitation='Linux private resident excludes separate hugetlb; slopes do not establish leaks or allocator attribution.')


def analyze_scale(cells):
    if len({c['name'] for c in cells}) != len(cells):
        raise ValueError('duplicate repeat identity')
    for cell in cells:
        validate(cell)
        if not cell['cleanup']['all_zero']:
            raise ValueError('failed cleanup')
    results = []
    for kind in sorted({c['kind'] for c in cells}):
        selected = [c for c in cells if c['kind'] == kind]
        if len({c.get('materialized_streams', False) for c in selected}) != 1 or len({c['resource_scope'] for c in selected}) != 1:
            raise ValueError('mixed residency/resource scope')
        for role in ('source', 'destination'):
            points = []
            for count in sorted({c['active_count'] for c in selected}):
                rows = []
                for cell in selected:
                    if cell['active_count'] != count:
                        continue
                    phases = {}
                    for phase in ('idle', 'active'):
                        samples = [s for s in cell['samples'] if s['role'] == role and s['phase'] == phase]
                        if not samples:
                            raise ValueError('missing phase samples')
                        phases[phase] = {f: statistics.median(s[f] for s in samples) for f in FIELDS}
                    rows.append(dict(name=cell['name'], **phases,
                        incremental_private_resident_bytes=phases['active']['private_resident_bytes'] - phases['idle']['private_resident_bytes']))
                values = [r['active']['private_resident_bytes'] for r in rows]
                mean = statistics.fmean(values)
                cv = statistics.stdev(values) / mean * 100 if len(values) > 1 and mean else None
                points.append(dict(count=count, repeats=len(rows), active_private_resident_cv_percent=cv,
                    repeat_gate=len(rows) >= (5 if cv is not None and cv > 5 else 3),
                    active_private_resident_median=statistics.median(values),
                    active_private_resident_range=[min(values), max(values)],
                    incremental_private_resident_median=statistics.median(r['incremental_private_resident_bytes'] for r in rows), rows=rows))
            results.append(dict(kind=kind, role=role, points=points, resource_scope=selected[0]['resource_scope'],
                materialized_streams=selected[0].get('materialized_streams', False),
                derived_active_private_resident_slope_bytes_per_unit=slope([(p['count'], p['active_private_resident_median']) for p in points]),
                derived_incremental_private_resident_slope_bytes_per_unit=slope([(p['count'], p['incremental_private_resident_median']) for p in points])))
    return results


def load_input(root):
    root = Path(root).resolve()
    index = (root / 'checksums.sha256').read_bytes()
    verified = {}
    for line in index.decode().splitlines():
        expected, name = line.split('  ', 1)
        path = (root / name).resolve()
        if (not re.fullmatch(r'[0-9a-f]{64}', expected) or not path.is_relative_to(root)
                or path in verified or not path.is_file()):
            raise ValueError('invalid input checksum path/digest')
        with path.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != expected:
            raise ValueError('input checksum mismatch')
        verified[path] = expected

    def required(name):
        path = (root / name).resolve()
        if path not in verified:
            raise ValueError(f'unverified required input: {name}')
        return path

    env = json.loads(required('environment.json').read_bytes())
    build = json.loads(required('build-manifest.json').read_bytes())
    cells = json.loads(required('records.json').read_bytes())
    if env.get('platform') != 'linux' or not isinstance(cells, list) or not cells:
        raise ValueError('Linux nonempty input required')
    for key in ('source_sha', 'binary_source_sha'):
        if not re.fullmatch(r'[0-9a-f]{40}', str(env.get(key, ''))):
            raise ValueError('missing source provenance')
    binaries = env.get('binary_sha256', {})
    if set(binaries) != {'rust', 'server'} or build.get('source_sha') != env['binary_source_sha']:
        raise ValueError('inconsistent binary provenance')
    for role, name in (('rust', 'perf_rust_source'), ('server', 'wp8_interop_server')):
        digest = verified[required('binaries/' + name)]
        if binaries[role] != digest or build.get('binary_sha256', {}).get(name) != digest:
            raise ValueError('binary byte binding mismatch')
    if build.get('build_profile') != 'release' or not build.get('build_commands') or not build.get('toolchains'):
        raise ValueError('incomplete build provenance')
    controllers = {}
    for name in ('run_b3_v2.py', 'run_b3_session_lifecycle.py', 'performance/b3_linux.py',
                 'performance/b3_linux_analysis.py', 'performance/linux_resources.py', 'performance/linux_loopback.py'):
        controllers[name] = verified[required('source/scripts/' + name)]
    linux = env.get('linux_environment', {})
    stable_fields = ('topology', 'selected_cpus', 'inherited_cpus', 'kernel', 'python', 'taskset_version', 'lscpu_version')
    if any(key not in linux for key in stable_fields) or not env.get('memory_scope'):
        raise ValueError('missing platform/placement/memory binding')
    identity = dict(source_sha=env['source_sha'], binary_source_sha=env['binary_source_sha'],
        binary_sha256=binaries, controller_hashes=controllers, memory_scope=env['memory_scope'],
        platform={key: linux[key] for key in stable_fields},
        cgroup_limits={key: value for key, value in linux.get('cgroup_observed', {}).items() if not key.endswith('cpu.stat')})
    classification = env.get('classification')
    if classification not in ('DIAGNOSTIC', 'DIAGNOSTIC_BINARY_SOURCE_MISMATCH', 'MEASURED_PENDING_ANALYSIS'):
        raise ValueError('unknown input classification')
    if env['source_sha'] != env['binary_source_sha']:
        classification = 'DIAGNOSTIC_BINARY_SOURCE_MISMATCH'
    provenance = dict(root=str(root), checksums_sha256=hashlib.sha256(index).hexdigest(),
        environment_sha256=verified[required('environment.json')],
        records_sha256=verified[required('records.json')], build_manifest_sha256=verified[required('build-manifest.json')],
        classification=classification, **identity)
    return cells, identity, provenance


def analyze_roots(roots):
    if not roots or len({str(Path(root).resolve()) for root in roots}) != len(roots):
        raise ValueError('distinct input roots required')
    cells, inputs, reference = [], [], None
    for root in roots:
        rows, identity, provenance = load_input(root)
        if reference is not None and identity != reference:
            raise ValueError('incompatible controller/build/platform/placement/memory provenance')
        reference = identity
        cells.extend(rows)
        inputs.append(provenance)
    classifications = {row['classification'] for row in inputs}
    classification = ('DIAGNOSTIC_BINARY_SOURCE_MISMATCH' if 'DIAGNOSTIC_BINARY_SOURCE_MISMATCH' in classifications
                      else 'DIAGNOSTIC' if 'DIAGNOSTIC' in classifications else 'MEASURED_PENDING_ANALYSIS')
    return dict(schema='nbsr-b3-linux-analysis-v1', inputs=inputs, classification=classification,
        cycles=[analyze_cycles(c) for c in cells if c['kind'] == 'cycles'],
        scale=analyze_scale([c for c in cells if c['kind'] != 'cycles']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('roots', type=Path, nargs='+')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    document = analyze_roots(args.roots)
    with args.output.open('x', encoding='utf-8') as output:
        json.dump(document, output, indent=2)
        output.write('\n')


if __name__ == '__main__':
    main()
