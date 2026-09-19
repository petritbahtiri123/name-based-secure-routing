import os,shutil,subprocess,tarfile
from pathlib import Path
out,build,repo=Path('/out'),Path('/build'),Path('/tmp/source')
sha=(build/'source-sha.txt').read_text().strip()
with (out/'setup.log').open('x') as log:
 for argv in (['git','clone','--no-checkout','/old/source-full.bundle',str(repo)],['git','-C',str(repo),'fetch',str(build/'update.bundle'),'HEAD'],['git','-C',str(repo),'sparse-checkout','set','scripts','crates','config','docs'],['git','-C',str(repo),'checkout','--detach',sha]):
  subprocess.run(argv,stdout=log,stderr=subprocess.STDOUT,check=True)
Path('/work').mkdir()
for archive in ('crates.tar','vectors.tar'):
 with tarfile.open(build/archive) as f:f.extractall('/work',filter='data')
shutil.copytree(build/'binaries',Path('/tmp/binaries'))
for p in Path('/tmp/binaries').iterdir():p.chmod(0o755)
for base,dirs,files in os.walk(repo):
 os.chown(base,65532,65532)
 for name in dirs+files:os.chown(Path(base)/name,65532,65532)
print('PREPARED_NONROOT_PEER_SOURCE',sha,flush=True)
