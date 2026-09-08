import json
from pathlib import Path
import subprocess
import sys
repo=Path('C:/Users/bajra/OneDrive/Documents/NBSR')
out=Path(__file__).parent
sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
assert sha=='07096c080cd5759d7da470667f559583707e50c1'
assert not subprocess.check_output(['git','status','--porcelain'],cwd=repo,text=True)
base=[sys.executable,'-B','-m','scripts.run_b5_v2','--target','C:/NBSR-build/b5-pretouch-windows-target-506ddfa1','--cores','1','--groups','1','--depth','1','--warmup','3','--duration','120','--progress','30']
cases=[]
for repeat in range(1,4):
    for path in (('direct','nbsr') if repeat%2 else ('nbsr','direct')):
        label=f'historical-rate-{path}-r{repeat}'
        cases.append((label,base+['--output',str(out/label),'--diagnostic','--paths',path,'--rate','5206274500000','150044089','--streams','32','--payload','1024']))
label='reference-16k8-short-preflight'
cases.append((label,base+['--output',str(out/label),'--reference','C:/NBSR-build/windows-reference-16k8-07096c08','--paths','nbsr','--percent','70','--streams','8','--payload','16384']))
(out/'definition.json').write_text(json.dumps(dict(source_sha=sha,historical_rate_scope='Fixed 2d7525f3 load and shape, no current capacity inference',preflight_scope='Current-source reference loader must qualify 16k8; 120 seconds is not a 60/120-minute soak',cases=[dict(label=label,argv=argv) for label,argv in cases]),indent=2))
results=[]
for label,argv in cases:
    print(label,flush=True)
    with (out/(label+'.log')).open('x') as log:
        result=subprocess.run(argv,cwd=repo,stdout=log,stderr=subprocess.STDOUT)
    results.append(dict(label=label,exit_code=result.returncode))
    (out/'results.json').write_text(json.dumps(results,indent=2))
    print(results[-1],flush=True)
assert not subprocess.check_output(['git','status','--porcelain'],cwd=repo,text=True)
