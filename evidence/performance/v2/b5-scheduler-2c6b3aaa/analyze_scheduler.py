"""Offline scheduler accounting. Queue wait is not network or host stall attribution."""
import json
from pathlib import Path

root = Path(__file__).resolve().parent
cohort = json.loads((root / 'analysis.json').read_text())
rows = []
for run in cohort['rows']:
    if run['observer'] != 'on':
        continue
    name = f"pair-r{run['repeat']}-on"
    raw = root / name / 'raw/nbsr-r1'
    result = json.loads((raw / 'result.json').read_text())
    origin = result['qualification']['resource_phase_origin_monotonic_ns']
    end = origin + 300_000_000_000
    resources = [json.loads(x) for x in (raw / 'resources.ndjson').read_text().splitlines()]
    events = [json.loads(x) for x in (root / (name + '-sched.ndjson')).read_text().splitlines()]
    assert events[0]['event'] == 'observer_start'
    assert events[-1]['event'] == 'observer_end' and events[-1]['stopped']
    unavailable = [r for r in events if r['event'] == 'sample_unavailable'
                   and origin <= r['timestamp_ns'] <= end]
    assert not unavailable, unavailable
    progress = [json.loads(x) for x in (raw / 'source.stdout.ndjson').read_text().splitlines()]
    windows = [x for x in progress if x.get('event') == 'b5_grouped_progress' and x.get('phase') == 'steady']
    output = dict(repeat=run['repeat'], roles={}, windows=[])
    series = {}
    for role in ('source', 'destination_0'):
        expected = {(r['pid'], r['start_ticks']) for r in resources if r['role'] == role}
        samples = [r for r in events if r['event'] == 'scheduler_sample' and r['role'] == role
                   and origin <= r['timestamp_ns'] <= end]
        assert len(samples) >= 290
        assert {(r['pid'], r['start_ticks']) for r in samples} == expected
        assert max(b['timestamp_ns'] - a['timestamp_ns'] for a, b in zip(samples, samples[1:])) < 2_000_000_000
        identities = {tuple((t['tid'], t['start_ticks']) for t in r['tasks']) for r in samples}
        assert len(identities) == 1, 'task set changed during steady phase'
        series[role] = samples
        def delta(first, last):
            span = last['timestamp_ns'] - first['timestamp_ns']
            threads = []
            for a, b in zip(first['tasks'], last['tasks']):
                assert (a['tid'], a['start_ticks']) == (b['tid'], b['start_ticks'])
                values = {k: b[k] - a[k] for k in ('runtime_ns', 'runqueue_ns', 'timeslices')}
                assert all(v >= 0 for v in values.values())
                threads.append(dict(tid=a['tid'], **values))
            return dict(wall_ns=span, threads=threads,
                        runtime_cores=sum(t['runtime_ns'] for t in threads) / span,
                        runqueue_thread_seconds_per_second=sum(t['runqueue_ns'] for t in threads) / span)
        output['roles'][role] = dict(samples=len(samples), **delta(samples[0], samples[-1]))
    for window in windows:
        row = dict(elapsed_seconds=window['elapsed_ns']/1e9, p99_ms=window['p99_latency_ns']/1e6,
                   gbps=window['goodput_bytes_per_second']*8/1e9, roles={})
        for role, samples in series.items():
            selected = [r for r in samples if origin+window['interval_start_ns'] <= r['timestamp_ns'] <= origin+window['interval_end_ns']]
            assert len(selected) >= 25
            row['roles'][role] = delta(selected[0], selected[-1])
        output['windows'].append(row)
    cgroup = [r for r in events if r['event']=='cgroup_cpu' and origin <= r['timestamp_ns'] <= end]
    assert len(cgroup) >= 290
    output['cgroup_delta'] = {k:cgroup[-1]['counters'][k]-cgroup[0]['counters'][k]
                             for k in cgroup[0]['counters']}
    assert all(v>=0 for v in output['cgroup_delta'].values())
    rows.append(output)
report = dict(classification='SCHEDULER_ACCOUNTING_DIAGNOSTIC', rows=rows,
              source='https://docs.kernel.org/scheduler/sched-stats.html',
              limitations=['Runqueue time is per-thread wait to execute, not total blocked/IO time.',
                  'Summed waiting thread-seconds are not CPU utilization.',
                  'Guest counters cannot explain Windows host scheduling or prove a physical-core ceiling.',
                  'Cgroup CPU includes controller and observer; kernel counters may update at schedule boundaries.',
                  'Observer qualification must be assessed independently from the matched cohort.'])
(root/'scheduler-analysis.json').write_text(json.dumps(report, indent=2))
for row in rows:
    print(json.dumps({k:v for k,v in row.items() if k!='windows'}))
