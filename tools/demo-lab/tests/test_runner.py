import copy
import json
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nbsr_demo_lab import runner, worker
from nbsr_demo_lab.evidence import EXPECTED_TESTS


def test_changed_manifest_cannot_pass(tmp_path, monkeypatch):
    manifest = dict(source_commit='a' * 40, source_hashes={'main.go': 'b' * 64},
                    platform='Windows-amd64', toolchain={'go': 'go1.26.5'},
                    artifacts={'test-client': {'path': str(tmp_path / 'test.exe'), 'sha256': 'c' * 64}})
    changed = copy.deepcopy(manifest)
    changed['artifacts']['test-client']['sha256'] = 'd' * 64
    calls = iter([manifest, changed])
    monkeypatch.setattr(runner, 'validate_build', lambda *args: next(calls))
    def fake_run(argv, cwd, env, logs, **kwargs):
        logs.mkdir()
        name = EXPECTED_TESTS['unknown_service']
        (logs / 'stdout.log').write_text(f'=== RUN   {name}\n--- PASS: {name} (0.01s)\nPASS\n')
        return dict(exit_code=0, reason='completed', cleanup='CLEAN')
    monkeypatch.setattr(runner, 'run_owned', fake_run)
    result = runner.execute(tmp_path, tmp_path / 'state', 'demo-' + 'a' * 32,
                            'unknown_service', threading.Event())
    assert result['outcome'] == 'FAIL'
    assert result['receipt']['result']['reason'] == 'source_or_binary_changed'


def test_mac_live_blocked_before_files_or_processes(tmp_path, monkeypatch):
    monkeypatch.setattr(worker.platform, 'system', lambda: 'Darwin')
    with pytest.raises(ValueError, match='macOS live'):
        worker.run(tmp_path / 'nonexistent.json')
    assert list(tmp_path.iterdir()) == []


def test_worker_rejects_changed_manifest_before_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(worker.platform, 'system', lambda: 'Windows')
    state = tmp_path / 'state'
    run_id = 'demo-' + 'b' * 32
    run_dir = state / 'runs' / run_id
    run_dir.mkdir(parents=True)
    request = run_dir / 'worker.json'
    request.write_text(json.dumps(dict(repo=str(tmp_path), state=str(state), run_id=run_id, manifest={'pin': 'a'})))
    monkeypatch.setattr(worker, 'validate_build', lambda *args: {'pin': 'b'})
    with pytest.raises(ValueError, match='manifest changed'):
        worker.run(request)
    assert not (tmp_path / 'client').exists()
