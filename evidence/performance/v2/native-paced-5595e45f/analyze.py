"""Independent short paced native integration results, never soak/capacity."""
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path.cwd()))
from scripts.performance.linux_native_finite_run import check_endpoint
from scripts.performance.linux_native_pair import analyze_pair, read, verify_index

ROOT = Path('C:/NBSR-build/native-paced-5595e45f')
SHA = Path('C:/NBSR-build/linux-current-5595e45f/source-sha.txt').read_text().strip()
rows = read(ROOT, 'records.json')
assert [row['label'] for row in rows] == [f'{path}-r{repeat}' for repeat in range(1, 6)
    for path in (('direct', 'nbsr') if repeat % 2 else ('nbsr', 'direct'))]
cells = []
for row in rows:
    root = ROOT / row['label']
    index = verify_index(root)
    assert row['owned_processes_absent_before_stop'] == dict(source=True, destination=True)
    config = read(ROOT, row['label'] + '-config.json')
    assert config['source_sha'] == SHA and config['diagnostic_rate'] == [1000, 1]
    assert config['post_close_reports'] is True
    entry = dict(label=row['label'], path=row['path'], controller_status=row['status'], index_sha256=index)
    if row['status'] == 'PASS_FUNCTIONAL':
        pair = analyze_pair(root / 'source/peer', root / 'destination/peer', source_sha=SHA)
        assert pair['workload_mode'] == 'PACED_DIAGNOSTIC'
        assert pair['cell']['diagnostic_rate'] == [1000, 1]
        assert all(value['exit_code'] == 0 and not value['local_relay_forced']
                   for value in read(root, 'cleanup.json').values())
        for role in ('source', 'destination'):
            check_endpoint(root / role, role)
            assert (ROOT / (row['label'] + '-' + role + '-owned-pid-absent.txt')).read_text().strip() == 'OWNED_PID_ABSENT'
        summary = read(root / 'source/peer', 'validated-result.json')
        entry.update(peer=pair, source=summary)
    else:
        entry['failure'] = read(root, 'failure.json')
    cells.append(entry)
summary = {}
for path in ('direct', 'nbsr'):
    selected = [cell for cell in cells if cell['path'] == path]
    valid = [cell for cell in selected if cell['controller_status'] == 'PASS_FUNCTIONAL']
    result = dict(functional_passes=len(valid), failures=len(selected)-len(valid))
    if valid:
        rates = [cell['peer']['application_gbps'] for cell in valid]
        result.update(median_gbps=statistics.median(rates),
            cv_percent=100 * statistics.stdev(rates) / statistics.mean(rates) if len(rates) > 1 else None,
            achieved_offered_ratios=[cell['source']['achieved_offered_ratio'] for cell in valid],
            cells_with_drift_failure=sum(bool(cell['source']['drift_failures']) for cell in valid),
            median_cell_window_quantiles_ns={q: statistics.median(cell['source'][q+'_latency_ns'] for cell in valid)
                                             for q in ('p50', 'p95', 'p99')},
            errors=sum(cell['source']['final']['errors'] for cell in valid),
            timeouts=sum(cell['source']['final']['timeouts'] for cell in valid))
    summary[path] = result
report = dict(source_sha=SHA, summary=summary, cells=cells,
              classification='SHORT_PACED_DIAGNOSTIC', strict_stable='NOT_ESTABLISHED',
              near_ceiling='NOT_ESTABLISHED', soak='NOT_RUN', live_private_growth='NOT_MEASURED',
              observer_qualification='REJECTED_IN_SEPARATE_AC40740C_COHORT', hardware_ceiling='NOT_PROVEN')
(Path(__file__).resolve().parent / 'analysis.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(summary, indent=2))
