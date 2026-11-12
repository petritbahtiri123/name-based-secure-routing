import json
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nbsr_demo_lab import mac, container_runner
from nbsr_demo_lab.evidence import BODY, write_receipt


def test_configure_never_claims_verification(tmp_path, monkeypatch):
    monkeypatch.setattr(mac.platform, 'system', lambda: 'Darwin')
    result = mac.configure(tmp_path, 'sha256:' + 'b' * 64)
    assert 'not verified' in result['validation']
    (tmp_path / 'active.json').write_text('{}')
    with pytest.raises(ValueError, match='reconcile'):
        mac.configure(tmp_path, 'sha256:' + 'c' * 64)


@pytest.mark.parametrize('cleanup,changed,expected', [('CLEAN', False, 'PASS'), ('UNCONFIRMED', False, 'INCOMPLETE'), ('CLEAN', True, 'FAIL')])
def test_outer_container_receipt_requires_host_cleanup_and_source(tmp_path, monkeypatch, cleanup, changed, expected):
    monkeypatch.setattr(mac.platform, 'system', lambda: 'Darwin')
    monkeypatch.setattr(mac.platform, 'machine', lambda: 'arm64')
    hashes = {'main.go': 'a' * 64}
    config = {'docker': '/bin/docker', 'image_id': 'sha256:' + 'b' * 64, 'source_hashes': hashes}
    monkeypatch.setattr(mac, 'validate', lambda *args: config)
    monkeypatch.setattr(mac.shutil, 'which', lambda _: '/bin/git')
    monkeypatch.setattr(mac, 'command', lambda *args: 'c' * 40)
    monkeypatch.setattr(mac, 'inventory', lambda _: {'main.go': 'd' * 64} if changed else hashes)
    def fake_container(docker, image, run_id, mounts, argv, logdir, cancel):
        assert logdir.parent == mounts['artifacts'].parent
        assert not logdir.is_relative_to(mounts['artifacts'])
        inner = mounts['artifacts'] / 'inner'
        provenance = dict(source_commit='c' * 40, source_hashes=hashes, binary_hashes={'worker': 'e' * 64},
                          platform='Linux-aarch64', toolchain={'go': 'go1.26.5'})
        result = dict(exit_code=0, reason='completed', cancelled=False, timeout=False,
                      expected_tests=[], regression_kind=None)
        write_receipt(inner, 'allowed_service_a', provenance, result, 'CLEAN',
                      {'application.json': json.dumps({'body': BODY}),
                       'destination.json': json.dumps({'status': 'PASS', 'backend_requests': 1})})
        return dict(exit_code=0, reason='completed', cleanup=cleanup, container_id='f' * 64)
    monkeypatch.setattr(container_runner, 'run_container', fake_container)
    result = mac.execute(tmp_path, tmp_path / 'state', 'demo-' + 'a' * 32,
                         'allowed_service_a', threading.Event())
    assert result['outcome'] == expected
    assert result['receipt']['schema_version'] == 2
    assert result['receipt']['execution']['mode'] == 'mac_host_linux_container'


def test_internal_container_entry_rejects_host(monkeypatch):
    monkeypatch.setattr(mac.platform, 'system', lambda: 'Windows')
    with pytest.raises(ValueError, match='Internal Linux'):
        mac.container_worker('allowed_service_a')


def test_missing_inner_timeout_retains_verifiable_attempt(tmp_path, monkeypatch):
    monkeypatch.setattr(mac.platform, 'system', lambda: 'Darwin')
    monkeypatch.setattr(mac.platform, 'machine', lambda: 'arm64')
    config = {'docker': '/bin/docker', 'image_id': 'sha256:' + 'b' * 64, 'source_hashes': {'main.go': 'a' * 64}}
    monkeypatch.setattr(mac, 'validate', lambda *args: config)
    monkeypatch.setattr(mac.shutil, 'which', lambda _: '/bin/git')
    monkeypatch.setattr(mac, 'command', lambda *args: 'c' * 40)
    monkeypatch.setattr(container_runner, 'run_container', lambda *args: dict(exit_code=None, reason='timeout', cleanup='CLEAN', container_id='d' * 64))
    run_id = 'demo-' + 'a' * 32
    outcome = mac.execute(tmp_path, tmp_path / 'state', run_id, 'allowed_service_a', threading.Event())
    assert outcome['outcome'] == 'INCOMPLETE'
    assert outcome['cleanup'] == 'CLEAN'
    assert outcome['receipt']['container_id'] == 'd' * 64
    assert mac.verify(tmp_path / 'state/runs' / run_id) == outcome
