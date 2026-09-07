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
def cv(values):
    return statistics.stdev(values) / statistics.mean(values)
rows = []
required = 3
for repeat in range(1, 6):
    if repeat > required:
        break
    for observer in (('off', 'on') if repeat % 2 else ('on', 'off')):
        name = f'{observer}-r{repeat}'
        argv = [sys.executable, '-B', '-m', 'scripts.performance.linux_b5_campaign',
            '--binaries', str(bins), '--build-manifest', str(build / 'build-manifest.json'),
            '--output', str(out / name), '--diagnostic', '--rate',
            str(target['rate_numerator']), str(target['rate_denominator']),
            '--paths', 'nbsr', '--payload', '1024', '--streams', '32', '--depth', '1',
            '--duration', '120', '--warmup', '3', '--progress', '10']
        if observer == 'on':
            argv.append('--ownership-sampling')
        print(name, flush=True)
        (out / (name + '-command.json')).write_text(json.dumps(argv, indent=2))
        with (out / (name + '.log')).open('x') as log:
            completed = subprocess.run(argv, cwd=repo, stdout=log, stderr=subprocess.STDOUT)
        if completed.returncode:
            (out / 'failure.json').write_text(json.dumps(dict(phase=name, exit_code=completed.returncode,
                classification='INVALID_PARTIAL_NO_REPLACEMENT'), indent=2))
            raise SystemExit(completed.returncode)
        row = json.loads((out / name / 'records.json').read_text())[0]
        assert row['valid']
        rows.append(dict(observer=observer, repeat=repeat, gbps=row['gbps'], p99=row['window_p99_median_ns']))
        (out / 'comparison-rows.json').write_text(json.dumps(rows, indent=2))
        print(json.dumps(rows[-1]), flush=True)
    if repeat == 3:
        if any(cv([r[field] for r in rows if r['observer'] == observer]) > .05
               for observer in ('off', 'on') for field in ('gbps', 'p99')):
            required = 5
medians = {observer: {field: statistics.median(r[field] for r in rows if r['observer'] == observer)
    for field in ('gbps', 'p99')} for observer in ('off', 'on')}
impact = {field: abs(medians['on'][field] / medians['off'][field] - 1) for field in ('gbps', 'p99')}
dispersion = {observer: {field: cv([r[field] for r in rows if r['observer'] == observer])
    for field in ('gbps', 'p99')} for observer in ('off', 'on')}
passed = all(v <= .05 for v in impact.values()) and all(v <= .05 for fields in dispersion.values() for v in fields.values())
(out / 'comparison.json').write_text(json.dumps(dict(scope='ownership-observer only; smaps resource observer always present',
    classification='PASS' if passed else 'REJECTED_OBSERVER_COMPARISON', medians=medians,
    absolute_impact=impact, cv=dispersion, repeats=required), indent=2))
print('COMPARISON_READY', flush=True)
