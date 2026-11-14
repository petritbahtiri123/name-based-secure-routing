"""Local temporary persistence tests; no production feed or network."""
import importlib
import json
import pytest
from tests.test_extractor import line
from tests.test_grouped import progress, final


def session(path):
    try:
        module = importlib.import_module('lab.capture')
    except ModuleNotFoundError:
        pytest.fail('Local capture persistence is not implemented')
    return module.CaptureSession(path, 'synthetic-source')


def test_snapshot_retains_raw_and_publishes_only_grouped(tmp_path):
    s = session(tmp_path / 'capture')
    diagnostic = line(dict(schema='nbsr-rust-ownership-v1', event='diagnostic', detail='private'))
    grouped = line(progress())
    result = s.append(diagnostic + grouped, offset=0, source_identity='synthetic-source')
    assert (result / 'raw.bin').read_bytes() == diagnostic + grouped
    assert (result / 'grouped.ndjson').read_bytes() == grouped
    manifest = json.loads((result / 'manifest.json').read_text())
    assert manifest['ledger']['source_bytes'] == len(diagnostic + grouped)
    assert manifest['source_identity_verified'] is False
    assert manifest['owner_closed'] is False
    assert s.snapshot_path() == result / 'grouped.ndjson'


def test_diagnostics_and_partial_tail_do_not_republish_same_grouped(tmp_path):
    s = session(tmp_path / 'capture')
    first = line(progress())
    original = s.append(first, offset=0, source_identity='synthetic-source')
    s.append(b'{', offset=len(first), source_identity='synthetic-source')
    assert s.snapshot_path() == original / 'grouped.ndjson'


def test_failure_latches_and_preserves_bytes_without_publish(tmp_path):
    s = session(tmp_path / 'capture')
    first = line(progress())
    s.append(first, offset=0, source_identity='synthetic-source')
    with pytest.raises(ValueError):
        s.append(b'bad\n', offset=len(first), source_identity='synthetic-source')
    with pytest.raises(ValueError):
        s.snapshot_path()
    assert (tmp_path / 'capture' / 'failure-raw.bin').read_bytes() == first + b'bad\n'
    with pytest.raises(ValueError):
        s.append(b'', offset=len(first)+4, source_identity='synthetic-source')


def test_owner_closure_and_existing_session_rejection(tmp_path):
    path = tmp_path / 'capture'
    s = session(path)
    raw = line(progress()) + line(final())
    s.append(raw, offset=0, source_identity='synthetic-source')
    result = s.finish()
    assert json.loads((result / 'manifest.json').read_text())['owner_closed'] is True
    with pytest.raises(FileExistsError):
        session(path)


def test_write_failure_latches_even_with_old_snapshot(tmp_path, monkeypatch):
    s = session(tmp_path / 'capture')
    raw = line(progress())
    s.append(raw, offset=0, source_identity='synthetic-source')
    def fail(*args, **kwargs):
        raise OSError('simulated full disk')
    monkeypatch.setattr(s, '_persist', fail)
    with pytest.raises(OSError):
        s.append(line(progress(2)), offset=len(raw), source_identity='synthetic-source')
    with pytest.raises(ValueError):
        s.snapshot_path()


def test_partial_only_has_no_exportable_path(tmp_path):
    s = session(tmp_path / 'capture')
    result = s.append(b'{', offset=0, source_identity='synthetic-source')
    assert not (result / 'grouped.ndjson').exists()
    assert s.snapshot_path() is None
    with pytest.raises(ValueError):
        s.finish()


def test_capture_budget_fail_closed(tmp_path, monkeypatch):
    s = session(tmp_path / 'capture')
    module = importlib.import_module('lab.capture')
    monkeypatch.setattr(module, 'MAX_SESSION_BYTES', 1)
    with pytest.raises(ValueError, match='budget'):
        s.append(line(progress()), offset=0, source_identity='synthetic-source')
    with pytest.raises(ValueError):
        s.snapshot_path()
    assert not list((tmp_path / 'capture').glob('snapshot-*'))


def test_metadata_failure_no_visible_partial_bundle(tmp_path, monkeypatch):
    s = session(tmp_path / 'capture')
    write = s._write
    def fail_manifest(path, raw):
        if path.name == 'manifest.json':
            raise OSError('simulated interruption')
        write(path, raw)
    monkeypatch.setattr(s, '_write', fail_manifest)
    with pytest.raises(OSError):
        s.append(line(progress()), offset=0, source_identity='synthetic-source')
    assert not list((tmp_path / 'capture').glob('snapshot-*'))
    assert list((tmp_path / 'capture').glob('.pending-*'))
    with pytest.raises(ValueError):
        s.snapshot_path()


@pytest.mark.parametrize('operation', ['rename', 'fsync'])
def test_commit_fault_latches_and_retains_primary_error(tmp_path, monkeypatch, operation):
    s = session(tmp_path / 'capture')
    module = importlib.import_module('lab.capture')
    def fail(*args, **kwargs):
        raise OSError('primary persistence fault')
    if operation == 'rename':
        monkeypatch.setattr(module.Path, 'rename', fail)
    else:
        monkeypatch.setattr(module.os, 'fsync', fail)
    with pytest.raises(OSError, match='primary persistence fault'):
        s.append(line(progress()), offset=0, source_identity='synthetic-source')
    with pytest.raises(ValueError):
        s.snapshot_path()
    assert not list((tmp_path / 'capture').glob('snapshot-*'))


def test_failure_retention_fault_does_not_replace_extraction_error(tmp_path, monkeypatch):
    s = session(tmp_path / 'capture')
    def fail(*args, **kwargs):
        raise OSError('secondary full disk')
    monkeypatch.setattr(s, '_write', fail)
    with pytest.raises(ValueError):
        s.append(b'bad\n', offset=0, source_identity='synthetic-source')
    with pytest.raises(ValueError):
        s.snapshot_path()


def test_snapshot_count_budget(tmp_path, monkeypatch):
    s = session(tmp_path / 'capture')
    module = importlib.import_module('lab.capture')
    monkeypatch.setattr(module, 'MAX_SNAPSHOTS', 0)
    with pytest.raises(ValueError, match='budget'):
        s.append(line(progress()), offset=0, source_identity='synthetic-source')
    assert not list((tmp_path / 'capture').glob('snapshot-*'))


@pytest.mark.parametrize('offset,identity', [(1, 'synthetic-source'), (0, 'other')])
def test_source_contract_failure_cannot_publish(tmp_path, offset, identity):
    s = session(tmp_path / 'capture')
    with pytest.raises(ValueError):
        s.append(line(progress()), offset=offset, source_identity=identity)
    with pytest.raises(ValueError):
        s.snapshot_path()
    assert (tmp_path / 'capture' / 'failure-raw.bin').read_bytes() == b''
    assert not list((tmp_path / 'capture').glob('snapshot-*'))
