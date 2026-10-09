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
    monkeypatch.setattr(run, 'collect_reports', lambda target, role, output, **kwargs: actions.append('reports-' + role))
    monkeypatch.setattr(run, 'collect', lambda target, role, output, **kwargs: actions.append(role))
    output = tmp_path / 'evidence'
    with pytest.raises(InterruptedError):
        run.execute(config(), output)
    assert actions == ['close', 'reports-source', 'source']
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
    monkeypatch.setattr(run, 'collect_reports', lambda *args, **kwargs: pytest.fail('unowned reports must not be transferred'))
    monkeypatch.setattr(run, 'collect', lambda *args, **kwargs: pytest.fail('unowned output must not be transferred'))
    output = tmp_path / 'evidence'
    with pytest.raises(FileExistsError):
        run.execute(config(), output)
    assert secret.read_text() == 'must remain private'
    assert (output / 'source-collection-skipped.json').exists()
    assert not (output / 'source.tar').exists()


@pytest.mark.parametrize('source_report_fails', [False, True])
def test_reports_from_both_owned_peers_survive_interrupted_first_bulk_transfer(tmp_path, monkeypatch, source_report_fails):
    import json
    actions = []
    class OuterDeadline(BaseException):
        pass
    class Manager:
        def __init__(self, *args, **kwargs):
            self.children = dict(source=object(), destination=object())
            self.ledger = SimpleNamespace(positions=dict(source=3, destination=2))
        def start_command(self, *args):
            raise InterruptedError('destination control EOF')
        wait = send = finish = sleep = lambda *args: None
        def close(self):
            return {}
    report = {'status': 'PASS', 'connections': 16, 'samples': [{}] * 15}
    def reports(target, role, output, **kwargs):
        actions.append('reports-' + role)
        if role == 'source' and source_report_fails:
            raise TimeoutError('source report transfer deadline')
        saved = output / (role + '-reports')
        saved.mkdir()
        (saved / 'server-result.json').write_text(json.dumps(report))
    def bulk(target, role, output, **kwargs):
        actions.append('bulk-' + role)
        raise OuterDeadline()
    monkeypatch.setattr(run, 'Manager', Manager)
    monkeypatch.setattr(run, 'collect_reports', reports, raising=False)
    monkeypatch.setattr(run, 'collect', bulk)
    output = tmp_path / 'evidence'
    with pytest.raises(OuterDeadline):
        run.execute(config(), output)
    assert actions == ['reports-destination', 'reports-source', 'bulk-source']
    assert json.loads((output / 'destination-reports/server-result.json').read_text()) == report
    assert not (output / 'result.json').exists()


def test_report_collection_preserves_exact_bytes_with_small_explicit_limits(tmp_path, monkeypatch):
    import io
    import tarfile
    wire = b'{"status":"PASS","connections":16,"samples":[]}\n'
    observed = {}
    def download(command, archive, stderr, **kwargs):
        observed.update(command=command, **kwargs)
        with tarfile.open(archive, 'w') as stream:
            member = tarfile.TarInfo('peer/server-result.json')
            member.size = len(wire)
            stream.addfile(member, io.BytesIO(wire))
        return dict(archive_sha256='test-transfer-hash')
    monkeypatch.setattr(run, 'download_archive', download)
    run.collect_reports(config()['destination'], 'destination', tmp_path)
    assert (tmp_path / 'destination-reports/peer/server-result.json').read_bytes() == wire
    assert observed['timeout'] == 3
    assert observed['maximum_bytes'] == 4 * 1024 * 1024
    assert 'peer/server-result.json' in observed['command'][-1]
    assert 'executed-binary' not in observed['command'][-1]
    assert 'authority' not in observed['command'][-1]
    assert (tmp_path / 'destination-reports.tar').exists()
    assert not (tmp_path / 'destination').exists()
