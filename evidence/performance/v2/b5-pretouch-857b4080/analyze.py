import json
from pathlib import Path
import statistics

root = Path(__file__).parent
run = root / 'off-r1'
row = json.loads((run / 'records.json').read_text())[0]
origin = row['qualification']['resource_phase_origin_monotonic_ns']
resources = [json.loads(line) for line in (run / 'raw/nbsr-r1/resources.ndjson').read_text().splitlines()]
progress = [json.loads(line) for line in (run / 'raw/nbsr-r1/source.stdout.ndjson').read_text().splitlines()]
steady = [p for p in progress if p.get('phase') == 'steady']
end = origin + steady[-1]['elapsed_ns']
result = {'classification': 'FAILED_DIAGNOSTIC_NO_STABLE_CLAIM', 'source_sha': '857b4080',
          'error': row['error'], 'steady_windows': len(steady), 'roles': {}}
for role in ('source', 'destination_0'):
    selected = [r for r in resources if r['role'] == role and origin <= r['timestamp_ns'] <= end and r.get('private_resident_bytes') is not None]
    xs = [(r['timestamp_ns'] - origin) / 1e9 for r in selected]
    ys = [r['private_resident_bytes'] for r in selected]
    mx, my = statistics.mean(xs), statistics.mean(ys)
    slope = sum((x-mx)*(y-my) for x,y in zip(xs,ys))/sum((x-mx)**2 for x in xs)
    residual = sum((y-(my+slope*(x-mx)))**2 for x,y in zip(xs,ys))
    total = sum((y-my)**2 for y in ys)
    result['roles'][role] = dict(samples=len(xs), first_private=ys[0], last_private=ys[-1],
        delta=ys[-1]-ys[0], slope_bytes_s=slope, r_squared=1-residual/total if total else 1,
        fd_range=[min(r['fd_count'] for r in selected), max(r['fd_count'] for r in selected)],
        thread_range=[min(len(r['thread_ids']) for r in selected), max(len(r['thread_ids']) for r in selected)],
        ten_second_last_private=[next((r['private_resident_bytes'] for r in reversed(selected)
            if r['timestamp_ns'] <= origin+t*1_000_000_000), None) for t in range(10,101,10)])
result['last_progress'] = steady[-1]
(root / 'analysis.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
