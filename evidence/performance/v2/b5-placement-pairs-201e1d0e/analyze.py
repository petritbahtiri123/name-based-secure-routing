import hashlib,json,statistics,sys
from pathlib import Path
root=Path('C:/NBSR-build/b5-placement-pairs-201e1d0e')
repo=Path('C:/Users/bajra/OneDrive/Documents/NBSR')
sys.path.insert(0,str(repo))
from scripts.performance.post_close_cleanup import FIELDS
from scripts.performance.b5_ownership import CAPACITIES
rows=[]
verified=0
for attempt in json.loads((root/'results.json').read_text()):
 case=root/f"pair-r{attempt['repeat']}-{attempt['placement']}"
 for line in (case/'checksums.sha256').read_text().splitlines():
  expected,name=line.split('  ',1); p=(case/name).resolve()
  assert p.is_relative_to(case.resolve())
  with p.open('rb') as f: assert hashlib.file_digest(f,'sha256').hexdigest()==expected,p
  verified+=1
 env=json.loads((case/'environment.json').read_text())
 expected={'source':[0], 'destination_0':[0 if attempt['placement']=='shared' else 1]}
 cpus=env['linux_environment']['selected_cpus']
 expected={'source':[cpus[0]], 'destination_0':[cpus[-1]]}
 assert len(cpus)==(1 if attempt['placement']=='shared' else 2)
 assert env['cpu_allocation']['verified_host_physical_cores'] is False
 assert env['shape']['runtime_workers']==1
 assert env['placement']['source_mask']==1<<cpus[0]
 assert env['placement']['endpoint_masks']==[1<<cpus[-1]]
 raw=case/'raw/nbsr-r1'
 commands=json.loads((raw/'commands.json').read_text())
 assert all(c['argv'][0:3]==[env['linux_environment']['taskset'],'-c',str(expected[c['role']][0])] for c in commands)

 r=json.loads((raw/'result.json').read_text())
 assert r['final']['errors']==r['final']['timeouts']==0
 assert all(x['all_11_zero'] for x in r['ownership_reports'])
 origin=r['qualification']['resource_phase_origin_monotonic_ns']
 resources=[json.loads(x) for x in (raw/'resources.ndjson').read_text().splitlines()]
 row=dict(attempt,failures=r.get('diagnostic_gate_failures',[]),final=r['final'],final_all_11_zero=True,resources={},ownership={})
 for role,filename in [('source','source.stdout.ndjson'),('destination_0','d0.ownership.ndjson')]:
  samples=[s for s in resources if s['role']==role and origin<=s['timestamp_ns']<=origin+300_000_000_000]
  assert len({(s['pid'],s['start_ticks']) for s in samples})==1
  assert len(samples)>=299 and all(s['affinity']==expected[role] for s in samples)
  first,last=samples[0],samples[-1]
  row['resources'][role]=dict(samples=len(samples),private_first=first['private_resident_bytes'],private_last=last['private_resident_bytes'],private_delta=last['private_resident_bytes']-first['private_resident_bytes'],effective_cores=(last['cpu_ns']-first['cpu_ns'])/(last['timestamp_ns']-first['timestamp_ns']),fd_range=[min(s['fd_count'] for s in samples),max(s['fd_count'] for s in samples)],thread_range=[min(len(s['thread_ids']) for s in samples),max(len(s['thread_ids']) for s in samples)])
  if True:
   snapshots=[json.loads(x) for x in (raw/filename).read_text().splitlines()]
   snapshots=[s for s in snapshots if s.get('schema')=='nbsr-rust-ownership-v1' and s.get('phase') in ('b5_sample','sample')]
   assert len(snapshots)>=299
   row['ownership'][role]=dict(samples=len(snapshots),ranges={f:[min(s[f] for s in snapshots),max(s[f] for s in snapshots)] for f in (*FIELDS,*CAPACITIES) if all(f in s for s in snapshots)})
   active=[s for s in snapshots if s['application_streams_current_live']==8 and s['transport_sessions_current_live']==1]
   assert len(active)>=295
   row['ownership'][role]['active_samples']=len(active)
   row['ownership'][role]['active_ranges']={f:[min(s[f] for s in active),max(s[f] for s in active)] for f in (*FIELDS,*CAPACITIES) if all(f in s for s in active)}
   assert all(a==b for a,b in row['ownership'][role]['active_ranges'].values())
 row['sum_effective_cores']=sum(s['effective_cores'] for s in row['resources'].values())
 rows.append(row)
metrics=('gbps','window_p99_median_ns','sum_effective_cores')
cohorts={o:{f:dict(median=statistics.median(r[f] for r in rows if r['placement']==o),cv=statistics.stdev(r[f] for r in rows if r['placement']==o)/statistics.mean(r[f] for r in rows if r['placement']==o)) for f in metrics} for o in ('shared','split')}
deltas={f:100*(cohorts['split'][f]['median']/cohorts['shared'][f]['median']-1) for f in metrics}
pairs=[dict(repeat=n,delta_percent={f:100*(next(r for r in rows if r['repeat']==n and r['placement']=='split')[f]/next(r for r in rows if r['repeat']==n and r['placement']=='shared')[f]-1) for f in metrics}) for n in sorted({r['repeat'] for r in rows})]
report=dict(classification='DIAGNOSTIC_NOT_ACCEPTED_SOAK',observer_qualification='NOT_QUALIFIED',indexed_files_verified=verified,cohorts=cohorts,median_delta_percent=deltas,paired_deltas=pairs,rows=rows,limitations=['Complete failed runs are retained, not accepted stability repeats.','Sampled NBSR counters and retained map capacities do not account for every Quinn, Tokio or allocator allocation.','Independent 300-second runs cannot establish a sustained soak.','Fixed historical offered rate is not a current-SHA capacity calibration.','Split uses two selected guest CPUs versus one shared CPU; not a same-resource efficiency comparison.','Guest CPU affinity is not verified host physical-core isolation; resource phase alignment uses receive-clock approximation.'])
(root/'analysis.json').write_text(json.dumps(report,indent=2))
print(json.dumps({k:v for k,v in report.items() if k!='rows'},indent=2))
for r in rows: print(json.dumps({k:r[k] for k in ('repeat','placement','failures','resources','ownership')}))


