import hashlib,json,shutil,statistics,subprocess,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from scripts import run_max_throughput_v2_stage4 as s,run_p2a_established as p2a
from scripts.performance.authority import write_loopback_authority
from scripts.profile_b2_v2 import windows_processor_topology
from scripts.run_physical_core_v2 import placement
from scripts.run_b4b_task4k import checksums
root=Path('C:/NBSR-build/p2a-ownership-observer-564df326');root.mkdir(exist_ok=False)
status=subprocess.check_output(['git','status','--porcelain'],text=True);assert not status,status
binaries=p2a.build(Path('C:/NBSR-build/b4b-task4k'))
(root/'binaries').mkdir()
for role,b in list(binaries.items()):
 dst=root/'binaries'/b.name;shutil.copyfile(b,dst);binaries[role]=dst
shutil.copyfile(__file__,root/'runner.py')
t=windows_processor_topology()
meta={'schema':'nbsr-post-close-observer-v1','repository_sha':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'git_status':status,'topology':t,'binary_sha256':{k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in binaries.items()},'duration_seconds':30,'warmup_seconds':3,'repeats':5,'path':'nbsr','order':'off/on odd; on/off even','observer':'optional destination ownership counters enabled before setup; source post-close report','threshold':{'absolute_median_goodput_change':0.05,'absolute_median_p99_change':0.05},'scope':'Windows loopback paired observer control; not Direct comparison; no hardware ceiling inference'}
(root/'environment.json').write_text(json.dumps(meta,indent=2)+'\n',newline='\n')
rows=[];analysis={}
try:
 with tempfile.TemporaryDirectory(prefix='nbsr-observer-') as tmp:
  authority=Path(tmp)/'authority';write_loopback_authority(authority)
  for name,cores,groups,payload,streams in [('1core-1k64',1,1,1024,64),('4core-16k1',4,4,16384,1)]:
   for repeat in range(1,6):
    for enabled in ([False,True] if repeat%2 else [True,False]):
     mode='on' if enabled else 'off';raw=root/name/mode;raw.mkdir(parents=True,exist_ok=True)
     print(name,mode,repeat,flush=True)
     r=s.run_repeat(dict(path='nbsr',payload_bytes=payload,streams_per_group=streams,outstanding_per_stream=1,endpoint_groups=groups,runtime_workers=1),repeat,binaries,authority,3,30,raw,t,placement=placement(t,cores,groups),ownership_reports=enabled)
     r.update(observer=mode,shape=name);rows.append(r)
     (root/'records.json').write_text(json.dumps(rows,indent=2)+'\n',newline='\n')
     assert r['valid'], 'invalid run retained; observer sequence stopped'
   modes={m:[r for r in rows if r['shape']==name and r['observer']==m] for m in ['off','on']}
   delta={field:statistics.median(r[field] for r in modes['on'])/statistics.median(r[field] for r in modes['off'])-1 for field in ['aggregate_application_gbps','p99_latency_ns']}
   analysis[name]={'median_relative_changes':delta,'observer_gate':'PASS' if all(abs(x)<=.05 for x in delta.values()) else 'FAIL','ownership_all_zero':all(r['ownership_cleanup']['classification']=='PASS' for r in modes['on']),'cv':{m:statistics.stdev(r['aggregate_application_gbps'] for r in rs)/statistics.mean(r['aggregate_application_gbps'] for r in rs) for m,rs in modes.items()}}
   (root/'analysis.json').write_text(json.dumps(analysis,indent=2)+'\n',newline='\n')
   print(name,analysis[name],flush=True)
finally:checksums(root)
