"""Fixed scenario execution. Every attempt has a fresh lifecycle and evidence root."""
import json
import os
import re
import sys
from pathlib import Path

from .evidence import EXPECTED_TESTS, verify, write_receipt
from .setup import environment, private_path, validate_build
from .supervision import run_owned


def execute(repo, state, run_id, scenario, cancel):
    if not re.fullmatch(r'demo-[0-9a-f]{32}', run_id):
        raise ValueError('Invalid owned run ID')
    manifest = validate_build(repo, state)
    run_dir = private_path(state / 'runs' / run_id)
    run_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    provenance = {key: manifest[key] for key in ('source_hashes', 'source_commit', 'platform', 'toolchain')}
    provenance['binary_hashes'] = {k: v['sha256'] for k, v in manifest['artifacts'].items()}
    logs = run_dir / 'process'
    env = environment()
    if scenario == 'allowed_service_a':
        request = run_dir / 'worker.json'
        request.write_text(json.dumps({'repo': str(repo), 'state': str(state), 'run_id': run_id, 'manifest': manifest}), encoding='utf-8')
        argv = [sys.executable, str(repo / 'tools/demo-lab/demo.py'), '_worker', '--request', str(request)]
        cwd = repo
        expected = []
    elif scenario in EXPECTED_TESTS:
        role = 'test-corestate' if scenario == 'expired_mapping' else ('test-resolution' if scenario == 'shared_ip_isolation' else 'test-client')
        cwd = repo / ('client/nbsr-go-client' if role != 'test-client' else 'client/nbsr-go-client/demo')
        expected = [EXPECTED_TESTS[scenario]]
        argv = [manifest['artifacts'][role]['path'], '-test.v', '-test.count=1', '-test.timeout=60s', '-test.run=^' + expected[0] + '$']
    else:
        raise ValueError('Unknown scenario')
    result = run_owned(argv, cwd, env, logs, timeout=95, cancel=cancel)
    raw = {}
    if scenario == 'allowed_service_a':
        for name in ('application.json', 'destination.json'):
            path = run_dir / ('worker-' + name)
            if path.is_file() and path.stat().st_size <= 4 * 1024**2:
                raw[name] = path.read_text(encoding='utf-8')
    else:
        path = logs / 'stdout.log'
        if path.is_file():
            raw['test-output.txt'] = path.read_text(encoding='utf-8', errors='strict')
    structured = {'exit_code': result['exit_code'], 'reason': result['reason'],
                  'cancelled': result['reason'] == 'cancelled', 'timeout': result['reason'] == 'timeout',
                  'expected_tests': expected, 'regression_kind': None if scenario == 'allowed_service_a' else 'fixture_regression'}
    # Source/binary recheck after execution prevents mixed-build receipts.
    try:
        if validate_build(repo, state) != manifest:
            raise ValueError('Build manifest changed during execution')
    except (ValueError, OSError):
        structured['exit_code'] = 1
        structured['reason'] = 'source_or_binary_changed'
    write_receipt(run_dir, scenario, provenance, structured, result['cleanup'], raw)
    return verify(run_dir)
