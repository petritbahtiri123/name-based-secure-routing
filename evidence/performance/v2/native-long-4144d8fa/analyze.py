"""Read all retained paired-observed cells; no stability or observer qualification."""
import argparse
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from scripts.performance.linux_native_cohort import comparison_identity
from scripts.performance.linux_native_pair import analyze_pair, verify_index
from scripts.performance.linux_native_destination_observer import replay_destination

SHA = '4144d8fa226b1cbee3c8e2227d8d357b73584434'


def analyze(root):
    index = verify_index(root)
    records = json.loads((root / 'records.json').read_bytes())
    assert len(records) in (6, 10)
    rows, identities, pair_authorities, checked_pairs = [], {}, {}, []
    for sequence, record in enumerate(records):
        repeat = sequence // 2 + 1
        order = ('direct', 'nbsr') if repeat % 2 else ('nbsr', 'direct')
        assert record['repeat'] == repeat and record['path'] == order[sequence % 2]
        assert record['label'] == record['path'] + '-r' + str(repeat)
        assert record['status'] == 'PASS_FUNCTIONAL'
        assert record['owned_processes_absent_before_stop'] == dict(source=True, destination=True)
        peer = root / record['label'] / 'source' / 'peer'
        pair = json.loads((root / record['label'] / 'result.json').read_bytes())
        checked = analyze_pair(peer, root / record['label'] / 'destination' / 'peer', source_sha=SHA)
        assert checked['cell'] == dict(path=record['path'], cores=1, payload_bytes=16384,
                                       streams=8, outstanding=1, diagnostic_rate=[1000, 1], diagnostic_seconds=60)
        assert all(pair[key] == value for key, value in checked.items() if key not in ('status', 'live_private_growth', 'destination_private_growth'))
        checked_pairs.append(checked)
        for role in ('source', 'destination'):
            env = json.loads((root / record['label'] / role / 'peer/environment.json').read_bytes())
            current = comparison_identity(env)
            certs = current.pop('certificates_sha256')
            assert role not in identities or identities[role] == current
            identities[role] = current
            assert (repeat, role) not in pair_authorities or pair_authorities[repeat, role] == certs
            pair_authorities[repeat, role] = certs
        destination_guard = replay_destination(root / record['label'] / 'destination', peer, payload_bytes=16384, diagnostic_seconds=60)
        assert pair['destination_live_guard'] == destination_guard
        assert pair['live_private_growth'] == 'PAIRED_DIAGNOSTIC'
        assert destination_guard['resource_series_available'] and destination_guard['final_received']
        guard = pair['source_live_guard']
        source = json.loads((peer / 'validated-result.json').read_bytes())
        assert source['final']['errors'] == source['final']['timeouts'] == 0
        assert guard['final_received'] and guard['resource_series_available']
        assert guard['latency_comparison_available']
        resources = [row['value'] for row in map(json.loads, (peer / 'live-events.ndjson').read_text().splitlines())
                     if row['kind'] == 'resource']
        live = [row for row in resources if row['private_resident_bytes'] is not None]
        lifetime = (resources[-1]['cpu_ns'] - resources[0]['cpu_ns']) / (
            resources[-1]['timestamp_ns'] - resources[0]['timestamp_ns'])
        rows.append(dict(label=record['label'], path=record['path'],
            gbps=pair['application_gbps'], achieved_offered_ratio=source['achieved_offered_ratio'],
            latency={key: source[key] for key in ('p50_latency_ns', 'p95_latency_ns', 'p99_latency_ns')},
            source_guard=guard, destination_guard=destination_guard, source_private_resident_peak_bytes=max(row['private_resident_bytes'] for row in live),
            source_max_fd_count=max(row['fd_count'] for row in live if row['fd_count'] is not None),
            source_max_threads=max(len(row['thread_ids']) for row in live),
            source_sampled_lifetime_effective_cores=lifetime,
            source_cleanup=pair['runtime_ownership_cleanup']))
    assert len({row[role + '_index_sha256'] for row in checked_pairs
                for role in ('source', 'destination')}) == len(records)*2
    summary = {}
    first_cvs = {}
    for mode in ('direct', 'nbsr'):
        selected = [row for row in rows if row['path'] == mode]
        rates = [row['gbps'] for row in selected]
        first_cvs[mode] = statistics.stdev(rates[:3])/statistics.mean(rates[:3])
        assert len(records) == 10 or first_cvs[mode] <= .05
        summary[mode] = dict(repeats=len(selected), median_gbps=statistics.median(rates),
            throughput_cv=statistics.stdev(rates)/statistics.mean(rates),
            achieved_offered_ratio_range=[min(row['achieved_offered_ratio'] for row in selected),
                                          max(row['achieved_offered_ratio'] for row in selected)],
            p99_drift_failure_runs=sum(any(f['reason'] == 'p99' for f in row['source_guard']['failures']) for row in selected),
            private_growth_failure_runs=sum(any(f['reason'] == 'private_growth' for f in row['source_guard']['failures']) for row in selected),
            destination_private_growth_failure_runs=sum(any(f['reason'] == 'private_growth' for f in row['destination_guard']['failures']) for row in selected),
            median_window_quantiles={key: statistics.median(row['latency'][key] for row in selected)
                                     for key in ('p50_latency_ns', 'p95_latency_ns', 'p99_latency_ns')},
            source_peak_private_bytes_range=[min(row['source_private_resident_peak_bytes'] for row in selected),
                                             max(row['source_private_resident_peak_bytes'] for row in selected)])
    return dict(source_sha=SHA, raw_index_sha256=index, classification='DIAGNOSTIC_ONLY',
        workload='1000 offered ops/s, 16KiB, eight streams, depth one, 3s warmup/60s issue, guest CPU0 per peer',
        observer_qualification='NOT_ESTABLISHED', destination_private_growth='SHORT_DIAGNOSTIC',
        sustained_capacity='NOT_ESTABLISHED', external_hardware='NOT_PROVEN', summary=summary, rows=rows,
        checked_pairs=checked_pairs,
        authority_scope='fresh certificates per repeat, exact certificate equality within each Direct/NBSR pair',
        first_three_throughput_cv=first_cvs,
        cpu_scope='derived sampled source lifetime cores including startup/warmup/drain, not steady ns/op',
        memory_scope='both roles use local-clock Linux private-resident samples, approximate receipt-based phase; not leak/per-object cost',
        latency_scope='median of cell medians of steady-window quantiles; not pooled quantiles')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    print(json.dumps(analyze(parser.parse_args().root), indent=2))
