"""Mac-hosted Linux execution; no claim of native macOS backend execution."""
import json
import platform
import re
import shutil
import threading
from pathlib import Path

from .evidence import MAX_BYTES, verify, write_attempt, write_receipt
from .setup import command, environment, inventory, private_path


def configure(state, image_id):
    if platform.system() != 'Darwin':
        raise ValueError('Container configuration is for a Mac host')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', image_id):
        raise ValueError('Supply the exact reviewed local image ID (sha256:...)')
    state = private_path(state)
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    if (state / 'active.json').exists() or (state / 'ui.lock').exists():
        raise ValueError('Stop and reconcile the Demo Lab session before changing image')
    pending = state / 'container-image.pending.json'
    with pending.open('x', encoding='utf-8') as stream:
        json.dump({'image_id': image_id}, stream)
    pending.replace(state / 'container-image.json')
    return {'configured': image_id, 'validation': 'Identity selected only; image and native acceptance not verified'}


def validate(repo, state):
    if platform.system() != 'Darwin' or platform.machine().lower() not in ('arm64', 'x86_64'):
        raise ValueError('Native Mac Intel/Apple Silicon host required')
    from .container_runner import native_architecture
    native_architecture()
    docker = shutil.which('docker')
    if not docker:
        raise ValueError('Docker CLI missing; install Docker Desktop explicitly using official instructions')
    path = private_path(state / 'container-image.json')
    with path.open('rb') as stream:
        raw = stream.read(4097)
    if len(raw) > 4096:
        raise ValueError('Image configuration exceeds bound')
    config = json.loads(raw)
    if (set(config) != {'image_id'} or not isinstance(config['image_id'], str)
            or not re.fullmatch(r'sha256:[0-9a-f]{64}', config['image_id'])):
        raise ValueError('Invalid reviewed image configuration')
    return {**config, 'docker': str(Path(docker).resolve()), 'source_hashes': inventory(repo)}


def execute(repo, state, run_id, scenario, cancel):
    from .container_runner import run_container
    from .coordinator import SCENARIOS
    if scenario not in SCENARIOS or not re.fullmatch(r'demo-[0-9a-f]{32}', run_id):
        raise ValueError('Invalid fixed scenario/run identity')
    config = validate(repo, state)
    git = shutil.which('git')
    if not git:
        raise ValueError('Git required to identify source commit')
    commit = command(git, ['rev-parse', 'HEAD'], repo)
    run_dir = private_path(state / 'runs' / run_id)
    run_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    source, artifacts = run_dir / 'source', run_dir / 'artifacts'
    source.mkdir(mode=0o700)
    artifacts.mkdir(mode=0o700)
    (source / 'source.json').write_text(json.dumps({'source_commit': commit,
                'source_hashes': config['source_hashes']}), encoding='utf-8')
    result = run_container(config['docker'], config['image_id'], run_id,
                           {'source': source, 'artifacts': artifacts}, [scenario],
                           run_dir / 'control', cancel)
    # Never expose helper-control files to the container's writable mount.
    (run_dir / 'host-result.json').write_text(json.dumps(result), encoding='utf-8')
    inner_dir = artifacts / 'inner'
    inner = verify(inner_dir)
    receipt = inner.get('receipt')
    def incomplete(reason):
        write_attempt(run_dir, {'schema': 'nbsr-demo-attempt-v1', 'run_id': run_id,
                      'source_commit': commit, 'expected_source_hashes': config['source_hashes'],
                      'host_platform': 'Darwin-' + platform.machine().lower(),
                      'image_id': config['image_id'], 'container_id': result.get('container_id'),
                      'exit_code': result['exit_code'], 'reason': reason, 'cleanup': result['cleanup']})
        return verify(run_dir)
    if (not inner['valid'] or not receipt or receipt.get('scenario') != scenario
            or receipt['provenance']['source_hashes'] != config['source_hashes']
            or receipt['provenance']['source_commit'] != commit
            or not re.fullmatch(r'[0-9a-f]{64}', result.get('container_id') or '')):
        return incomplete('missing_or_inconsistent_inner_evidence')
    expected_platform = 'Linux-aarch64' if platform.machine().lower() == 'arm64' else 'Linux-x86_64'
    if receipt['provenance']['platform'] != expected_platform:
        return incomplete('container_architecture_mismatch')
    structured = dict(receipt['result'])
    if result['exit_code'] != 0 or result['reason'] != 'completed':
        structured.update(exit_code=result['exit_code'], reason=result['reason'],
                          cancelled=result['reason'] == 'cancelled', timeout=result['reason'] == 'timeout')
    if inventory(repo) != config['source_hashes'] or validate(repo, state)['image_id'] != config['image_id']:
        structured.update(exit_code=1, reason='source_or_image_changed')
    raw = {}
    for name in receipt['artifacts']:
        path = private_path(inner_dir / name)
        with path.open('rb') as stream:
            data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError('Container evidence exceeds bound')
        raw[name] = data.decode('utf-8')
    execution = {'mode': 'mac_host_linux_container', 'host_platform': 'Darwin-' + platform.machine().lower(),
                 'execution_platform': expected_platform, 'image_id': config['image_id'],
                 'container_id': result['container_id']}
    write_receipt(run_dir, scenario, receipt['provenance'], structured, result['cleanup'], raw, execution=execution)
    return verify(run_dir)


def container_worker(scenario):
    """Fixed image entry point; host source is compared but never executed."""
    import os
    from .coordinator import SCENARIOS
    from .runner import execute as run_inner
    from .setup import validate_build
    if platform.system() != 'Linux' or os.environ.get('NBSR_DEMO_CONTAINER') != '1':
        raise ValueError('Internal Linux-container entry point only')
    run_id = os.environ.get('NBSR_DEMO_RUN_ID', '')
    if scenario not in SCENARIOS or not re.fullmatch(r'demo-[0-9a-f]{32}', run_id):
        raise ValueError('Invalid container scenario identity')
    repo, state = Path('/src'), Path('/work')
    manifest = validate_build(repo, state)
    with Path('/source/source.json').open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('Source snapshot exceeds bound')
    snapshot = json.loads(raw)
    if snapshot != {key: manifest[key] for key in ('source_commit', 'source_hashes')}:
        raise ValueError('Reviewed host source differs from immutable image source')
    outcome = run_inner(repo, state, run_id, scenario, threading.Event())
    inner_dir = Path('/artifacts/inner')
    inner_dir.mkdir(mode=0o700)
    for name in ('receipt.json', *outcome.get('receipt', {}).get('artifacts', {})):
        shutil.copyfile(state / 'runs' / run_id / name, inner_dir / name)
    return 0 if outcome['valid'] and outcome['outcome'] == 'PASS' else 1
