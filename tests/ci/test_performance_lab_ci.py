"""Performance Lab CI selection/security; no live lab or package installation."""
import json
from pathlib import Path

from scripts.ci.check import validate_workflow

ROOT = Path(__file__).resolve().parents[2]


def workflow():
    return json.loads((ROOT / '.github/workflows/performance-lab.yml').read_text(encoding='utf-8'))


def test_performance_lab_workflow_preserves_security_and_automatic_triggers():
    doc = workflow()
    validate_workflow(doc)
    assert doc['on'] == {'push': {'branches': ['codex/nbsr-v3-wp0-wp1']}, 'pull_request': {}, 'workflow_dispatch': {}}
    assert set(doc['jobs']) == {'performance-lab'}
    job = doc['jobs']['performance-lab']
    assert job['runs-on'] == 'ubuntu-24.04'
    assert job['timeout-minutes'] == 15
    assert job['defaults']['run'] == {'shell': 'pwsh', 'working-directory': 'tools/performance-lab'}
    existing = json.loads((ROOT / '.github/workflows/ci.yml').read_text(encoding='utf-8'))
    allowed_actions = {step['uses'] for entry in existing['jobs'].values() for step in entry['steps'] if 'uses' in step}
    for step in job['steps']:
        if 'uses' in step:
            assert step['uses'] in allowed_actions
        if 'run' in step:
            assert 1 <= step['timeout-minutes'] <= 5
    text = json.dumps(doc)
    assert 'secrets.' not in text
    assert 'upload-artifact' not in text
    assert 'cache/save' not in text


def test_performance_lab_runs_all_scoped_gates_with_own_pins():
    steps = workflow()['jobs']['performance-lab']['steps']
    commands = [step['run'] for step in steps if 'run' in step]
    assert commands == [
        'python -m pip install -r requirements-dev.txt',
        'npm ci --ignore-scripts --no-audit --no-fund',
        'python -B -m pytest -q -p no:cacheprovider tests',
        'node --experimental-strip-types --test tests/frontend.test.mjs',
        'npm run typecheck',
        'npm run build',
        'git diff --exit-code -- package.json package-lock.json requirements.txt requirements-dev.txt',
    ]
    package = json.loads((ROOT / 'tools/performance-lab/package.json').read_text())
    assert package['scripts']['typecheck'] == 'tsc --noEmit'
    assert package['scripts']['build'].startswith('tsc --noEmit && esbuild ')
    setup = {step['uses'].split('@')[0]: step.get('with', {}) for step in steps if 'uses' in step}
    assert setup['actions/checkout'] == {'persist-credentials': False, 'fetch-depth': 1,
                                         'sparse-checkout': 'tools/performance-lab'}
    assert setup['actions/setup-python']['python-version'] == '3.13.14'
    assert setup['actions/setup-node'] == {'node-version': '24.19.0', 'package-manager-cache': False}
