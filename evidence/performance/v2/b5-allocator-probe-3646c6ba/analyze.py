"""Verify a controlled allocator fixture; never classify NBSR from these rows."""
import json
from pathlib import Path
import statistics

root = Path(__file__).resolve().parent
phases = ('baseline', 'allocated', 'partial_touch', 'full_touch', 'freed', 'cooldown')
results = []
for mode in ('large', 'small'):
    for repeat in range(1, 6):
        path = root / f'{mode}-r{repeat}.ndjson'
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        assert tuple(r['phase'] for r in rows) == phases
        assert all(r['mode'] == mode for r in rows)
        assert all(type(v) is int and v >= 0 for r in rows for k, v in r.items()
                   if k not in ('mode', 'phase'))
        baseline, allocated, partial, full, freed, cooldown = rows
        expected = 3014656 if mode == 'large' else 16384 * 64
        assert [r['owned_requested_bytes'] for r in rows] == [0, expected, expected, expected, 0, 0]
        def account(row):
            return row['uordblks'] + row['hblkhd']
        assert account(allocated) - account(baseline) >= expected
        assert account(allocated) == account(partial) == account(full)
        assert account(cooldown) - account(baseline) < 65536
        if mode == 'large':
            assert full['private_bytes'] - allocated['private_bytes'] > 2 * 1024**2
            assert full['private_bytes'] - freed['private_bytes'] > 2 * 1024**2
            assert allocated['hblks'] == baseline['hblks'] + 1
            assert freed['hblks'] == cooldown['hblks'] == baseline['hblks']
        else:
            assert cooldown['private_bytes'] - baseline['private_bytes'] > 1024**2
            assert freed['fordblks'] - allocated['fordblks'] > 1024**2
        results.append(dict(mode=mode, repeat=repeat,
            allocation_accounting_delta=account(allocated)-account(baseline),
            untouched_private_delta=allocated['private_bytes']-baseline['private_bytes'],
            touch_private_delta=full['private_bytes']-allocated['private_bytes'],
            post_free_accounting_delta=account(cooldown)-account(baseline),
            post_free_private_delta=cooldown['private_bytes']-baseline['private_bytes'],
            post_free_arena_free_delta=cooldown['fordblks']-baseline['fordblks'],
            mallinfo2_ns=[r['mallinfo2_ns'] for r in rows]))
summary = {}
for mode in ('large', 'small'):
    selected = [r for r in results if r['mode'] == mode]
    fields = ('allocation_accounting_delta', 'untouched_private_delta',
              'touch_private_delta', 'post_free_accounting_delta',
              'post_free_private_delta', 'post_free_arena_free_delta')
    summary[mode] = {f: [min(r[f] for r in selected), max(r[f] for r in selected)] for f in fields}
    times = [n for r in selected for n in r['mallinfo2_ns']]
    summary[mode]['sample_duration_ns_range'] = [min(times), max(times)]
    summary[mode]['duration_cv_by_phase'] = {phase: statistics.stdev(r['mallinfo2_ns'][i] for r in selected)/statistics.mean(r['mallinfo2_ns'][i] for r in selected) for i, phase in enumerate(phases)}
    first_three = [r['mallinfo2_ns'][4] for r in selected[:3]]
    summary[mode]['first_three_freed_duration_cv'] = statistics.stdev(first_three)/statistics.mean(first_three)
report = dict(classification='CONTROLLED_FIXTURE_PASS_NOT_NBSR_ATTRIBUTION',
              repeats_per_mode=5, rows=results, summary=summary,
              observer_qualification='NOT_QUALIFIED_FOR_B5',
              limitations=['No NBSR binaries or workloads were executed.',
                  'Allocator accounting is not exact application-owned bytes.',
                  'Single-threaded mallinfo2 cost cannot qualify concurrent allocator contention.',
                  'Call durations exclude smaps and output; no negligible-overhead claim.'])
(root/'analysis.json').write_text(json.dumps(report, indent=2))
print(json.dumps(summary, indent=2))
print('PASS: 10 fixture processes / 60 phase observations')
