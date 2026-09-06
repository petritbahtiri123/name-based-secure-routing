"""Tar-before-release adaptation of the accepted B3 capture.py; no empty-copy PASS."""
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import time

root = Path(__file__).parent
name = 'nbsr-b4-fd-9397429f'
identifier = (root/'container-id.txt').read_text().strip()
before = json.loads(subprocess.check_output(['docker', 'inspect', identifier], timeout=15))[0]
assert before['Name'] == '/' + name and before['Id'] == identifier
assert before['Config']['Labels']['nbsr.compatibility.run'] == name
deadline = time.monotonic() + 1800
while time.monotonic() < deadline:
    result = subprocess.run(['docker', 'logs', identifier], capture_output=True, check=True, timeout=15)
    if b'READY_FOR_EVIDENCE_COPY' in result.stdout:
        break
    if not json.loads(subprocess.check_output(['docker', 'inspect', identifier], timeout=15))[0]['State']['Running']:
        raise RuntimeError('container exited before verified transfer')
    time.sleep(2)
else:
    raise RuntimeError('bounded compatibility capture deadline')
(root/'container.stdout.log').write_bytes(result.stdout)
(root/'container.stderr.log').write_bytes(result.stderr)
with (root/'evidence.tar').open('xb') as stdout, (root/'tar.stderr.log').open('xb') as stderr:
    subprocess.run(['docker', 'exec', identifier, 'tar', '-C', '/evidence', '-cf', '-', '.'],
                   stdout=stdout, stderr=stderr, check=True, timeout=45)
assert (root/'evidence.tar').stat().st_size > 1024
captured = root/'captured'
captured.mkdir()
with tarfile.open(root/'evidence.tar') as archive:
    archive.extractall(captured, filter='data')
index = captured/'checksums.sha256'
entries = index.read_text().splitlines()
assert entries
seen = set()
for line in entries:
    expected, relative = line.split('  ', 1)
    path = (captured/relative).resolve()
    assert path.is_relative_to(captured.resolve()) and path.is_file() and relative not in seen
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, relative
    seen.add(relative)
assert seen == {p.relative_to(captured).as_posix() for p in captured.rglob('*') if p.is_file() and p != index}
assert (captured/'wrapper-result.json').is_file()
wrapper = json.loads((captured/'wrapper-result.json').read_text())
validation = {'transfer': 'NONEMPTY_HASH_VERIFIED', 'artifacts_verified': len(seen),
              'wrapper': wrapper, 'cohort_acceptance': 'PENDING_INDEPENDENT_REVIEW'}
(root/'capture-validation.json').write_text(json.dumps(validation, indent=2))
subprocess.run(['docker', 'exec', identifier, 'python3', '-c',
               "from pathlib import Path; Path('/tmp/evidence-copied').touch()"], check=True, timeout=10)
code = subprocess.check_output(['docker', 'wait', identifier], timeout=15)
(root/'container.exit.txt').write_bytes(code)
(root/'container-after.json').write_bytes(subprocess.check_output(['docker', 'inspect', identifier], timeout=15))
assert int(code.strip()) == wrapper['exit_code']
print(json.dumps(validation), flush=True)
