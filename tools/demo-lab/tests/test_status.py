import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nbsr_demo_lab.status import inspect


def test_absent_state_is_not_created_or_ready(tmp_path):
    result = inspect(tmp_path)
    assert set(result['markers'].values()) == {'ABSENT'}
    assert not result['reconciliation_required']
    assert result['readiness'] == 'NOT_ESTABLISHED'
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('relative', [
    'tools/demo-lab/.state/ui.lock',
    'tools/demo-lab/.state/active.json',
    'client/nbsr-go-client/demo/test-results/nbsr-demo/runtime/active.lock',
])
def test_marker_contents_never_read_or_changed(tmp_path, monkeypatch, relative):
    marker = tmp_path / relative
    marker.parent.mkdir(parents=True)
    marker.write_text('malformed secret fixture', encoding='utf-8')
    before = marker.stat()
    def forbidden(*args, **kwargs):
        raise AssertionError('status must not read marker contents')
    monkeypatch.setattr(Path, 'open', forbidden)
    result = inspect(tmp_path)
    assert result['reconciliation_required']
    assert 'PRESENT' in result['markers'].values()
    assert 'secret' not in json.dumps(result)
    assert marker.stat() == before


def test_permission_failure_is_unknown_not_absent(tmp_path, monkeypatch):
    original = Path.lstat
    def denied(path, *args, **kwargs):
        if path.name == 'ui.lock':
            raise PermissionError('fixture denial')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'lstat', denied)
    result = inspect(tmp_path)
    assert result['markers']['dashboard'] == 'UNKNOWN'
    assert result['reconciliation_required']


def test_unsafe_path_is_unknown(tmp_path, monkeypatch):
    from nbsr_demo_lab import status
    monkeypatch.setattr(status, 'private_path', lambda path: (_ for _ in ()).throw(ValueError('unsafe')))
    result = inspect(tmp_path)
    assert set(result['markers'].values()) == {'UNKNOWN'}
    assert result['reconciliation_required']


@pytest.mark.parametrize('required,expected', [(False, 0), (True, 2)])
def test_cli_exit_status_without_starting_services(monkeypatch, capsys, required, expected):
    import demo
    from nbsr_demo_lab import status
    monkeypatch.setattr(status, 'inspect', lambda repo: {'reconciliation_required': required})
    monkeypatch.setattr(sys, 'argv', ['demo.py', 'status'])
    assert demo.main() == expected
    assert json.loads(capsys.readouterr().out)['reconciliation_required'] == required
