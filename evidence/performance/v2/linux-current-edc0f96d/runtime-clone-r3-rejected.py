import json,os,shutil,subprocess,sys
from pathlib import Path
root=Path('/evidence');repo=Path('/tmp/nbsr-source');bins=Path('/tmp/nbsr-binaries')
sha=(root/'source-sha.txt').read_text().strip()
with (root/'runtime-setup.log').open('w') as log:
 subprocess.run(['git','clone','--no-checkout',str(root/'source-full.bundle'),str(repo)],stdout=log,stderr=subprocess.STDOUT,check=True)
 subprocess.run(['git','checkout','--detach',sha],cwd=repo,stdout=log,stderr=subprocess.STDOUT,check=True)
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()==sha
assert not subprocess.check_output(['git','status','--porcelain'],cwd=repo,text=True)
shutil.copytree(root/'binaries',bins)
for f in bins.iterdir():f.chmod(0o755)
for repeat in range(1,4):
 argv=[sys.executable,'-B','-m','scripts.performance.linux_b5_campaign','--binaries',str(bins),'--build-manifest',str(root/'build-manifest.json'),'--output',str(root/f'compat-r{repeat}'),'--diagnostic','--rate','1000','1','--paths','direct','nbsr','--ownership-sampling','--payload','1024','--streams','32','--depth','1','--warmup','3','--duration','10','--progress','2']
 print(f'compat repeat={repeat}',flush=True)
 with (root/f'compat-r{repeat}.log').open('w') as log:subprocess.run(argv,cwd=repo,stdout=log,stderr=subprocess.STDOUT,check=True)
print('COMPATIBILITY_READY: /evidence',flush=True)
