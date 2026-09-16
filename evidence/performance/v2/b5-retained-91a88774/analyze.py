import hashlib
import json
from pathlib import Path
import statistics
import sys

repo = Path('C:/Users/bajra/OneDrive/Documents/NBSR')
sys.path.insert(0, str(repo))
from scripts.performance.sustained_capacity import _slope, private_growth

root = Path(__file__).resolve().parent
rows = []
verified = 0
for attempt in json.loads((root / 'results.json').read_text()):
    case = root / f"retained-r{attempt['repeat']}"
    for line in (case / 'checksums.sha256').read_text().splitlines():
        expected, name = line.split('  ', 1)
        path = (case / name).resolve()
        assert path.is_relative_to(case.resolve())
        with path.open('rb') as stream:
            assert hashlib.file_digest(stream, 'sha256').hexdigest() == expected
        verified += 1
    raw = case / 'raw/nbsr-r1'
    result = json.loads((raw / 'result.json').read_text())
    origin = result['qualification']['resource_phase_origin_monotonic_ns']
    resources = [json.loads(line) for line in (raw / 'resources.ndjson').read_text().splitlines()]
    progress = [json.loads(line) for line in (raw / 'source.stdout.ndjson').read_text().splitlines()]
    windows = [r for r in progress if r.get('phase') == 'steady' and r.get('p99_latency_ns') is not None]
    row = dict(repeat=attempt['repeat'], classification=result['classification'], valid=result['valid'],
               gbps=result.get('gbps'), achieved_offered_ratio=result.get('achieved_offered_ratio'),
               first_performance_failure=(result.get('diagnostic_gate_failures') or [None])[0],
               failure_count=len(result.get('diagnostic_gate_failures', [])),
               ownership_reports=result.get('ownership_reports'), continuous_ownership=result.get('continuous_ownership'),
               final=result.get('final'), window_count=len(windows),
               window_p99_median_ms=statistics.median(r['p99_latency_ns'] for r in windows)/1e6 if windows else None,
               memory={})
    for role in ('source', 'destination_0'):
        selected = [r for r in resources if r['role'] == role
                    and r.get('private_resident_bytes') is not None
                    and origin <= r['timestamp_ns'] <= origin + 600_000_000_000]
        assert all(b['timestamp_ns'] >= a['timestamp_ns'] for a,b in zip(selected, selected[1:]))
        subsets = {}
        for label, minimum in (('whole', 0), ('last_300s', 300)):
            samples = [r for r in selected if (r['timestamp_ns']-origin)/1e9 >= minimum]
            points = [((r['timestamp_ns']-origin)/1e9, r['private_resident_bytes']) for r in samples]
            if not points:
                subsets[label] = None
                continue
            slope, r_squared = _slope(points)
            subsets[label] = dict(samples=len(points), first_seconds=points[0][0], last_seconds=points[-1][0],
                first_bytes=points[0][1], last_bytes=points[-1][1], delta_bytes=points[-1][1]-points[0][1],
                min_bytes=min(p[1] for p in points), max_bytes=max(p[1] for p in points),
                slope_bytes_per_second=slope, r_squared=r_squared, private_growth_gate=private_growth(points),
                fd_min=min(r['fd_count'] for r in samples), fd_max=max(r['fd_count'] for r in samples),
                threads_min=min(len(r['thread_ids']) for r in samples),
                threads_max=max(len(r['thread_ids']) for r in samples))
        row['memory'][role] = subsets
    rows.append(row)
report = dict(classification='DIAGNOSTIC_NOT_ACCEPTED_SOAK', indexed_files_verified=verified, rows=rows,
    limitations=['RSS/private residency does not identify live allocation ownership or prove a leak.',
                 'Phase origin is first-progress receipt minus elapsed; approximate.',
                 'Last-300s analysis is supplementary; it cannot erase earlier failures.',
                 'Fixed historical rate is not current near-ceiling calibration; observer unqualified.'])
(root / 'analysis.json').write_text(json.dumps(report, indent=2))
print(json.dumps([dict(repeat=r['repeat'], classification=r['classification'], gbps=r['gbps'],
    first_failure=r['first_performance_failure'], memory=r['memory']) for r in rows], indent=2))
