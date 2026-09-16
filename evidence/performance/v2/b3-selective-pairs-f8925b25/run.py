import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time

out = Path('/out')
variants = {}
with (out / 'setup.log').open('x') as log:
    for mode in ('before', 'after'):
        build = Path('/' + mode)
        repo = Path('/tmp/' + mode + '-source')
        sha = (build / 'source-sha.txt').read_text().strip()
        for argv in (
            ['git', 'clone', '--no-checkout', '/old/source-full.bundle', str(repo)],
            ['git', '-C', str(repo), 'fetch', str(build / 'update.bundle'), 'HEAD'],
            ['git', '-C', str(repo), 'sparse-checkout', 'set', 'scripts', 'crates', 'config', 'docs'],
            ['git', '-C', str(repo), 'checkout', '--detach', sha],
        ):
            subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, check=True)
        bins = Path('/tmp/' + mode + '-build/release')
        bins.parent.mkdir()
        shutil.copytree(build / 'binaries', bins)
        for binary in bins.iterdir():
            binary.chmod(0o755)
        for base, dirs, files in os.walk(repo):
            os.chown(base, 65532, 65532)
            for name in dirs + files:
                os.chown(Path(base) / name, 65532, 65532)
        variants[mode] = dict(build=build, repo=repo, target=bins.parent, sha=sha)
Path('/work').mkdir()
for archive in ('crates.tar', 'vectors.tar'):
    with tarfile.open(Path('/after') / archive) as stream:
        stream.extractall('/work', filter='data')
os.setgroups([])
os.setgid(65532)
os.setuid(65532)
os.environ['XDG_CONFIG_HOME'] = '/tmp/nbsr-empty-config'
os.environ.pop('NBSR_BENCH_UDP_RECEIVE_BUFFER_BYTES', None)


def snapshot(label):
    data = dict(scope='pre/post only; no timed profiler', monotonic_ns=time.monotonic_ns(), clock_ticks_per_second=os.sysconf('SC_CLK_TCK'))
    for path in ('/proc/net/snmp', '/proc/net/netstat', '/sys/fs/cgroup/cpu.stat',
                 '/sys/fs/cgroup/memory.peak', '/sys/fs/cgroup/memory.events'):
        data[path] = Path(path).read_text()
    space = os.statvfs(out)
    data['output_free_bytes'] = space.f_bavail * space.f_frsize
    (out / (label + '-counters.json')).write_text(json.dumps(data, indent=2))


def verify_copy(root):
    index = root / 'checksums.sha256'
    assert index.is_file(), 'runner must preserve its failure index too'
    count = 0
    for line in index.read_text().splitlines():
        expected, name = line.split('  ', 1)
        path = (root / name).resolve()
        assert path.is_relative_to(root.resolve()) and path.is_file()
        with path.open('rb') as stream:
            assert hashlib.file_digest(stream, 'sha256').hexdigest() == expected, str(path)
        count += 1
    return count


results = []
for repeat in range(1, 6):
    for mode in (('before', 'after') if repeat % 2 else ('after', 'before')):
        label = f'{mode}-r{repeat}'
        spec = variants[mode]
        case = Path('/tmp') / label
        argv = [sys.executable, '-B', '-m', 'scripts.run_b3_v2', '--platform', 'linux',
                '--target', str(spec['target']), '--build-manifest', str(spec['build'] / 'build-manifest.json'),
                '--output', str(case), '--cores', '1', '--axis', 'live-bundles', '--counts', '2048',
                '--repeats', '1', '--materialized-streams', '--accept-window', '1']
        (out / (label + '-command.json')).write_text(json.dumps(argv, indent=2))
        snapshot(label + '-before')
        print(label, flush=True)
        with (out / (label + '.log')).open('x') as log:
            result = subprocess.run(argv, cwd=spec['repo'], stdout=log, stderr=subprocess.STDOUT)
        snapshot(label + '-after')
        destination = out / label
        shutil.copytree(case, destination)
        verified = verify_copy(destination)
        results.append(dict(mode=mode, repeat=repeat, source_sha=spec['sha'], exit_code=result.returncode,
                            original_output=str(case), retained_output=str(destination), copied_files_verified=verified))
        (out / 'results.json').write_text(json.dumps(results, indent=2))
        print(results[-1], flush=True)
(out / 'copy-complete.json').write_text(json.dumps(dict(attempts=len(results), all_copies_verified=True)))
