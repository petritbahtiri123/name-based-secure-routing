import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tarfile
import time

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
os.environ.pop('NBSR_BENCH_UDP_RECEIVE_BUFFER_BYTES',None)
target=dict(rate_numerator=64804600000000,rate_denominator=7500349701,calibration_sha='40b277fbbf6842f76094c0621f0a9fde0ee28f5a',run_sha=sha,classification='FIXED_RATE_DIAGNOSTIC_NOT_CURRENT_CALIBRATION')
(out/'target.json').write_text(json.dumps(target,indent=2))
results = []
required = 3
for repeat in range(1, 6):
    if repeat > required:
        break
    for placement in (('shared', 'split') if repeat % 2 else ('split', 'shared')):
        name = f'pair-r{repeat}-{placement}'
        argv = [sys.executable, '-B', '-m', 'scripts.performance.linux_b5_campaign',
                '--binaries', str(bins), '--build-manifest', str(build / 'build-manifest.json'),
                '--output', str(out / name), '--diagnostic', '--retain-failed-diagnostic',
                '--rate', str(target['rate_numerator']), str(target['rate_denominator']),
                '--paths', 'nbsr', '--payload', '16384', '--streams', '8', '--depth', '1',
                '--duration', '300', '--warmup', '3', '--progress', '30']
        argv.append('--ownership-sampling')
        argv += ['--placement', placement]
        (out / (name + '-command.json')).write_text(json.dumps(argv, indent=2))
        print(name, flush=True)
        with (out / (name + '.log')).open('x') as log:
            result = subprocess.run(argv, cwd=repo, stdout=log, stderr=subprocess.STDOUT)
        record_path = out / name / 'records.json'
        records = json.loads(record_path.read_text()) if record_path.exists() else []
        row = records[-1] if records else {}
        summary = dict(repeat=repeat, placement=placement, exit_code=result.returncode,
                       classification=row.get('classification', 'SETUP_FAILURE'),
                       complete_final='final' in row, gbps=row.get('gbps'),
                       continuous_ownership=row.get('continuous_ownership'),
                       gate_failure_count=len(row.get('diagnostic_gate_failures', [])))
        raw = out / name / 'raw/nbsr-r1/source.stdout.ndjson'
        latencies = []
        if raw.exists():
            for line in raw.read_text().splitlines():
                value = json.loads(line)
                if value.get('phase') == 'steady' and value.get('p99_latency_ns') is not None:
                    latencies.append(value['p99_latency_ns'])
        summary['window_p99_median_ns'] = statistics.median(latencies) if latencies else None
        results.append(summary)
        (out / 'results.json').write_text(json.dumps(results, indent=2))
        print(summary, flush=True)
        if not summary['complete_final']:
            raise RuntimeError('incomplete attempt retained; stop without replacement')
    if repeat == 3:
        dispersion = {}
        for placement in ('shared', 'split'):
            complete = [r for r in results if r['placement'] == placement and r['complete_final']]
            if len(complete) == 3:
                for field in ('gbps', 'window_p99_median_ns'):
                    values = [r[field] for r in complete]
                    if all(type(v) in (int, float) and v > 0 for v in values):
                        dispersion[placement + '/' + field] = statistics.stdev(values) / statistics.mean(values)
        if any(value > .05 for value in dispersion.values()):
            required = 5
        (out / 'repeat-decision.json').write_text(json.dumps(dict(required=required,
            cv=dispersion, classification='DIAGNOSTIC_ONLY'), indent=2))
(out / 'run-complete.json').write_text(json.dumps(dict(attempts=len(results), classification='DIAGNOSTIC_ONLY')))
