"""Independently replay both Go/Rust lifecycle cohorts without pooling them."""
from pathlib import Path
import hashlib
import json
import statistics as stats
import sys


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def cv(values):
    return stats.stdev(values) / stats.mean(values) if len(values) > 1 else None


def slope(values):
    n = len(values)
    x = list(range(n))
    xm, ym = stats.mean(x), stats.mean(values)
    return sum((a-xm)*(b-ym) for a, b in zip(x, values)) / sum((a-xm)**2 for a in x)


def cohort(root, expected_sha, completion):
    policy, build, attempts = (read(root / name) for name in ('policy.json', 'build-manifest.json', 'attempts.json'))
    assert policy['source_sha'].startswith(expected_sha) and policy['source_sha'] == build['source_sha']
    assert build['profile'] == 'release' and policy.get('destination_completion', False) is completion
    assert (policy['idle_seconds'], policy['active_seconds'], policy['cooldown_seconds'], policy['cadence']) == (2, 2, 2, 0.5)
    for name, digest in build['binaries'].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest
    groups = {}
    for row in attempts:
        spec = row['spec']
        assert spec['sessions'] == 1 and spec.get('destination_completion', False) is completion
        assert len(row['owned_processes']) == 2 and all(p['returncode'] is not None for p in row['owned_processes'])
        group = groups.setdefault(row['shape'], [])
        record = {'repeat': row['repeat'], 'status': row['status']}
        group.append(record)
        folder = root / 'raw/go-rust' / spec['name']
        if row['status'] != 'PASS_SCOPED':
            assert (folder / 'failure.json').is_file()
            record['error'] = read(folder / 'failure.json')['error']
            continue
        assert all(p['returncode'] == 0 for p in row['owned_processes'])
        cell = read(folder / 'cell.json')
        expected = spec['cycles'] * spec['channels'] * spec['streams']
        source = read(folder / 'source-0.stdout')
        assert cell['client_results'] == [source] and source['status'] == 'PASS'
        assert len(source['samples']) == expected == row['completed_operations']
        assert all(s['success'] is True and s['bytes_transmitted'] == s['bytes_received'] == 1024 for s in source['samples'])
        destination = read(folder / 'server-result.json')
        assert len(destination['samples']) == expected
        cleanup = cell['cleanup']
        assert cleanup['all_zero'] and cleanup['source_processes_exited'] and cleanup['destination_exited']
        assert cleanup['counter_scope'] == 'historical-go-destination-8-fields'
        assert len(cleanup['counters']) == 8 and all(type(v) is int and v == 0 for v in cleanup['counters'].values())
        if completion:
            assert cell['destination_completion_records'] == list(range(spec['cycles']))
            assert cell['completion_environment'] == {'NBSR_PERF_LIFECYCLE_COMPLETION_MARKERS': '1'}
        record.update(completed_operations=expected, roles={})
        for role in ('source', 'destination'):
            samples = [s for s in cell['samples'] if s['role'] == role]
            phase = {p: stats.median(s['private_bytes'] for s in samples if s['phase'] == p) for p in ('idle', 'active', 'cooldown') if any(s['phase'] == p for s in samples)}
            assert phase['active'] == row['active_private_bytes'][role]
            role_result = {'phase_private_bytes': phase, 'handles_range': [min(s['handle_count'] for s in samples), max(s['handle_count'] for s in samples)], 'threads_range': [min(s['thread_count'] for s in samples), max(s['thread_count'] for s in samples)]}
            if spec['cycles'] == 50:
                cool = [s for s in samples if s['phase'] == 'cooldown']
                indices = sorted({s['cycle'] for s in cool})
                values = [stats.median(s['private_bytes'] for s in cool if s['cycle'] == i) for i in indices]
                assert indices == list(range(49 if role == 'source' else 50))
                role_result['cooldown'] = {'observed_cycles': len(values), 'first_private_bytes': values[0], 'last_private_bytes': values[-1], 'last10_range_bytes': max(values[-10:])-min(values[-10:]), 'last10_slope_bytes_per_cycle': slope(values[-10:]), 'second_half_range_bytes': max(values[len(values)//2:])-min(values[len(values)//2:])}
            record['roles'][role] = role_result
        runtime = [json.loads(line) for line in (folder / 'go-runtime-0.ndjson').read_text().splitlines()]
        record['go_runtime'] = {field: [min(r[field] for r in runtime), max(r[field] for r in runtime)] for field in ('heap_alloc_bytes', 'heap_sys_bytes', 'goroutines', 'num_gc', 'mallocs', 'frees', 'total_alloc_bytes')}
    result = {}
    for shape, rows in groups.items():
        assert [r['repeat'] for r in rows] == list(range(1, len(rows)+1))
        passed = [r for r in rows if r['status'] == 'PASS_SCOPED']
        summary = {'attempts': len(rows), 'passed': len(passed), 'rows': rows}
        if len(passed) == len(rows):
            first = {role: cv([r['roles'][role]['phase_private_bytes']['active'] for r in rows[:3]]) for role in ('source', 'destination')}
            required = 5 if max(first.values()) > .05 else 3
            assert len(rows) == required
            decision = read(root / (shape+'-repeat-decision.json'))
            assert decision['repeats_required'] == required and decision['first_three_cv'] == first
            summary['active_private_cv'] = {role: cv([r['roles'][role]['phase_private_bytes']['active'] for r in rows]) for role in ('source', 'destination')}
        else:
            assert len(rows) == 3
        result[shape] = summary
    return {'source_sha': build['source_sha'], 'completion_gate': completion, 'attempts': len(attempts), 'passed': sum(r['status']=='PASS_SCOPED' for r in attempts), 'completed_operations_in_accepted_cells': sum(r.get('completed_operations', 0) for r in attempts), 'shapes': result, 'scope': 'DIAGNOSTIC: no source ownership/observer qualification/isolated resource cost/soak claim'}


if __name__ == '__main__':
    base = Path(sys.argv[1]) if len(sys.argv)>1 else Path('C:/NBSR-build')
    print(json.dumps({'baseline': cohort(base/'go-b3-dfc22f2c', 'dfc22f2c', False), 'corrected': cohort(base/'go-b3-97e0ca06', '97e0ca06', True)}, indent=2))
