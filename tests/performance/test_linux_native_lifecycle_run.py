from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.performance import linux_native_lifecycle_run as run
from scripts.performance.linux_b5_placement import seal_output
from tests.performance.test_linux_native_lifecycle_coordinator import config


def test_collection_keeps_archive_when_integrity_fails(tmp_path, monkeypatch):
    def download(command, archive, stderr, **kwargs):
        archive.write_bytes(b'archive')
        return dict(archive_sha256='fake')
    def extract(archive, destination):
        destination.mkdir()
        (destination / 'checksums.sha256').write_text('invalid')
    monkeypatch.setattr(run, 'download_archive', download)
    monkeypatch.setattr(run, 'extract_public_archive', extract)
    with pytest.raises(ValueError):
        run.collect(config()['source'], 'source', tmp_path)
    assert (tmp_path / 'source.tar').read_bytes() == b'archive'


def test_collection_removes_only_verified_duplicate_archive(tmp_path, monkeypatch):
    def download(command, archive, stderr, **kwargs):
        archive.write_bytes(b'archive')
        return dict(archive_sha256='fake')
    def extract(archive, destination):
        destination.mkdir()
        (destination / 'result.json').write_text('{}')
        seal_output(destination)
    monkeypatch.setattr(run, 'download_archive', download)
    monkeypatch.setattr(run, 'extract_public_archive', extract)
    run.collect(config()['source'], 'source', tmp_path)
    assert not (tmp_path / 'source.tar').exists()
    assert (tmp_path / 'source' / 'result.json').read_text() == '{}'
    assert (tmp_path / 'source-transfer.json').exists()


def test_failure_still_closes_manager_collects_started_role_and_seals(tmp_path, monkeypatch):
    actions = []
    class Manager:
        def __init__(self, *args, **kwargs):
            self.children = dict(source=object())
            self.ledger = SimpleNamespace(positions=dict(source=1, destination=0))
        def start_command(self, *args):
            raise InterruptedError('simulated management failure')
        wait = send = finish = sleep = lambda *args: None
        def close(self):
            actions.append('close')
            return dict(source=dict(remote_cleanup='UNCONFIRMED'))
    monkeypatch.setattr(run, 'Manager', Manager)
    monkeypatch.setattr(run, 'collect', lambda target, role, output, **kwargs: actions.append(role))
    output = tmp_path / 'evidence'
    with pytest.raises(InterruptedError):
        run.execute(config(), output)
    assert actions == ['close', 'source']
    assert (output / 'failure.json').exists() and (output / 'checksums.sha256').exists()
    assert not (output / 'result.json').exists()


def test_run_rejects_checkout_output_before_creation(monkeypatch, tmp_path):
    monkeypatch.setattr(run, 'ROOT', Path(tmp_path))
    with pytest.raises(ValueError, match='external'):
        run.execute(config(), tmp_path / 'inside')
    assert not (tmp_path / 'inside').exists()


def test_startup_failure_without_live_event_never_collects_preexisting_private_output(tmp_path, monkeypatch):
    private = tmp_path / 'preexisting'
    private.mkdir()
    secret = private / 'private-sentinel'
    secret.write_text('must remain private')
    class Manager:
        def __init__(self, *args, **kwargs):
            self.children = dict(source=object())
            self.ledger = SimpleNamespace(positions=dict(source=0, destination=0))
        def start_command(self, *args):
            raise FileExistsError('preexisting remote output')
        wait = send = finish = sleep = lambda *args: None
        def close(self):
            return {}
    monkeypatch.setattr(run, 'Manager', Manager)
    monkeypatch.setattr(run, 'collect', lambda *args, **kwargs: pytest.fail('unowned output must not be transferred'))
    output = tmp_path / 'evidence'
    with pytest.raises(FileExistsError):
        run.execute(config(), output)
    assert secret.read_text() == 'must remain private'
    assert (output / 'source-collection-skipped.json').exists()
    assert not (output / 'source.tar').exists()
