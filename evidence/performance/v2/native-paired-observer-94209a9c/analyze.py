"""Matched short paced live-guard observer experiment; no capacity acceptance."""
import argparse
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from scripts.performance.linux_native_cohort import comparison_identity
from scripts.performance.linux_native_destination_observer import replay_destination
from scripts.performance.linux_native_pair import analyze_pair, verify_index

SHA = '94209a9c97b9fbf0442e0423f14f1ca23f5bfbb8'


def analyze(root):
    index = verify_index(root)
    plan = json.loads((root / 'experiment-plan.json').read_bytes())
    assert plan['qualification_gates'] == dict(absolute_median_paired_goodput_percent=5,
        absolute_median_paired_p99_percent=5, throughput_cv_max=.05)
    assert plan['pairs'] == 5 and plan['diagnostic_rate'] == [1000, 1]
    records = json.loads((root / 'records.json').read_bytes())
    assert len(records) == 10
    rows, identities, authorities, indexes = [], {}, {}, set()
    for sequence, record in enumerate(records):
        repeat = sequence // 2 + 1
        observer = (('off', 'on') if repeat % 2 else ('on', 'off'))[sequence % 2]
        enabled = observer == 'on'
        assert record['repeat'] == repeat and record['observer'] == observer
        assert record['label'] == f'{observer}-r{repeat}' and record['path'] == 'nbsr'
        assert record['status'] == 'PASS_FUNCTIONAL'
        assert record['owned_processes_absent_before_stop'] == dict(source=True, destination=True)
        cell = root / record['label']
        source = cell / 'source' / 'peer'
        checked = analyze_pair(source, cell / 'destination' / 'peer', source_sha=SHA)
        assert checked['cell'] == dict(path='nbsr', cores=1, payload_bytes=16384,
                                      streams=8, outstanding=1, diagnostic_rate=[1000, 1])
        result = json.loads((cell / 'result.json').read_bytes())
        assert result['application_gbps'] == checked['application_gbps']
        for role in ('source', 'destination'):
            current_index = checked[role + '_index_sha256']
            assert current_index not in indexes
            indexes.add(current_index)
            env = json.loads((cell / role / 'peer/environment.json').read_bytes())
            assert env['repository_sha'] == SHA and env['post_close_reports'] is True
            assert env.get('paired_live_guards', False) is enabled
            assert env.get('source_live_guard', False) is (enabled and role == 'source')
            identity = comparison_identity(env)
            certificates = identity.pop('certificates_sha256')
            identity.pop('paired_live_guards')
            identity.pop('source_live_guard')
            assert role not in identities or identities[role] == identity
            identities[role] = identity
            assert (repeat, role) not in authorities or authorities[repeat, role] == certificates
            authorities[repeat, role] = certificates
        if enabled:
            assert result['destination_live_guard'] == replay_destination(
                cell / 'destination', source, payload_bytes=16384)
            assert result['live_private_growth'] == 'PAIRED_DIAGNOSTIC'
        validated = json.loads((source / 'validated-result.json').read_bytes())
        assert validated['final']['errors'] == validated['final']['timeouts'] == 0
        assert validated['p99_latency_ns'] > 0
        rows.append(dict(repeat=repeat, observer=observer, gbps=checked['application_gbps'],
            p99_ns=validated['p99_latency_ns'], achieved_offered_ratio=validated['achieved_offered_ratio'],
            drift_failures=validated['drift_failures'],
            source_index_sha256=checked['source_index_sha256'],
            destination_index_sha256=checked['destination_index_sha256']))
    changes = []
    for offset in range(0, 10, 2):
        pair = {row['observer']: row for row in rows[offset:offset + 2]}
        changes.append(dict(repeat=pair['off']['repeat'], **{
            field + '_percent': 100 * (pair['on'][field] / pair['off'][field] - 1)
            for field in ('gbps', 'p99_ns')}))
    medians = {field: statistics.median(row[field] for row in changes)
               for field in ('gbps_percent', 'p99_ns_percent')}
    cv, latency_cv = {}, {}
    for observer in ('off', 'on'):
        rates = [row['gbps'] for row in rows if row['observer'] == observer]
        cv[observer] = statistics.stdev(rates) / statistics.mean(rates)
        latencies = [row['p99_ns'] for row in rows if row['observer'] == observer]
        latency_cv[observer] = statistics.stdev(latencies) / statistics.mean(latencies)
    effect_pass = all(abs(value) <= 5 for value in medians.values())
    dispersion_pass = all(value <= .05 for value in cv.values())
    return dict(source_sha=SHA, raw_index_sha256=index, rows=rows,
        paired_changes=changes, median_changes_percent=medians, throughput_cv=cv,
        p99_window_summary_cv=latency_cv,
        effect_gate_pass=effect_pass, dispersion_gate_pass=dispersion_pass,
        classification='PASS_SCOPED_OBSERVER_GATE' if effect_pass and dispersion_pass else 'REJECTED_OBSERVER_GATE',
        scope='this short paced NBSR workload only; post-close reports enabled in both arms',
        limitations='no higher-load, unpaced, long-run, stable-capacity or physical-core qualification; five-pair estimate is not a confidence bound',
        authority_scope='fresh per repeat; exact within each observer pair',
        latency_scope='median of steady-window p99 values, not pooled p99',
        coverage='all ten declared attempts; no undisclosed-attempt detection or remote attestation')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    print(json.dumps(analyze(parser.parse_args().root), indent=2))
