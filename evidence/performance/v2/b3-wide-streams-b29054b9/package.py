from pathlib import Path
import json,hashlib,sys
sys.path.insert(0,str(Path.cwd()))
from scripts.performance.b3_v2_analysis import analyze_scale
root=Path('C:/NBSR-build/b3-wide-streams-b29054b9');p=Path('evidence/performance/v2/b3-wide-streams-b29054b9');p.mkdir()
index=root/'checksums.sha256';lines=index.read_text().splitlines()
for line in lines:
 h,rel=line.split('  ',1);assert hashlib.sha256((root/rel).read_bytes()).hexdigest()==h,rel
cells=json.loads((root/'records.json').read_text());assert len(cells)==35 and all(c['cleanup']['all_zero'] for c in cells)
checks=[]
fields=['transport_sessions_current_live','service_channels_current_live','application_streams_current_live','nbsr_tasks_current_live','quic_connections_current_live','quic_streams_current_live','pending_routes_current_entries','channel_registry_current_entries','stream_registry_current_entries','audit_queue_current_entries','replay_state_current_entries']
for c in cells:
 d=root/'raw/rust-rust'/c['name'];source=[json.loads(x) for x in (d/'source-0.stdout').read_text().splitlines() if x.startswith('{')];ready=[x for x in source if x.get('phase')=='b3_materialized_streams_ready'];final=[x for x in source if x.get('phase')=='lifecycle_cleanup'];assert len(ready)==len(final)==1
 dest=json.loads((d/'destination-0.active.json').read_text());expected=c['active_count']
 for s in [ready[0],dest]:assert s['quic_streams_current_live']==s['application_streams_current_live']==expected and s['service_channels_current_live']==32
 assert sum(x.get('success') is True for x in source)==expected
 dest_final=[json.loads(x) for x in (d/'destination-diagnostics.ndjson').read_text().splitlines() if x.startswith('{')][-1]
 for s in [final[0],dest_final]:assert all(type(s.get(k)) is int and s[k]==0 for k in fields)
 checks.append({'name':c['name'],'materialized_streams_per_role':expected,'channels_per_role':32,'validated_completions':expected,'all_11_final_counters_zero':True,'source_audit_high_water':final[0]['audit_queue_high_water_entries'],'destination_audit_high_water':dest_final['audit_queue_high_water_entries']})
a=analyze_scale(cells);assert all(x['repeat_gate'] for s in a for x in s['points'])
for name,obj in [('analysis.json',a),('ownership-validation.json',checks),('external-input.json',{'raw_path':str(root),'raw_index_sha256':hashlib.sha256(index.read_bytes()).hexdigest(),'verified_artifacts':len(lines),'valid_cells':len(cells)})]:
 (p/name).write_text(json.dumps(obj,indent=2)+'\n',newline='\n')
for src,dst in [('environment.json','environment.json'),('checksums.sha256','raw-checksums.sha256')]: (p/dst).write_text((root/src).read_text(),newline='\n')
print('raw_hashes',len(lines),'valid_cells',len(cells))
for role in a:
 print(role['role'],'active_slope',role['derived_active_private_slope_bytes_per_unit'],'incremental_slope',role['derived_incremental_private_slope_bytes_per_unit'],'maximum_point',{k:role['points'][-1][k] for k in ['count','active_private_median','active_private_range','active_private_cv_percent']})
