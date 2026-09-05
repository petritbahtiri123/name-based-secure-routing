from pathlib import Path
import json,hashlib,sys,collections
sys.path.insert(0,str(Path.cwd()))
from scripts.performance.b3_v2_analysis import analyze_scale,analyze_cycles
out=Path('evidence/performance/v2/b3-materialized-scale-a6d46796');out.mkdir(exist_ok=False)
names=['b3-materialized-bundles-797aabf1','b3-materialized-512-rate125-diagnostic','b3-materialized-512-rate125-repeats','b3-materialized-channels-797aabf1','b3-materialized-streams-797aabf1','b3-materialized-512-close-diagnostic','b3-materialized-1024-close-diagnostic','b3-materialized-streams-36e8970b','b3-materialized-streams-a6d46796','b3-materialized-cycles50-a6d46796']
fields=['transport_sessions_current_live','service_channels_current_live','application_streams_current_live','nbsr_tasks_current_live','quic_connections_current_live','quic_streams_current_live','pending_routes_current_entries','channel_registry_current_entries','stream_registry_current_entries','audit_queue_current_entries','replay_state_current_entries']
inputs=[];analyses=[]
for name in names:
 root=Path('C:/NBSR-build')/name;index=root/'checksums.sha256';lines=index.read_text().splitlines()
 for line in lines:
  h,rel=line.split('  ',1);assert hashlib.sha256((root/rel).read_bytes()).hexdigest()==h,(name,rel)
 cells=json.loads((root/'records.json').read_text()) if (root/'records.json').exists() else []
 env=json.loads((root/'environment.json').read_text());failure=[]
 for f in sorted((root/'raw').rglob('failure.json')):
  value=json.loads(f.read_text());failure.append({'cell':f.parent.name,'error':value['error'][:300],'raw_relative_path':str(f.relative_to(root)),'sample_phases':dict(collections.Counter(x['phase'] for x in value.get('samples',[])))})
 final_ownership=[]
 for cell in cells:
  p=root/'raw/rust-rust'/cell['name'];role_rows=[]
  for q in sorted(p.glob('source-*.stdout')):
   rows=[json.loads(x) for x in q.read_text().splitlines() if x.startswith('{')];final=[x for x in rows if x.get('phase')=='lifecycle_cleanup'];assert len(final)==1,(name,cell['name'],'source final count')
   role_rows.append(('source',final[0]))
   closed=[x for x in rows if str(x.get('phase','')).startswith('lifecycle_cycle_') and str(x.get('phase','')).endswith('_closed')]
   if cell['kind']=='cycles':
    assert len(closed)==cell['cycles']; assert all(all(type(x.get(k)) is int and x[k]==0 for k in fields) for x in closed),(name,cell['name'],'source cycle ownership')
  rows=[json.loads(x) for x in (p/'destination-diagnostics.ndjson').read_text().splitlines() if x.startswith('{')];assert rows
  role_rows.append(('destination',rows[-1]));assert all(all(type(row.get(k)) is int and row[k]==0 for k in fields) for _,row in role_rows),(name,cell['name'],'final ownership')
  final_ownership.append({'cell':cell['name'],'final_all_11_zero':True,'source_cycle_all_11_zero':True if cell['kind']=='cycles' else None,'source_audit_high_water':role_rows[0][1]['audit_queue_high_water_entries'],'destination_audit_high_water':role_rows[-1][1]['audit_queue_high_water_entries']})
 analyses.append({'raw_root':name,'source_sha':env.get('source_sha'),'scale':analyze_scale([c for c in cells if c['kind']!='cycles']),'cycles':[analyze_cycles(c) for c in cells if c['kind']=='cycles'],'failures':failure,'retained_diagnostics_ownership':final_ownership})
 inputs.append({'raw_path':str(root),'raw_index_sha256':hashlib.sha256(index.read_bytes()).hexdigest(),'verified_artifacts':len(lines),'completed_valid_cells':len(cells),'failed_attempts':len(failure),'source_sha':env.get('source_sha'),'binary_sha256':env.get('binary_sha256')})
 d=out/name;d.mkdir();(d/'raw-checksums.sha256').write_text(index.read_text(),newline='\n');(d/'environment.json').write_text(json.dumps(env,indent=2)+'\n',newline='\n')
 print(name,len(cells),'complete',len(failure),'failed',len(lines),'verified')
(out/'external-inputs.json').write_text(json.dumps(inputs,indent=2)+'\n',newline='\n');(out/'analysis.json').write_text(json.dumps(analyses,indent=2)+'\n',newline='\n')
print('all retained final ownership observations passed11fields')
