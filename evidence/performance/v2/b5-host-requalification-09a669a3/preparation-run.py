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
bins = Path('/tmp/binaries')
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
from scripts.performance.linux_b5_ceiling import NAMES, current_environment, load_reference
from scripts.performance.linux_loopback import digest
target = dict(rate_numerator=6676826000000, rate_denominator=85751993, calibration_sha='8779e69cfd7fe5cb244aba2f3e96e785c3dd47eb', run_sha=sha, classification='FIXED_RATE_DIAGNOSTIC_NOT_CURRENT_CALIBRATION')
(out / 'target.json').write_text(json.dumps(target, indent=2))

results=[]
for repeat in range(1,4):
    for warmup in ([3,60] if repeat % 2 else [60,3]):
        name=f'warmup-{warmup}-r{repeat}'
        argv=[sys.executable,'-B','-m','scripts.performance.linux_b5_campaign', '--binaries',str(bins),'--build-manifest',str(build/'build-manifest.json'), '--output',str(out/name),'--diagnostic','--rate',str(target['rate_numerator']),str(target['rate_denominator']), '--paths','nbsr','--payload','1024','--streams','32','--depth','1','--duration','120','--warmup',str(warmup),'--progress','10']
        (out/(name+'-command.json')).write_text(json.dumps(argv,indent=2))
        print(name,flush=True)
        with (out/(name+'.log')).open('x') as log:
            result=subprocess.run(argv,cwd=repo,stdout=log,stderr=subprocess.STDOUT)
        results.append(dict(name=name,warmup=warmup,repeat=repeat,exit_code=result.returncode,classification='DIAGNOSTIC_PREPARATION_COMPARISON_NOT_CAPACITY'))
        (out/'results.json').write_text(json.dumps(results,indent=2))
        print(results[-1],flush=True)
