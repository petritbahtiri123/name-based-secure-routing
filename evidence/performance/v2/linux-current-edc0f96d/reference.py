import json,os,shutil,subprocess,sys
from pathlib import Path
root=Path('/evidence');repo=Path('/tmp/nbsr-source');bins=Path('/tmp/nbsr-binaries')
sha=(root/'source-sha.txt').read_text().strip()
with (root/'reference-setup.log').open('w') as log:
 subprocess.run(['git','clone','--no-checkout',str(root/'source-full.bundle'),str(repo)],stdout=log,stderr=subprocess.STDOUT,check=True)
 subprocess.run(['git','sparse-checkout','set','scripts','crates','config','docs'],cwd=repo,stdout=log,stderr=subprocess.STDOUT,check=True)
 subprocess.run(['git','checkout','--detach',sha],cwd=repo,stdout=log,stderr=subprocess.STDOUT,check=True)
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()==sha
assert not subprocess.check_output(['git','status','--porcelain'],cwd=repo,text=True)
shutil.copytree(root/'binaries',bins)
for f in bins.iterdir():f.chmod(0o755)
argv=[sys.executable,'-B','-m','scripts.performance.linux_b5_reference','--binaries',str(bins),'--build-manifest',str(root/'build-manifest.json'),'--output',str(root/'reference-1k32'),'--payload-bytes','1024','--streams','32','--depths','1','2','4','--warmup','3','--duration','30']
with (root/'reference.log').open('w') as log:subprocess.run(argv,cwd=repo,stdout=log,stderr=subprocess.STDOUT,check=True)
print('REFERENCE_READY: /evidence/reference-1k32',flush=True)
