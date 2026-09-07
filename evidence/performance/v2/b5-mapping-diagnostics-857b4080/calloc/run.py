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

import time

def descendants(pid):
    found = []
    try:
        children = Path(f'/proc/{pid}/task/{pid}/children').read_text().split()
    except FileNotFoundError:
        return found
    for child in children:
        child = int(child)
        found.append(child)
        found.extend(descendants(child))
    return found

def mapping_summary(pid):
    rows = []
    for line in Path(f'/proc/{pid}/smaps').read_text().splitlines():
        fields = line.split()
        if '-' in fields[0] and len(fields) >= 5:
            rows.append(dict(address_range=fields[0], name=' '.join(fields[5:]) or '[anonymous]', permission=fields[1]))
        elif fields[0] in ('Size:', 'Rss:', 'Private_Clean:', 'Private_Dirty:', 'Anonymous:'):
            rows[-1][fields[0][:-1]] = int(fields[1]) * 1024
    return rows

results = []
for repeat in range(1, 4):
    name = f'mappings-r{repeat}'
    argv = [sys.executable, '-B', '-m', 'scripts.performance.linux_b5_campaign',
        '--binaries', str(bins), '--build-manifest', str(build / 'build-manifest.json'),
        '--output', str(out / name), '--diagnostic', '--rate',
        str(target['rate_numerator']), str(target['rate_denominator']),
        '--paths', 'nbsr', '--payload', '1024', '--streams', '32', '--depth', '1',
        '--duration', '120', '--warmup', '3', '--progress', '10']
    (out / (name + '-command.json')).write_text(json.dumps(argv, indent=2))
    print(name, flush=True)
    with (out / (name + '.log')).open('x') as log, (out / (name + '-mappings.ndjson')).open('x') as captures:
        environment = dict(os.environ, LD_PRELOAD='/out/calloc_trace.so', NBSR_CALLOC_TRACE=f'/out/{name}-calloc.txt')
        process = subprocess.Popen(argv, cwd=repo, stdout=log, stderr=subprocess.STDOUT, env=environment)
        next_sample = time.monotonic()
        while process.poll() is None:
            if time.monotonic() >= next_sample:
                for pid in descendants(process.pid):
                    started = time.monotonic_ns()
                    try:
                        command = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
                        role = next((role for role, binary in NAMES.items() if command and command[0] == str(bins / binary).encode()), None)
                        if role is None:
                            continue
                        mappings = mapping_summary(pid)
                        captures.write(json.dumps(dict(pid=pid, role=role, timestamp_ns=started,
                            capture_duration_ns=time.monotonic_ns()-started, mappings=mappings))+'\n')
                    except (FileNotFoundError, ProcessLookupError, PermissionError) as error:
                        captures.write(json.dumps(dict(pid=pid, timestamp_ns=started, error=repr(error)))+'\n')
                captures.flush()
                next_sample = time.monotonic() + 10
            time.sleep(.1)
        results.append(dict(repeat=repeat, exit_code=process.returncode,
            classification='DIAGNOSTIC_ONLY_OBSERVER_UNQUALIFIED'))
        (out / 'results.json').write_text(json.dumps(results, indent=2))
print('MAPPING_DIAGNOSTICS_RETAINED', flush=True)
