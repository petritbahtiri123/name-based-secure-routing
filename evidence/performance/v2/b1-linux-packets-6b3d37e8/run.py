import json,os,shutil,subprocess,sys,tarfile
from pathlib import Path
out,build,repo=Path('/out'),Path('/build'),Path('/tmp/source')
sha=(build/'source-sha.txt').read_text().strip()
with (out/'setup.log').open('x') as log:
 for argv in (['git','clone','--no-checkout','/old/source-full.bundle',str(repo)],['git','-C',str(repo),'fetch',str(build/'update.bundle'),'HEAD'],['git','-C',str(repo),'sparse-checkout','set','scripts','crates','config','docs'],['git','-C',str(repo),'checkout','--detach',sha]):
  subprocess.run(argv,stdout=log,stderr=subprocess.STDOUT,check=True)
Path('/work').mkdir()
for archive in ('crates.tar','vectors.tar'):
 with tarfile.open(build/archive) as stream:stream.extractall('/work',filter='data')
bins=Path('/tmp/binaries');shutil.copytree(build/'binaries',bins)
for binary in bins.iterdir():binary.chmod(0o755)
os.environ['XDG_CONFIG_HOME']='/tmp/nbsr-empty-config'
os.environ.pop('NBSR_BENCH_UDP_RECEIVE_BUFFER_BYTES',None)
argv=[sys.executable,'-B','-m','scripts.performance.linux_b1_capture','--binaries',str(bins),'--build-manifest',str(build/'build-manifest.json'),'--output','/out/cohort','--operations','1000']
(out/'command.json').write_text(json.dumps(argv,indent=2))
print('DOCKER_WSL_PACKET_ACCOUNTING_ROOT_FIXTURE_NOT_PERFORMANCE',flush=True)
raise SystemExit(subprocess.call(argv,cwd=repo))

