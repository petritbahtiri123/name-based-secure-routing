"""Replay native concurrent-bundle diagnostic memory without timing claims."""

import json
from collections import Counter
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path.cwd()))
from scripts.performance.linux_native_lifecycle_gate import check_endpoint
from scripts.performance.linux_native_lifecycle_pair import analyze
from scripts.performance.linux_native_pair import verify_index
from scripts.performance.post_close_cleanup import FIELDS
from scripts.performance.b3_v2_analysis import slope

root = Path(sys.argv[1])
verify_index(root)
records = json.loads((root / 'records.json').read_bytes())
assert all(r['status'] in ('PASS_FUNCTIONAL', 'FAIL_RETAINED') for r in records)
counts = (16, 32, 64, 128, 256, 512, 1024)
assert {r['count'] for r in records} == set(counts)
assert len({r['label'] for r in records}) == len(records), 'cohort identity: repeated cell'
for record in records:
    assert record['label'] == f"n{record['count']}-r{record['repeat']}", 'cohort identity: label/repeat mismatch'
    config = json.loads((root / record['label'] / 'config.json').read_bytes())
    assert config['source_sha'] == 'c5b53c66a12ba5fa59a2d9d97ef724ec27d50928', 'cohort identity: mixed source'
rows = []
failures = []
for record in records:
    cell = root / record['label']
    verify_index(cell)
    config = json.loads((cell / 'config.json').read_bytes())
    count = config['count']
    assert count == record['count'] and config['rate'] == 100 and config['shards'] == 2
    assert config['memory_observer'] is True
    if record['status'] == 'FAIL_RETAINED':
        assert count == 1024 and record['repeat'] == 1
        diagnostics = {}
        for role in ('source', 'destination'):
            peer = cell / role / 'peer'
            verify_index(cell / role)
            verify_index(peer)
            close = [json.loads(line) for line in (peer / 'stderr').read_text(encoding='utf-8').splitlines()
                     if line.startswith('{"schema":"nbsr-b3-close-diagnostic-v1"')]
            held = [r['released_elapsed_ns'] - r['prepared_elapsed_ns'] for r in close if r['close_reason'] == 'timed_out']
            diagnostics[role] = dict(close_reasons=dict(Counter(r['close_reason'] for r in close)),
                timed_out_ready_to_release_ns_min=min(held), timed_out_ready_to_release_ns_max=max(held),
                forced_cleanup=json.loads((peer / 'forced-cleanup.json').read_bytes()))
        source = [json.loads(line) for line in (cell / 'source/peer/stdout').read_text(encoding='utf-8').splitlines()]
        outcomes = [r for r in source if type(r.get('success')) is bool]
        assert len({r['logical_client_id'] for r in outcomes}) == len(outcomes)
        assert record['owned_processes_absent_before_stop'] == {'source': True, 'destination': True}
        failures.append(dict(label=record['label'], count=count, status='FAILED_PARTIAL_IDLE_EXPIRY_OBSERVED',
            source_recorded_successes=sum(r['success'] for r in outcomes), source_recorded_failures=sum(not r['success'] for r in outcomes),
            source_missing_terminal_outcomes=count-len(outcomes), diagnostics=diagnostics,
            final_ownership='NOT_MEASURED: cancelled after failure; owned processes killed and absence verified'))
        continue
    result = analyze(cell / 'source/peer', cell / 'destination/peer', source_sha=config['source_sha'], count=count, memory_observer=True)
    resources = {}
    for role in ('source', 'destination'):
        events = check_endpoint(cell / role, role, count, memory_observer=True)['events']
        env = json.loads((cell / role / 'peer/environment.json').read_bytes())
        assert env['offered_rate'] == 100 and env['source_shards'] == 2
        assert len(env['linux_environment']['selected_cpus']) == config[role]['cores'] == 1
        samples = [json.loads(line) for line in (cell / role / 'peer/resources.ndjson').read_text(encoding='utf-8').splitlines()]
        memory = [json.loads(line) for line in (cell / role / 'peer/memory.ndjson').read_text(encoding='utf-8').splitlines()]
        phases = {'active': (events['active']['timestamp_ns'], events['released']['timestamp_ns'])}
        if role == 'destination':
            phases['cooldown'] = (events['report_ready']['timestamp_ns'], events['report_released']['timestamp_ns'])
        measured = {}
        for name, (start, end) in phases.items():
            ms = [m['value'] for m in memory if start <= m['capture_started_ns'] <= m['capture_finished_ns'] <= end and m['value']['memory_state'] == 'MEASURED']
            ss = [s for s in samples if start <= s['timestamp_ns'] <= end and s['state'] != 'Z']
            assert ms and ss and all(s['fd_count_state'] == 'MEASURED' for s in ss)
            private = statistics.median(m['private_resident_bytes'] for m in ms)
            assert private == record['phase_private_bytes'][role][name]
            measured[name] = dict(private_median_bytes=private, pss_median_bytes=statistics.median(m['pss_bytes'] for m in ms),
                                  rss_median_bytes=statistics.median(s['rss_bytes'] for s in ss), memory_samples=len(ms),
                                  fd_min=min(s['fd_count'] for s in ss), fd_max=max(s['fd_count'] for s in ss),
                                  thread_min=min(len(s['thread_ids']) for s in ss), thread_max=max(len(s['thread_ids']) for s in ss))
        resources[role] = dict(phases=measured, max_memory_capture_ns=max(m['capture_finished_ns'] - m['capture_started_ns'] for m in memory))
        assert all(type(result[role + '_cleanup'][field]) is int and result[role + '_cleanup'][field] == 0 for field in FIELDS)
    assert record['owned_processes_absent_before_stop'] == {'source': True, 'destination': True}
    cleanup = json.loads((cell / 'cleanup.json').read_bytes())
    assert all(not value['local_relay_forced'] for value in cleanup.values())
    rows.append(dict(label=record['label'], count=count, result=result, resources=resources))
cells = {}
assert len(failures) == 1
for count in counts[:-1]:
    subset = [r for r in rows if r['count'] == count]
    first = {}
    metrics = {}
    for role, phase in (('source', 'active'), ('destination', 'active'), ('destination', 'cooldown')):
        values = [r['resources'][role]['phases'][phase]['private_median_bytes'] for r in subset]
        key = role + '_' + phase
        first[key] = statistics.stdev(values[:3]) / statistics.mean(values[:3])
        metrics[key] = dict(values=values, median_bytes=statistics.median(values), cv=statistics.stdev(values) / statistics.mean(values))
    assert first == json.loads((root / f'n{count}-first-three-resource-cv.json').read_bytes())
    assert len(subset) == (5 if any(v > .05 for v in first.values()) else 3)
    assert [r['repeat'] for r in records if r['count'] == count] == list(range(1, len(subset) + 1))
    cells[str(count)] = dict(repeats=len(subset), first_three_cv=first, private=metrics)
bundled_slopes = {key: slope([(int(n), cell['private'][key]['median_bytes']) for n, cell in cells.items()])
                  for key in ('source_active', 'destination_active', 'destination_cooldown')}
print(json.dumps(dict(classification='PARTIAL_DIAGNOSTIC_MEMORY_SCALE_1024_FAILED', trials=len(rows),
    successful_connections=sum(r['count'] for r in rows), all_successful_trials_final_eleven_ownership_counters_zero=True,
    source_cooldown='NOT_MEASURED: source exits after ACK', observer_neutrality='NOT_ESTABLISHED',
    marginal_cost='NOT_QUALIFIED: connection/session/channel/stream co-vary',
    derived_private_bytes_per_additional_bundle=bundled_slopes,
    slope_scope='DERIVED least-squares slope of measured cell medians;16..512 successful bundles only;includes transport/runtime/fixtures;no isolated resource or extrapolation claim',
    scope='Docker/WSL namespaces; one advertised guest core per role; no physical/server/capacity claim',
    attempted_trials=len(records), failures=failures, cells=cells, rows=rows), indent=2))
