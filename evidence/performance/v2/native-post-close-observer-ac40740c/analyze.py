"""Five predeclared paired observer controls; retain failed qualification."""
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path.cwd()))
from scripts.performance.linux_native_pair import analyze_pair, read, verify_index

ROOT = Path('C:/NBSR-build/native-post-close-observer-ac40740c')
SHA = Path('C:/NBSR-build/linux-current-ac40740c/source-sha.txt').read_text().strip()
rows = read(ROOT, 'records.json')
assert [row['label'] for row in rows] == [f'{mode}-r{repeat}' for repeat in range(1, 7)
    for mode in (('off', 'on') if repeat % 2 else ('on', 'off'))]
cells = {}
for row in rows:
    label, mode = row['label'], row['observer']
    assert row['status'] == 'PASS_FUNCTIONAL'
    assert row['owned_processes_absent_before_stop'] == dict(source=True, destination=True)
    root = ROOT / label
    index = verify_index(root)
    result = analyze_pair(root / 'source/peer', root / 'destination/peer', source_sha=SHA)
    assert read(ROOT, label + '-config.json')['post_close_reports'] is (mode == 'on')
    assert all(value['exit_code'] == 0 and not value['local_relay_forced']
               for value in read(root, 'cleanup.json').values())
    identities, resources = {}, {}
    for role in ('source', 'destination'):
        env = read(root / role / 'peer', 'environment.json')
        assert env['post_close_reports'] is (mode == 'on')
        assert (ROOT / (label + '-' + role + '-owned-pid-absent.txt')).read_text().strip() == 'OWNED_PID_ABSENT'
        identities[role] = {key: env[key] for key in ('cell', 'repository_sha', 'binary_sha256',
            'certificates_sha256', 'linux_environment', 'warmup_seconds', 'duration_seconds')}
        samples = [json.loads(line) for line in (root / role / 'peer/resources.ndjson').read_text().splitlines()]
        elapsed = samples[-1]['timestamp_ns'] - samples[0]['timestamp_ns']
        assert elapsed > 0
        resources[role] = dict(sample_interval_cpu_fraction=(samples[-1]['cpu_ns'] - samples[0]['cpu_ns']) / elapsed,
                               peak_rss_bytes=max(sample['rss_bytes'] for sample in samples),
                               peak_threads=max(len(sample['thread_ids']) for sample in samples),
                               peak_fds=max(sample['fd_count'] for sample in samples if type(sample['fd_count']) is int),
                               scope='peer sample interval including startup/warmup/drain; not steady CPU ns/op')
    source = read(root / 'source/peer', 'validated-result.json')
    cells[label] = dict(gbps=result['application_gbps'], p99_ns=source['p99_latency_ns'],
                       index_sha256=index, identities=identities, resources=resources,
                       runtime_ownership=result['runtime_ownership_cleanup'])
pairs = []
for repeat in range(1, 7):
    off, on = (cells[f'{mode}-r{repeat}'] for mode in ('off', 'on'))
    # Volatile environment fields are recorded; compare the fixed workload,
    # binaries, certificates and the actual selected CPU pool explicitly.
    for role in ('source', 'destination'):
        a, b = off['identities'][role], on['identities'][role]
        for key in ('cell', 'repository_sha', 'binary_sha256', 'certificates_sha256', 'warmup_seconds', 'duration_seconds'):
            assert a[key] == b[key], (repeat, role, key)
        assert a['linux_environment']['selected_cpus'] == b['linux_environment']['selected_cpus'] == [0]
    pairs.append(dict(repeat=repeat, goodput_change_percent=100 * (on['gbps'] / off['gbps'] - 1),
                      p99_change_percent=100 * (on['p99_ns'] / off['p99_ns'] - 1)))
cv = {}
for mode in ('off', 'on'):
    rates = [cells[f'{mode}-r{repeat}']['gbps'] for repeat in range(1, 7)]
    cv[mode] = 100 * statistics.stdev(rates) / statistics.mean(rates)
medians = {key: statistics.median(pair[key] for pair in pairs)
           for key in ('goodput_change_percent', 'p99_change_percent')}
interruption = read(ROOT, 'interruption.json') if (ROOT / 'interruption.json').exists() else None
uninterrupted = [pair for pair in pairs if not interruption
                 or pair['repeat'] not in interruption['paired_comparison_affected']]
qualified_medians = {key: statistics.median(pair[key] for pair in uninterrupted) for key in medians}
qualified_cv = {}
for mode in ('off', 'on'):
    rates = [cells[f"{mode}-r{pair['repeat']}"]['gbps'] for pair in uninterrupted]
    qualified_cv[mode] = 100 * statistics.stdev(rates) / statistics.mean(rates)
effect_pass = all(abs(value) <= 5 for value in qualified_medians.values())
variance_pass = all(value <= 5 for value in qualified_cv.values())
report = dict(source_sha=SHA, cells=cells, pairs=pairs, median_paired_changes=medians,
              throughput_cv_percent=cv, effect_gate_pass=effect_pass, variance_gate_pass=variance_pass,
              uninterrupted_median_paired_changes=qualified_medians, uninterrupted_cv_percent=qualified_cv,
              interruption=interruption, uninterrupted_pairs=len(uninterrupted),
              qualification_pass=effect_pass and variance_pass and len(uninterrupted) == 5,
              classification=('INCONCLUSIVE_INTERRUPTED_COHORT' if len(uninterrupted) != 5 else
                              'REJECTED_OBSERVER_GATE' if not effect_pass else
                              'INCONCLUSIVE_HOST_VARIANCE' if not variance_pass else 'PASS_OBSERVER_GATE'),
              strict_stable='NOT_ESTABLISHED', causal_production_bottleneck='NOT_PROVEN')
(Path(__file__).resolve().parent / 'analysis.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({key: value for key, value in report.items() if key not in ('cells', 'pairs')}, indent=2))
