import json,statistics
from pathlib import Path
root=Path('C:/NBSR-build/b5-placement-pairs-201e1d0e')
a=json.loads((root/'analysis.json').read_text())
extra=[]
for r in a['rows']:
 raw=root/f"pair-r{r['repeat']}-{r['placement']}"/'raw/nbsr-r1'
 windows=[json.loads(x) for x in (raw/'source.stdout.ndjson').read_text().splitlines()]
 windows=[x for x in windows if x.get('event')=='b5_grouped_progress' and x.get('phase')=='steady']
 assert len(windows) in (9, 10)  # boundary progress may be emitted as drain
 extra.append(dict(repeat=r['repeat'],placement=r['placement'],windows=len(windows),
  median_window_latency_ns={p:statistics.median(x[p+'_latency_ns'] for x in windows) for p in ('p50','p95','p99')},
  max_window_p99_ns=max(x['p99_latency_ns'] for x in windows),
  offered=r['final']['offered'],completed=r['final']['completed'],missed=r['final']['missed'],
  missed_fraction=r['final']['missed']/r['final']['offered'],
  cpu_ns_per_completed_op_approx=r['sum_effective_cores']*1e9/(r['final']['completed']/300)))
report=dict(classification='DIAGNOSTIC_DERIVED_PHASE_APPROXIMATION',rows=extra,
 cohorts={p:{f:statistics.median(x[f] for x in extra if x['placement']==p) for f in ('max_window_p99_ns','missed_fraction','cpu_ns_per_completed_op_approx')} for p in ('shared','split')})
(root/'latency-and-efficiency.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report['cohorts'],indent=2))

