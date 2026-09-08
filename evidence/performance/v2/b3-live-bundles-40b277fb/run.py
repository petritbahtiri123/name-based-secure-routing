import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tarfile

out, build, repo = Path('/out'), Path('/build'), Path('/tmp/source')
sha = (build / 'source-sha.txt').read_text().strip()
with (out / 'setup.log').open('x') as log:
    for argv in (
        ['git', 'clone', '--no-checkout', '/old/source-full.bundle', str(repo)],
        ['git', '-C', str(repo), 'fetch', str(build / 'update.bundle'), 'HEAD'],
        ['git', '-C', str(repo), 'sparse-checkout', 'set', 'scripts', 'crates', 'config', 'docs'],
        ['git', '-C', str(repo), 'checkout', '--detach', sha],
    ):
        subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, check=True)
Path('/work').mkdir()
for archive in ('crates.tar', 'vectors.tar'):
    with tarfile.open(build / archive) as stream:
        stream.extractall('/work', filter='data')
bins = Path('/tmp/build/release')
bins.parent.mkdir()
shutil.copytree(build / 'binaries', bins)
for binary in bins.iterdir():
    binary.chmod(0o755)
for base, dirs, files in os.walk(repo):
    os.chown(base, 65532, 65532)
    for name in dirs + files:
        os.chown(Path(base) / name, 65532, 65532)
os.setgroups([])
os.setgid(65532)
os.setuid(65532)
os.environ['XDG_CONFIG_HOME'] = '/tmp/nbsr-empty-config'
sys.path.insert(0, str(repo))


results=[]
for label, axis, counts, repeats in [('live-materialized', 'live-bundles', [512,1024],5), ('cycles-100', 'cycles',[100],5)]:
    argv=[sys.executable,'-B','-m','scripts.run_b3_v2','--platform','linux','--target','/tmp/build','--build-manifest',str(build/'build-manifest.json'),'--output',str(out/label),'--cores','1','--axis',axis,'--counts',*[str(v) for v in counts],'--repeats',str(repeats),'--materialized-streams']
    (out/(label+'-command.json')).write_text(json.dumps(argv,indent=2))
    print(label,flush=True)
    with (out/(label+'.log')).open('x') as log:
        result=subprocess.run(argv,cwd=repo,stdout=log,stderr=subprocess.STDOUT)
    results.append(dict(label=label,exit_code=result.returncode))
    (out/'results.json').write_text(json.dumps(results,indent=2))
    print(results[-1],flush=True)
