import sys,json,subprocess,hashlib
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from scripts.performance.b5_ceiling import load_ceiling
reference=Path('C:/NBSR-build/physical-core-16k8-cbdca987')
env=json.loads((reference/'environment.json').read_text())
sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
assert not subprocess.check_output(['git','status','--porcelain'],text=True)
rate=load_ceiling(reference,current_sha=sha,binary_sha256=env['binary_sha256'],shape=dict(physical_cores=1,endpoint_groups=1,streams_per_group=8,payload_bytes=16384,runtime_workers=1),percent=70,depth=1)
root=Path('C:/NBSR-build/b5-observer-16k8-cbdca987')
root.mkdir(exist_ok=False)
(root/'definition.json').write_text(json.dumps(dict(classification='DIAGNOSTIC_OBSERVER_QUALIFICATION',reference=rate,repeats=3,comparison_gate='absolute median goodput and p99 deltas <=5%; expand to five when CV >5%; retain every abort',duration_seconds=120,progress_seconds=30,ownership_states=['off','on']),indent=2))
results=[]
try:
 for repeat in range(1,4):
  for observed in ((False,True) if repeat%2 else (True,False)):
   name=('on' if observed else 'off')+f'-r{repeat}'
   command=[sys.executable,'scripts/run_b5_v2.py','--output',str(root/name),'--diagnostic','--paths','nbsr','--rate',str(rate['rate_numerator']),str(rate['rate_denominator']),'--cores','1','--groups','1','--streams','8','--payload','16384','--depth','1','--warmup','3','--duration','120','--progress','30']
   if observed: command.append('--ownership-sampling')
   print(name,flush=True)
   with (root/(name+'.log')).open('wb') as log:
    result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
   results.append(dict(name=name,command=command,exit_code=result.returncode))
   (root/'execution.json').write_text(json.dumps(results,indent=2))
   if result.returncode: raise RuntimeError('Retained failed diagnostic: '+name)
finally:
 with (root/'checksums.sha256').open('w',newline='\n') as out:
  for p in sorted(root.rglob('*')):
   if p.is_file() and p != root/'checksums.sha256':
    with p.open('rb') as f: digest=hashlib.file_digest(f,'sha256').hexdigest()
    out.write(digest+'  '+p.relative_to(root).as_posix()+'\n')
