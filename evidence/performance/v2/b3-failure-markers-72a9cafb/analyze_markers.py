import hashlib
import json
from pathlib import Path
import statistics

root = Path(__file__).resolve().parent
rows = []
verified = 0
def quantiles(values):
    values = sorted(values)
    if not values:
        return None
    return dict(n=len(values), p50_ms=round(statistics.median(values), 3),
                p95_ms=round(values[int((len(values)-1)*.95)], 3),
                p99_ms=round(values[int((len(values)-1)*.99)], 3), max_ms=round(values[-1], 3))
for result in json.loads((root / 'results.json').read_text()):
    case = root / f"window-1-r{result['repeat']}"
    for line in (case / 'checksums.sha256').read_text().splitlines():
        expected, name = line.split('  ', 1)
        path = (case / name).resolve()
        assert path.is_relative_to(case.resolve())
        with path.open('rb') as stream:
            assert hashlib.file_digest(stream, 'sha256').hexdigest() == expected
        verified += 1
    raw = case / 'raw/rust-rust/live-bundles-2048-r1'
    row = dict(repeat=result['repeat'], exit_code=result['exit_code'])
    if not result['exit_code']:
        cell = json.loads((raw / 'cell.json').read_text())
        assert cell['cleanup']['all_zero'] and cell['cleanup']['source_all_zero']
        row['cleanup'] = cell['cleanup']
        rows.append(row)
        continue
    snapshot = json.loads((raw / 'failure-markers.json').read_text())
    assert snapshot['status'] == 'CAPTURED'
    markers = {m['name']: m['mtime_ns'] for m in snapshot['markers']}
    assert len(markers) == len(snapshot['markers'])
    starts = [markers[f'connection-{i}.start'] for i in range(2048)]
    row['start_timestamps_nondecreasing'] = all(b >= a for a, b in zip(starts, starts[1:]))
    row['start_span_seconds'] = (starts[-1] - starts[0]) / 1e9
    row['cohorts'] = []
    for lower in range(0, 2048, 512):
        before, after = [], []
        absent, connected_only = [], []
        for i in range(lower, lower + 512):
            start = markers[f'connection-{i}.start']
            connected = markers.get(f'connection-{i}.connected')
            active = markers.get(f'connection-{i}.active')
            if connected is None:
                assert active is None
                absent.append(i)
            else:
                before.append((connected - start) / 1e6)
                if active is None:
                    connected_only.append(i)
                else:
                    after.append((active - connected) / 1e6)
        row['cohorts'].append(dict(first=lower, last=lower+511,
            missing_connected=len(absent), connected_without_active=len(connected_only),
            start_to_connected=quantiles(before), connected_to_active=quantiles(after),
            negative_intervals=sum(v < 0 for v in before+after)))
    rows.append(row)
report = dict(classification='DIAGNOSTIC marker publication intervals; wall clock not independently qualified',
              indexed_files_verified=verified, rows=rows)
(root / 'marker-analysis.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
