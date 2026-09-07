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

results = []
for axis, counts, options in (
    ('streams', [32,64,128,256,512,1024,2048], ['--fixed-channels','32','--materialized-streams']),
    ('bundles', [16,32,64,128,256,512], []),
    ('cycles', [3], ['--materialized-streams']),
):
    argv = [sys.executable, '-B', '-m', 'scripts.run_b3_v2', '--platform','linux',
        '--target','/tmp/build','--build-manifest',str(build/'build-manifest.json'),
        '--output',str(out/axis),'--cores','1','--axis',axis,'--counts',
        *map(str,counts),'--repeats','5',*options]
    (out/(axis+'-command.json')).write_text(json.dumps(argv,indent=2))
    print(axis,flush=True)
    with (out/(axis+'.log')).open('x') as log:
        result = subprocess.run(argv,cwd=repo,stdout=log,stderr=subprocess.STDOUT)
    results.append(dict(axis=axis,exit_code=result.returncode))
    (out/'results.json').write_text(json.dumps(results,indent=2))
    if result.returncode:
        print(f'{axis}: FAILED; preserved without replacement',flush=True)
    else:
        print(f'{axis}: completed',flush=True)
print('B3_ATTEMPTS_RETAINED',flush=True)
