"""Linux B3 memory summaries; private resident is not Windows private commit."""
import argparse
import json
from pathlib import Path
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('roots', type=Path, nargs='+')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    cells = [c for root in args.roots for c in json.loads((root / 'records.json').read_text())]
    document = dict(schema='nbsr-b3-linux-analysis-v1', inputs=list(map(str, args.roots)),
        cycles=[analyze_cycles(c) for c in cells if c['kind'] == 'cycles'],
        scale=analyze_scale([c for c in cells if c['kind'] != 'cycles']))
    with args.output.open('x', encoding='utf-8') as output:
        json.dump(document, output, indent=2)
        output.write('\n')


if __name__ == '__main__':
    main()
