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

out = Path('C:/NBSR-build/b5-live-red-f9e36322')
out.mkdir(exist_ok=False)
target = Path('C:/NBSR-build/b4b-task4k/release')
binaries = {key: target / name for key, name in (
    ('direct', 'perf_direct_peer.exe'), ('nbsr', 'perf_rust_source.exe'), ('server', 'wp8_interop_server.exe'))}
prior = json.loads(Path('C:/NBSR-build/task4i-fresh-1917b195/environment.json').read_text())
hashes = {k: hashlib.sha256(p.read_bytes()).hexdigest() for k, p in binaries.items()}
assert hashes == prior['binary_sha256']
metadata = dict(scope='LIVE RED integration only; no timing claim; unrelated compilation allowed',
                binary_source_sha=prior['repository_sha'], binary_sha256=hashes,
                harness_sha=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip())
(out / 'environment.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8', newline='\n')
native = subprocess.Popen


def with_flags(argv, *args, **kwargs):
    if str(argv[0]) == str(binaries['nbsr']) or (str(argv[0]) == str(binaries['direct']) and '--role' in argv and argv[argv.index('--role') + 1] == 'client'):
        argv = [*argv, '--b5-rate-numerator', '200', '--b5-rate-denominator', '1', '--p2a-progress-seconds', '1']
    return native(argv, *args, **kwargs)


failures = []
topology = stage4.windows_processor_topology()
try:
    subprocess.Popen = with_flags
    with tempfile.TemporaryDirectory(prefix='nbsr-b5-red-') as temp:
        authority = Path(temp) / 'authority'
        write_loopback_authority(authority)
        for mode in ('direct', 'nbsr'):
            cell = dict(path=mode, payload_bytes=16384, streams_per_group=1,
                        outstanding_per_stream=1, endpoint_groups=2, runtime_workers=1)
            result = stage4.run_repeat(cell, 1, binaries, authority, .2, 2, out, topology,
                                      placement=dict(source_mask=5, endpoint_masks=[5, 5], logical_processors_available=2))
            assert result['valid'] and result['cleanup_pass']
            prefix = f'{mode}-p16384-s1-o1-eg2-r1'
            rows = [json.loads(line) for line in (out / f'{prefix}.stdout.jsonl').read_text().splitlines() if line.startswith('{')]
            final = [r for r in rows if r.get('schema') == 'nbsr-b5-grouped-final-v1']
            failures.append(dict(path=mode, expected_new_final_count=1, actual_new_final_count=len(final),
                                 old_final_count=sum(r.get('schema') == 'nbsr-p2a-repeat-v2' for r in rows)))
finally:
    subprocess.Popen = native
    (out / 'red-result.json').write_text(json.dumps(failures, indent=2), encoding='utf-8', newline='\n')
    (out / 'checksums.sha256').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out).as_posix()}\n' for p in sorted(out.rglob('*')) if p.is_file() and p.name != 'checksums.sha256'), encoding='utf-8', newline='\n')
print(json.dumps(failures, indent=2))
assert all(r['actual_new_final_count'] == r['expected_new_final_count'] for r in failures), 'LIVE RED: paced final schema absent'
