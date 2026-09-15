import json
from pathlib import Path

root = Path(__file__).resolve().parent
rows = []
for attempt in json.loads((root / 'results.json').read_text()):
    if not attempt['exit_code']:
        continue
    repeat = attempt['repeat']
    raw = root / f'window-1-r{repeat}/raw/rust-rust/live-bundles-2048-r1'
    failure = json.loads((raw / 'failure.json').read_text())
    snapshot = json.loads((raw / 'linux-udp-failure.json').read_text())
    hz = json.loads((root / f'window-1-r{repeat}-before-counters.json').read_text())['clock_ticks_per_second']
    assert type(hz) is int and hz > 0
    roles = []
    for role, value in snapshot['roles'].items():
        assert value['status'] == 'MEASURED_FAILURE_SNAPSHOT'
        samples = [p for row in failure['samples'] if row['phase'] == 'idle'
                   for p in row['processes'] if p['pid'] == value['pid']]
        before = samples[-1]
        assert before['start_ticks'] == value['start_ticks']
        assert len(before['affinity']) == 1
        seconds = (value['cpu_sample_monotonic_ns'] - before['timestamp_ns']) / 1e9
        cpu_seconds = value['cpu_ticks'] / hz - before['cpu_ns'] / 1e9
        assert seconds > 0 and cpu_seconds >= 0
        roles.append(dict(role=role, interval_seconds=seconds, cpu_seconds=cpu_seconds,
                          effective_cores=cpu_seconds / seconds, affinity=before['affinity'],
                          udp_drops=value['live_socket_drops']))
    rows.append(dict(repeat=repeat, clock_ticks_per_second=hz, roles=roles,
                     approximate_sum_effective_cores=sum(r['effective_cores'] for r in roles)))
report = dict(classification='DIAGNOSTIC', scope='last idle sample through failure snapshot; includes post-start wait',
              limitations=['Not instantaneous handshake CPU or function attribution.',
                           'Per-role intervals have slightly different endpoints.',
                           'An average below 90% cannot exclude brief CPU saturation.'], rows=rows)
(root / 'failure-cpu-analysis.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
