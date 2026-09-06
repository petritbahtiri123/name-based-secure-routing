import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import traceback

from scripts import run_b3_session_lifecycle as b3
from scripts.run_b3_v2 import spec_for, validate_linux_manifest, verify_linux_execution
from scripts.performance.b3_linux import LinuxCapture, environment
from scripts.performance.b3_linux_analysis import analyze_roots
from scripts.run_b4b_task4k import checksums

ROOT = Path('/evidence')
SOURCE = Path('/controller')
SHA = '1cca67ad092292acec85f622c7d2825c47654a67'
paths = ['scripts/run_b3_v2.py', 'scripts/run_b3_session_lifecycle.py',
         'scripts/performance/b3_linux.py', 'scripts/performance/b3_linux_analysis.py',
         'scripts/performance/linux_resources.py', 'scripts/performance/linux_loopback.py']
summary = []
try:
    linux = environment(1)
    binaries = {'rust': Path('/opt/nbsr/bin/perf_rust_source'), 'server': Path('/opt/nbsr/bin/wp8_interop_server')}
    build = validate_linux_manifest(SOURCE / 'build-manifest.json', binaries)
    retained = ROOT / 'immutable-binary-copies'
    retained.mkdir()
    for path in binaries.values():
        shutil.copy2(path, retained / path.name)
    for axis, count in [('streams', 16), ('streams', 32), ('bundles', 16), ('cycles', 3)]:
        root = ROOT / f'{axis}-{count}'
        root.mkdir()
        (root / 'binaries').mkdir()
        for path in binaries.values():
            os.link(retained / path.name, root / 'binaries' / path.name)
        for path in paths:
            dest = root / 'source' / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SOURCE / path, dest)
        b3.write_json(root / 'build-manifest.json', build)
        b3.write_json(root / 'environment.json', dict(platform='linux', source_sha=SHA,
            binary_source_sha=build['source_sha'], binary_sha256={r: hashlib.sha256(p.read_bytes()).hexdigest() for r,p in binaries.items()},
            classification='DIAGNOSTIC_BINARY_SOURCE_MISMATCH', linux_environment=linux,
            memory_scope='Linux smaps private resident/RSS/PSS/separate hugetlb, FD/thread counts; no Windows aliases',
            invocation_scope='current staged run_cell+LinuxCapture compatibility; run_b3_v2 CLI live NOT_RUN',
            execution_paths={r:str(p) for r,p in binaries.items()},
            retained_paths={r:str(root / 'binaries' / p.name) for r,p in binaries.items()},
            wrapper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))
        records = []
        outcome = dict(axis=axis, count=count, valid_repeats=0)
        try:
            for repeat in range(1, 4):
                print(f'RUN {axis}-{count} repeat={repeat}', flush=True)
                spec = spec_for(axis, count, repeat, materialized_streams=True)
                verify_linux_execution(binaries, root / 'binaries', build)
                row = b3.run_cell('rust-rust', spec, binaries, root, idle_seconds=2,
                    active_seconds=2, cooldown_seconds=2, cadence=.5,
                    capture_backend=LinuxCapture(linux['selected_cpus'], linux['taskset']))
                records.append(row)
                b3.write_json(root / 'records.json', records)
                assert row['cleanup']['all_zero']
                outcome['valid_repeats'] += 1
            checksums(root)
            shutil.copy2(root / 'checksums.sha256', root / 'analysis-input-checksums.txt')
            analysis = analyze_roots([root])
            assert analysis['classification'] == 'DIAGNOSTIC_BINARY_SOURCE_MISMATCH'
            b3.write_json(root / 'analysis.json', analysis)
            outcome['status'] = 'COMPATIBILITY_PASS'
        except Exception as error:
            outcome.update(status='FAIL', error=repr(error), traceback=traceback.format_exc())
            b3.write_json(root / 'wrapper-failure.json', outcome)
        finally:
            checksums(root)
            summary.append(outcome)
            print(json.dumps(outcome), flush=True)
except Exception as error:
    summary.append(dict(status='SETUP_FAIL', error=repr(error), traceback=traceback.format_exc()))
finally:
    b3.write_json(ROOT / 'summary.json', summary)
    checksums(ROOT)
    print('READY_FOR_EVIDENCE_COPY', flush=True)
    deadline = time.monotonic() + 180
    while not Path('/tmp/evidence-copied').exists() and time.monotonic() < deadline:
        time.sleep(.2)
raise SystemExit(0 if summary and all(r.get('status') == 'COMPATIBILITY_PASS' for r in summary) else 1)
