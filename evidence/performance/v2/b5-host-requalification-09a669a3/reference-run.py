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

argv=[sys.executable,'-B','-m','scripts.performance.linux_b5_reference','--binaries',str(bins),'--build-manifest',str(build/'build-manifest.json'),'--output',str(out/'reference'),'--payload-bytes','1024','--streams','32','--depths','1','2','4','--warmup','3','--duration','30']
(out/'command.json').write_text(json.dumps(argv,indent=2))
print('CURRENT_REFERENCE_START',flush=True)
with (out/'reference.log').open('x') as log:
 result=subprocess.run(argv,cwd=repo,stdout=log,stderr=subprocess.STDOUT)
(out/'result.json').write_text(json.dumps(dict(exit_code=result.returncode)))
print('CURRENT_REFERENCE_END',result.returncode,flush=True)
