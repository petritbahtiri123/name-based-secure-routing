from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tempfile

ROOT = Path('C:/Users/bajra/OneDrive/Documents/NBSR')
sys.path.insert(0, str(ROOT))
from scripts import run_max_throughput_v2_stage4 as stage4
from scripts.performance.authority import write_loopback_authority
from scripts.performance.b5_grouped import ProgressValidator
from scripts.performance.post_close_cleanup import validate_report

out = Path(sys.argv[1])
out.mkdir(exist_ok=False)
target = Path('C:/NBSR-build/b4b-task4k/release')
binaries = {key: target / name for key, name in (
    ('direct', 'perf_direct_peer.exe'), ('nbsr', 'perf_rust_source.exe'), ('server', 'wp8_interop_server.exe'))}
metadata = dict(scope='LIVE GREEN integration only; no capacity/observer claim',
                binary_sha256={k: hashlib.sha256(p.read_bytes()).hexdigest() for k, p in binaries.items()},
                base_sha=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip())
(out / 'environment.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8', newline='\n')
(out / 'source.patch').write_bytes(subprocess.check_output(['git', 'diff', '--binary'], cwd=ROOT))
for relative in ['src/bin/perf_direct_peer.rs', 'src/bin/perf_rust_source.rs', 'src/bin/b5_support/driver.rs', 'src/bin/b5_support/coordinator.rs', 'src/bin/b5_support/runtime.rs', 'src/bin/b5_support/paced.rs']:
    source = ROOT / 'crates/nbsr-transport' / relative
    dest = out / 'source' / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(source.read_bytes())
results = []
try:
    with tempfile.TemporaryDirectory(prefix='nbsr-b5-green-') as temp:
        authority = Path(temp) / 'authority'
        write_loopback_authority(authority)
        for mode in ('direct', 'nbsr'):
            for groups in (1, 2, 4):
                prefix = f'{mode}-g{groups}'
                cell = dict(path=mode, payload_bytes=16384, streams_per_group=1,
                            outstanding_per_stream=1, endpoint_groups=groups, runtime_workers=1)
                ack = out / f'{prefix}.ack'
                processes, handles, endpoints, reports = [], [], [], []
                try:
                    for group in range(groups):
                        ready, result = out / f'{prefix}-d{group}.ready.json', out / f'{prefix}-d{group}.result.json'
                        argv, env = stage4._server_command(cell, binaries, authority, ready, result, ack)
                        report = out / f'{prefix}-d{group}.cleanup.json'
                        if mode == 'nbsr': argv += ['--p2a-cleanup-report', str(report)]
                        stdout = (out / f'{prefix}-d{group}.stdout').open('w')
                        stderr = (out / f'{prefix}-d{group}.stderr').open('w')
                        handles.extend([stdout, stderr])
                        server = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=stdout, stderr=stderr, text=True)
                        processes.append(server)
                        endpoints.append(stage4.wait_ready(ready, server)['endpoint'])
                        if mode == 'nbsr': reports.append(('destination', server.pid, report))
                    common = ['--authority-dir', str(authority), '--endpoint', endpoints[0], '--p2a-endpoints', ','.join(endpoints),
                              '--payload-bytes', '16384', '--p2a-streams', '1', '--p2a-groups', str(groups),
                              '--p2a-runtime-workers', '1', '--p2a-outstanding-per-stream', '1',
                              '--p2a-warmup-seconds', '0.2', '--p2a-duration-seconds', '2', '--p2a-progress-seconds', '1',
                              '--b5-rate-numerator', '200', '--b5-rate-denominator', '1']
                    argv = [str(binaries['direct']), '--role', 'client', '--samples', '1', '--lifecycle', 'warm', *common] if mode == 'direct' else [str(binaries['nbsr']), '--samples', '1', *common]
                    report = out / f'{prefix}-source.cleanup.json'
                    if mode == 'nbsr': argv += ['--p2a-cleanup-report', str(report)]
                    stderr = (out / f'{prefix}-source.stderr').open('w')
                    handles.append(stderr)
                    client = subprocess.Popen(argv, cwd=ROOT, env=os.environ.copy(), stdout=subprocess.PIPE, stderr=stderr, text=True)
                    processes.append(client)
                    if mode == 'nbsr': reports.append(('source', client.pid, report))
                    stdout, _ = client.communicate(timeout=92)
                    (out / f'{prefix}-source.stdout').write_text(stdout, encoding='utf-8', newline='\n')
                    assert client.returncode == 0, f'{prefix}: source failed'
                    rows = [json.loads(line) for line in stdout.splitlines() if line.startswith('{')]
                    validator = ProgressValidator(groups, 16384)
                    progress = [r for r in rows if r.get('schema') == 'nbsr-b5-grouped-progress-v1']
                    finals = [r for r in rows if r.get('schema') == 'nbsr-b5-grouped-final-v1']
                    assert len(finals) == 1 and not any(r.get('schema') == 'nbsr-p2a-repeat-v2' for r in rows)
                    for row in progress: validator.accept(row)
                    validator.finish(finals[0])
                    assert finals[0]['offered'] == 400 and finals[0]['completed'] > 0
                    ack.write_text('source completed and validated\n')
                    for server in processes[:-1]:
                        assert server.wait(timeout=15) == 0
                    for role, pid, report in reports:
                        assert validate_report(json.loads(report.read_text()), role, pid), str(report)
                    result = dict(path=mode, groups=groups, progress_windows=len(progress), completed=finals[0]['completed'],
                                  offered=400, missed=finals[0]['missed'], cleanup='11-counter PASS every role' if mode == 'nbsr' else 'process exit only', result='PASS')
                    results.append(result)
                    print(result, flush=True)
                finally:
                    for process in processes:
                        if process.poll() is None:
                            process.kill()
                            process.wait(timeout=5)
                    for handle in handles: handle.close()
finally:
    (out / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8', newline='\n')
    (out / 'checksums.sha256').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out).as_posix()}\n' for p in sorted(out.rglob('*')) if p.is_file() and p.name != 'checksums.sha256'), encoding='utf-8', newline='\n')
