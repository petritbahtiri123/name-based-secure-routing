"""Read-only raw validation and compact external evidence packaging."""
from pathlib import Path
import hashlib
import json
import math
import statistics

RAW = Path('C:/NBSR-build/linux-smoke-preparation-3644c324')
OUT = Path(__file__).parent

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def write(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8', newline='\n')

indexes = []
for root, name, count in [(RAW, 'evidence-checksums.sha256', 91),
                          (RAW / 'captured/run', 'checksums.sha256', 61)]:
    index = root / name
    lines = index.read_text(encoding='utf-8-sig').splitlines()
    assert len(lines) == count
    seen = set()
    for line in lines:
        expected, relative = line.split('  ', 1)
        target = (root / relative).resolve()
        assert target.is_relative_to(root.resolve()) and target not in seen
        seen.add(target)
        assert digest(target) == expected, relative
    indexes.append(dict(root=str(root), name=name, sha256=digest(index), verified_artifacts=count))
    (OUT / ('raw-checksums.sha256' if count == 91 else 'runner-checksums.sha256')).write_bytes(index.read_bytes())

records = []
terminals = []
for directory in sorted((RAW / 'captured/run/raw').iterdir()):
    record = read(directory / 'record.json')
    assert record['valid'] is True and record['cleanup'] == 'PASS_PROCESS_EXIT'
    binary = record['binary_record']
    assert all(binary[key] == 0 for key in ('errors','missing','duplicates','corrupt','wrong_request'))
    computed = binary['completed_operations'] * 16 * binary['payload_bytes'] / binary['measured_ns']
    assert math.isclose(computed, record['aggregate_application_gbps'], rel_tol=1e-12)
    samples = [json.loads(line) for line in (directory / 'resources.ndjson').read_text().splitlines()]
    for role in ('client', 'server'):
        rows = [row for row in samples if row['role'] == role]
        last = rows[-1]
        assert len({(row['pid'], row['start_ticks']) for row in rows}) == 1
        assert last['state'] == 'Z' and last['fd_count'] is None
        assert last['fd_count_state'] == 'UNAVAILABLE_ZOMBIE'
        assert all(a['cpu_ns'] <= b['cpu_ns'] for a,b in zip(rows, rows[1:]))
        assert record['final_process_samples'][role] == {k:v for k,v in last.items() if k != 'role'}
        terminals.append(dict(cell=directory.name, role=role, samples=len(rows), **record['final_process_samples'][role]))
    records.append(dict(raw_cell=directory.name, **record))
assert len(records) == 6 and len(terminals) == 12
analysis = read(RAW / 'captured/run/analysis.json')
for cell in analysis['cells']:
    rows = [r for r in records if r['cell'] == cell['cell']]
    rates = [r['aggregate_application_gbps'] for r in rows]
    assert len(rows) == cell['valid_repeats'] == 3
    assert statistics.median(rates) == cell['median_gbps']
    assert statistics.stdev(rates) / statistics.mean(rates) == cell['cv']
assert analysis['status'] == 'PASS_LOOPBACK_CONTROL'

container = read(RAW / 'container-after.json')[0]
host = container['HostConfig']
assert container['State']['ExitCode'] == 0 and not container['State']['Running']
assert container['Config']['User'] == '65532:65532'
assert host['ReadonlyRootfs'] and host['NetworkMode'] == 'none'
assert host['CapDrop'] == ['ALL'] and 'no-new-privileges' in host['SecurityOpt']
assert host['NanoCpus'] == 1_000_000_000 and host['Memory'] == 1_073_741_824
security = dict(container_id=container['Id'], image=container['Image'],
                user=container['Config']['User'], state=container['State'],
                settings={k:host[k] for k in ('ReadonlyRootfs','NetworkMode','CapDrop','SecurityOpt','NanoCpus','Memory','PidsLimit','Tmpfs','Mounts')})
write('security-settings.json', security)
write('records.json', records)
write('terminal-validation.json', terminals)
for name, relative in [('analysis.json','captured/run/analysis.json'),
                       ('environment.json','captured/run/environment.json'),
                       ('manifest.json','captured/run/manifest.json'),
                       ('build-manifest.json','captured/build-manifest.json'),
                       ('container-scope.json','captured/container-scope.json')]:
    write(name, read(RAW / relative))
write('external-inputs.json', dict(raw_root=str(RAW), indexes=indexes,
      source_sha='3644c324a535586e89af72a8c9796e8d58fadf48',
      prior_failure='C:/NBSR-build/linux-smoke-preparation-6227fd86',
      frozen_source_bundle=str(RAW / 'source.bundle'),
      build_log=str(RAW / 'build.log'), compact_json='Normalized JSON; original bytes remain bound by raw index'))
write('validation.json', dict(valid_runs=6, terminal_process_samples=12,
      same_identity_final_cpu_preserved=True, final_fd_count='null / UNAVAILABLE_ZOMBIE',
      cleanup_scope='Process exit and terminal CPU/identity; no 11-counter ownership proof',
      classification='PASS_LOOPBACK_CONTROL', scope='Docker Desktop Linux VM compatibility only'))
print(json.dumps(dict(indexes=indexes, valid_runs=len(records), terminal_samples=len(terminals))))
