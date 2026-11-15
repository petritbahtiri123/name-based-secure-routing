"""Keep component-only Demo Lab coverage automatic on both supported CI hosts."""
import json
from pathlib import Path

from scripts.ci.check import validate_workflow

ROOT = Path(__file__).resolve().parents[2]


def test_demo_lab_workflow_covers_components_and_ui_without_live_setup():
    path = ROOT / '.github/workflows/demo-lab.yml'
    assert path.exists(), 'Demo Lab currently has no automatic CI workflow'
    workflow = json.loads(path.read_text(encoding='utf-8'))
    validate_workflow(workflow)
    assert workflow['on'] == {
        'push': {'branches': ['codex/nbsr-v3-wp0-wp1']},
        'pull_request': {}, 'workflow_dispatch': {},
    }
    job = workflow['jobs']['demo-lab']
    assert set(job['strategy']['matrix']['os']) == {'ubuntu-24.04', 'windows-2025'}
    assert job['strategy']['fail-fast'] is False
    assert job['runs-on'] == '${{ matrix.os }}'
    assert job['timeout-minutes'] == 10
    steps = job['steps']
    assert not any(s.get('continue-on-error') for s in steps)
    runs = [s for s in steps if 'run' in s]
    assert [s['run'] for s in runs] == [
        'python -m pip install --constraint constraints/dev.txt pytest',
        'python scripts/ci/check.py validate',
        'python -m pytest -q -p no:cacheprovider tools/demo-lab/tests tests/ci/test_demo_lab_workflow.py',
        'node tools/demo-lab/tests/test_ui.cjs tools/demo-lab/static/app.js',
    ]
    assert all(1 <= s['timeout-minutes'] <= 5 for s in runs)
    assert all('if' not in s for s in runs)
    python = next(s for s in steps if s.get('uses', '').startswith('actions/setup-python@'))
    node = next(s for s in steps if s.get('uses', '').startswith('actions/setup-node@'))
    assert python['with']['python-version'] == '3.13.14'
    assert node['with']['node-version'] == '24.19.0'
    assert node['with']['package-manager-cache'] is False
