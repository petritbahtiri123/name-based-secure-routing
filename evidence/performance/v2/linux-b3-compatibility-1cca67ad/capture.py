import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import time

root = Path(__file__).parent
name = 'nbsr-b3-linux-1cca67ad-r2'
deadline = time.monotonic() + 600
last = ''
while time.monotonic() < deadline:
    result = subprocess.run(['docker', 'logs', name], capture_output=True, check=True)
    output = result.stdout.decode()
    if output != last:
        print(output[len(last):], end='', flush=True)
        last = output
    if 'READY_FOR_EVIDENCE_COPY' in output:
        break
    time.sleep(2)
else:
    raise RuntimeError('bounded wrapper readiness deadline')
(root / 'container.stdout.log').write_bytes(result.stdout)
(root / 'container.stderr.log').write_bytes(result.stderr)
with (root / 'evidence.tar').open('wb') as stdout, (root / 'tar.stderr.log').open('wb') as stderr:
    subprocess.run(['docker', 'exec', name, 'tar', '-C', '/evidence', '-cf', '-', '.'],
                   stdout=stdout, stderr=stderr, check=True, timeout=45)
captured = root / 'captured'
captured.mkdir()
with tarfile.open(root / 'evidence.tar') as archive:
    archive.extractall(captured, filter='data')
indexes = list(captured.rglob('checksums.sha256'))
assert len(indexes) == 5, len(indexes)
checked = 0
for index in indexes:
    for line in index.read_text().splitlines():
        expected, relative = line.split('  ', 1)
        path = (index.parent / relative).resolve()
        assert path.is_relative_to(captured.resolve()) and path.is_file()
        with path.open('rb') as stream:
            assert hashlib.file_digest(stream, 'sha256').hexdigest() == expected, relative
        checked += 1
analyses = list(captured.glob('*/analysis.json'))
assert len(analyses) == 4
summary = []
for path in analyses:
    analysis = json.loads(path.read_text())
    assert analysis['classification'] == 'DIAGNOSTIC_BINARY_SOURCE_MISMATCH'
    assert analysis['inputs'][0]['checksums_sha256'] == hashlib.sha256((path.parent / 'analysis-input-checksums.txt').read_bytes()).hexdigest()
    rows = json.loads((path.parent / 'records.json').read_text())
    assert len(rows) == 3 and all(row['cleanup']['all_zero'] for row in rows)
    if path.parent.name == 'cycles-3':
        assert all(row['cleanup']['source_cycle_all_zero'] for row in rows)
    summary.append(dict(shape=path.parent.name, valid_repeats=len(rows),
        classification=analysis['classification'],
        scale_repeat_gates=[dict(role=r['role'], cv_percent=r['points'][0]['active_private_resident_cv_percent'],
            repeat_gate=r['points'][0]['repeat_gate']) for r in analysis['scale']]))
validation = dict(status='CAPTURE_HASHES_AND_12_CLEANUP_RUNS_PASS', checksums_verified=checked,
    captured_file_count=sum(p.is_file() for p in captured.rglob('*')), results=summary)
(root / 'capture-validation.json').write_text(json.dumps(validation, indent=2))
print(json.dumps(validation), flush=True)
subprocess.run(['docker', 'exec', name, 'python3', '-c',
    "from pathlib import Path; Path('/tmp/evidence-copied').touch()"], check=True, timeout=10)
exit_code = subprocess.check_output(['docker', 'wait', name], timeout=15)
(root / 'container.exit.txt').write_bytes(exit_code)
(root / 'container-after.json').write_bytes(subprocess.check_output(['docker', 'inspect', name]))
assert exit_code.strip() == b'0'
