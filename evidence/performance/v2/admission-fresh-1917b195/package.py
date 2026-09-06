from pathlib import Path
import hashlib
import json
import shutil
import sys

REPO = Path('C:/Users/bajra/OneDrive/Documents/NBSR')
sys.path.insert(0, str(REPO))
from scripts.run_b4b_task4i import summarize

raw = Path('C:/NBSR-build/task4i-fresh-1917b195')
out = REPO / 'evidence/performance/v2/admission-fresh-1917b195'
out.mkdir(exist_ok=False)
index = (raw / 'checksums.sha256').read_text()
for line in index.splitlines():
    expected, relative = line.split('  ', 1)
    target = (raw / relative).resolve()
    assert target.is_relative_to(raw.resolve())
    assert hashlib.sha256(target.read_bytes()).hexdigest() == expected, relative
analysis = json.loads((raw / 'analysis.json').read_text())
environment = json.loads((raw / 'environment.json').read_text())
assert environment['repository_sha'].startswith('1917b195')
assert environment['dirty_tree'] is False
rebuilt = []
records = []
for cell in analysis['cells']:
    rows = [json.loads(p.read_text()) for p in sorted((raw / 'raw' / f"rate-{cell['offered_rate']}").glob('r[0-9].json'))]
    assert all(r['valid'] for r in rows)
    result = summarize(cell['offered_rate'], rows, rebuilt[0] if rebuilt else None)
    assert result == cell
    rebuilt.append(result)
    records.extend(rows)
assert len(records) == 27
assert all(r['successful_admissions'] == 512 and r['errors'] == 0 and r['timeouts'] == 0 for r in records)
assert all(r['cleanup']['all_zero'] and r['cleanup']['processes_exited'] and r['cleanup']['terminal_evidence_exact'] for r in records)
for r in records:
    assert len(r['cleanup']['destinations']) == 2
    for destination in r['cleanup']['destinations']:
        assert len(destination['counters']) == 8
        assert all(value == 0 for value in destination['counters'].values())
for name in ('analysis.json', 'environment.json'):
    (out / name).write_text((raw / name).read_text(), encoding='utf-8', newline='\n')
(out / 'raw-checksums.sha256').write_text(index, encoding='utf-8', newline='\n')
validation = {
    'raw_root': str(raw), 'verified_raw_artifacts': len(index.splitlines()),
    'valid_repeats': len(records), 'invalid_repeats': analysis['invalid_runs'],
    'successful_admissions': sum(r['successful_admissions'] for r in records),
    'errors': 0, 'timeouts': 0, 'recomputed_cells_equal': True,
    'destination_cleanup_scope': 'eight tracked counters on each of two destinations',
    'source_cleanup_scope': 'exact terminal evidence for all 512 clients and process exit; no source 11-counter assertion',
    'observational_work': 'No concurrent builds/tests/Docker workloads or repository edits during measurement; light read-only status inspection and external planning continued.',
}
(out / 'validation.json').write_text(json.dumps(validation, indent=2) + '\n', encoding='utf-8', newline='\n')
table = '\n'.join(
    f"| {c['offered_rate']} | {c['repeats']} | {c['actual_admissions_per_second']:.3f} | {100*c['achieved_offered_ratio']:.2f}% | {100*c['repeat_cv']:.2f}% | {c['handshake_latency_ns']['99']/1e6:.3f} | {c['admission_p99_latency_ns']/1e6:.3f} | {c['status']} |"
    for c in rebuilt)
report = f'''# Fresh finite-batch admission progression

MEASURED on clean source `{environment['repository_sha']}`, release Windows loopback,
two source shards, inherited affinity. Every repeat offers 512 clients alongside
30 seconds of established forwarding with two seconds of warmup. This is a finite
admission batch, **not sustained admission-soak or production/server capacity**.

| Offered/s | Repeats | Actual admissions/s | Achieved/offered | Max rate/goodput CV | Handshake p99 ms | Admission p99 ms | Classification |
| --- | --- | --- | --- | --- | --- | --- | --- |
{table}

All 27 repeats are valid and retained: 13,824 successful admissions, zero errors
and timeouts. All 512 terminal client records reconcile per repeat; all processes
exit. Eight tracked counters are zero on each of the two destinations. This
runner does not establish a source-global 11-counter post-close ownership result.

The highest tested STABLE offered rate is 125/s (119.920 actual/s). At 150/s the
median achieved/offered ratio is below 95%; at 200/s it is below 90%, which is
SATURATED under the declared classifier despite every client eventually succeeding.
Progression therefore stops at 200/s after preceding stable cells; configured
250/s was not executed. The 25/s and 50/s cells remain DEGRADED by forwarding CV,
with no attempt to remove unfavorable repeats or replace the original reference.
The classifier uses the 25/s cell's median forwarding reference, whose CV remains
above 5%; low-rate dispersion remains a qualification, not a proven causal limit.

Median sampled process CPU is approximately 1.32â€“1.52 effective cores across these
cells (whole observed lifetime). No physical-core affinity was imposed and no
hardware ceiling or production bottleneck is established. Handshake progress
remains UNRESOLVED / PLATFORM_DIAGNOSTIC_LIMIT under the earlier rejected observer
comparisons. These fresh outcomes cannot prove a cause for historical differences.

Historical 119.813 admissions/s and Task 4k's saturated outcomes remain separate
source/workload-stage evidence. This fresh cohort preserves the same broad
125/150/200 classification sequence; it is not an exact before/after optimization
comparison. No new production optimization accompanies this package.

`analysis.json` is the original runner output, independently rebuilt exactly from
all repeat records. `raw-checksums.sha256` binds all 254 retained raw artifacts
under `C:/NBSR-build/task4i-fresh-1917b195`; `environment.json` binds commands,
binary/source hashes and host identity. `validation.json` records integrity and
ownership scope. The package helper verifies raw data before writing this report.

Reproduce from the source SHA with a fresh output path:

```powershell
$env:CARGO_TARGET_DIR='C:/NBSR-build/b4b-task4k'
python scripts/run_b4b_task4i.py --output C:/NBSR-build/task4i-fresh-UNIQUE --source-shards 2 --offered-rates 25 50 75 100 125 150 200 250
```

No Administrator action, push, main modification or evidence deletion was needed.
Current benchmark forwarding/soak and complete external validation remain pending.
'''
(out / 'REPORT.md').write_text(report, encoding='utf-8', newline='\n')
(out / 'package.py').write_text(Path(__file__).read_text(), encoding='utf-8', newline='\n')
(out / 'checksums.sha256').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n' for p in sorted(out.iterdir()) if p.is_file()), encoding='utf-8', newline='\n')
print(json.dumps(validation, indent=2))
