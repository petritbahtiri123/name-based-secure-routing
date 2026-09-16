"""Offline correlation only; no causal attribution or acceptance reclassification."""
import json
import statistics
from pathlib import Path

root = Path(__file__).resolve().parent
analysis = json.loads((root / 'analysis.json').read_text())
rows = []
for record in analysis['rows']:
    raw = root / f"retained-r{record['repeat']}/raw/nbsr-r1"
    result = json.loads((raw / 'result.json').read_text())
    resources = [json.loads(line) for line in (raw / 'resources.ndjson').read_text().splitlines()]
    progress = [json.loads(line) for line in (raw / 'source.stdout.ndjson').read_text().splitlines()]
    steady = [p for p in progress if p.get('phase') == 'steady']
    origin = result['qualification']['resource_phase_origin_monotonic_ns']
    windows = []
    for p in steady:
        cores = {}
        for role in ('source', 'destination_0'):
            samples = [r for r in resources if r['role'] == role and
                       origin + p['interval_start_ns'] <= r['timestamp_ns'] <= origin + p['interval_end_ns']]
            assert len(samples) >= 2
            assert len({(r['pid'], r['start_ticks']) for r in samples}) == 1
            a, b = samples[0], samples[-1]
            assert b['cpu_ns'] >= a['cpu_ns']
            cores[role] = (b['cpu_ns']-a['cpu_ns'])/(b['timestamp_ns']-a['timestamp_ns'])
        windows.append(dict(elapsed_seconds=p['elapsed_ns']/1e9,
                            p99_ms=p['p99_latency_ns']/1e6,
                            gbps=p['goodput_bytes_per_second']*8/1e9,
                            effective_cores=cores, approximate_sum_cores=sum(cores.values())))
    n = max(1, len(windows)//3)
    early = statistics.median(w['p99_ms'] for w in windows[:n])
    late = statistics.median(w['p99_ms'] for w in windows[-n:])
    assert result['final']['errors'] == result['final']['timeouts'] == 0
    assert all(r['all_11_zero'] for r in result['ownership_reports'])
    rows.append(dict(repeat=record['repeat'], windows=windows,
                     early_p99_ms=early, late_p99_ms=late,
                     final_thirds_p99_drift_percent=100*(late/early-1),
                     min_window_cores=min(w['approximate_sum_cores'] for w in windows),
                     max_window_cores=max(w['approximate_sum_cores'] for w in windows)))
report = dict(classification='OFFLINE_DIAGNOSTIC_CORRELATION', rows=rows,
              cv={field: statistics.stdev(r[field] for r in analysis['rows']) /
                         statistics.mean(r[field] for r in analysis['rows'])
                  for field in ('gbps', 'window_p99_median_ms')},
              limitations=['Approximate receive-clock phase alignment; role intervals differ slightly.',
                           'Window means do not measure scheduler waits or transient saturation.',
                           'Final thirds do not replace live gates or erase early violations.'])
(root / 'correlation.json').write_text(json.dumps(report, indent=2))
print(json.dumps({**report, 'rows': [{k:v for k,v in r.items() if k != 'windows'} for r in rows]}, indent=2))
