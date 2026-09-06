import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

sys.path.insert(0, '/stage/controller')
from scripts import run_b4b_v2 as v2
from scripts import run_b4b_task4i as task
from scripts.performance.b3_linux import environment
from scripts.performance.b4_linux import LinuxB4Backend

root = Path('/evidence')
definition = json.loads(Path('/stage/definition.json').read_text())
binaries = {'nbsr': Path('/opt/nbsr/bin/perf_rust_source'), 'server': Path('/opt/nbsr/bin/wp8_interop_server')}
rows, cells = [], []
exit_code = 0
try:
    for role, path in binaries.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == definition['binary_sha256'][path.name]
    host = environment(1)
    v2.write_json(root/'definition.json', {**definition, 'linux_environment': host})
    shutil.copytree('/opt/nbsr/provenance', root/'image-build-provenance')
    backend = LinuxB4Backend(host['selected_cpus'], host['taskset'])
    for rate in (125, 200):
        directory = root/f'rate-{rate}'
        directory.mkdir()
        records = []
        required = 3
        for repeat in range(1, 6):
            if repeat > required:
                break
            print(f'rate={rate} repeat={repeat}/{required}', flush=True)
            record = v2.run_measured_cell(512, 1, repeat, binaries, directory,
                duration=30, warmup=2, planned_clients=[512], release_rate=rate,
                source_shards=2, counter_path=directory/f'r{repeat}-host.json', backend=backend)
            record['compatibility_classification'] = 'DIAGNOSTIC_BINARY_SOURCE_MISMATCH'
            v2.write_json(directory/f'r{repeat}.json', record)
            rows.append(record)
            v2.write_json(root/'records.json', rows)
            if not record['valid'] or not record['cleanup']['all_zero']:
                raise RuntimeError('invalid partial compatibility run; no replacement')
            records.append(record)
            if repeat == 3:
                required = task.required_repeats(records)
        result = task.summarize(rate, records, cells[0] if cells else None)
        result['status_scope'] = 'existing classifier output only; binary mismatch and observer unqualified'
        cells.append(result)
        v2.write_json(root/'analysis.json', {'classification': 'DIAGNOSTIC_BINARY_SOURCE_MISMATCH',
            'cells': cells, 'live_cli_current_build_acceptance': 'NOT_RUN',
            'observer_cost': 'NOT_QUALIFIED', 'hardware_capacity': 'NOT_PROVEN'})
except BaseException as error:
    exit_code = 1
    v2.write_json(root/'failure.json', {'classification': 'INVALID_PARTIAL_DIAGNOSTIC',
        'error_type': type(error).__name__, 'error': str(error), 'retained_repeat_records': len(rows)})
finally:
    v2.write_json(root/'wrapper-result.json', {'exit_code': exit_code, 'repeat_records': len(rows),
        'controller_sha': definition['controller_sha'], 'binary_source_sha': definition['binary_source_sha']})
    task.checksums(root)
    print('READY_FOR_EVIDENCE_COPY', flush=True)
    deadline = time.monotonic() + 600
    while not Path('/tmp/evidence-copied').exists():
        if time.monotonic() >= deadline:
            raise RuntimeError('evidence transfer release bound')
        time.sleep(.2)
raise SystemExit(exit_code)
