"""Revalidate native post-close cohort; never qualify timing as capacity."""
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path.cwd()))
from scripts.performance.linux_native_finite_run import check_endpoint
from scripts.performance.linux_native_pair import analyze_pair, read, verify_index

ROOT = Path('C:/NBSR-build/native-post-close-ac40740c')
OUT = Path(__file__).resolve().parent
SHA = Path('C:/NBSR-build/linux-current-ac40740c/source-sha.txt').read_text().strip()
rows = read(ROOT, 'records.json')
expected = [f'{path}-r{repeat}' for repeat in range(1, 6)
            for path in (('direct', 'nbsr') if repeat % 2 else ('nbsr', 'direct'))]
assert [row['label'] for row in rows] == expected
cells = []
for row in rows:
    cell = ROOT / row['label']
    assert row['status'] == 'PASS_FUNCTIONAL'
    assert row['owned_processes_absent_before_stop'] == dict(source=True, destination=True)
    index = verify_index(cell)
    config = read(ROOT, row['label'] + '-config.json')
    assert config['post_close_reports'] is True and config['source_sha'] == SHA
    assert all(value['exit_code'] == 0 and not value['local_relay_forced']
               for value in read(cell, 'cleanup.json').values())
    pair = analyze_pair(cell / 'source/peer', cell / 'destination/peer', source_sha=SHA)
    expected_scope = 'ALL_11_ZERO' if row['path'] == 'nbsr' else 'NOT_APPLICABLE_DIRECT'
    assert pair['runtime_ownership_cleanup'] == expected_scope
    for role in ('source', 'destination'):
        check_endpoint(cell / role, role)
        assert read(cell / role / 'peer', 'environment.json')['post_close_reports'] is True
        assert read(cell / role / 'peer', 'result.json')['runtime_ownership_cleanup'] == expected_scope
        assert (ROOT / (row['label'] + '-' + role + '-owned-pid-absent.txt')).read_text().strip() == 'OWNED_PID_ABSENT'
    source = read(cell / 'source/peer', 'validated-result.json')
    cells.append(dict(label=row['label'], path=row['path'], index_sha256=index,
                      peer=pair, runtime_ownership=expected_scope,
                      latency_ns={q: source[q + '_latency_ns'] for q in ('p50', 'p95', 'p99')}))
summary = {}
for path in ('direct', 'nbsr'):
    selected = [cell for cell in cells if cell['path'] == path]
    rates = [cell['peer']['application_gbps'] for cell in selected]
    summary[path] = dict(passes=len(selected), median_gbps=statistics.median(rates),
                         cv_percent=100 * statistics.stdev(rates) / statistics.mean(rates),
                         median_cell_latency_ns={q: statistics.median(cell['latency_ns'][q] for cell in selected)
                                                 for q in ('p50', 'p95', 'p99')})
report = dict(source_sha=SHA, cells=cells, summary=summary, timing='DIAGNOSTIC_ONLY',
              observer_qualification='NOT_ESTABLISHED', strict_stable='NOT_ESTABLISHED',
              soak='NOT_RUN', production_changes='NONE', hardware_ceiling='NOT_PROVEN')
(OUT / 'analysis.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(summary, indent=2))
