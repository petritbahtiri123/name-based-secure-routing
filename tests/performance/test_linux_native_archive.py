import hashlib
import io
import tarfile

import pytest

from scripts.performance import linux_native_lifecycle_run as run
from scripts.performance.linux_native_pair import verify_index
from tests.performance.test_linux_native_lifecycle_coordinator import config


def archive_bytes(entries):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w') as archive:
        for name, data, kind in entries:
            member = tarfile.TarInfo(name)
            member.type, member.size = kind, len(data)
            archive.addfile(member, io.BytesIO(data))
    return buffer.getvalue()


def test_archive_collection_keeps_complete_evidence_without_extracting(tmp_path, monkeypatch):
    data = b'full evidence'
    index = (hashlib.sha256(data).hexdigest() + '  nested/payload\n').encode()
    wire = archive_bytes([('nested/payload', data, tarfile.REGTYPE), ('checksums.sha256', index, tarfile.REGTYPE)])
    def download(command, archive, stderr, **kwargs):
        archive.write_bytes(wire)
        return dict(archive_sha256=hashlib.sha256(wire).hexdigest())
    monkeypatch.setattr(run, 'download_archive', download)
    root = run.collect(config()['source'], 'source', tmp_path, archive_collection=True)
    assert verify_index(root) == hashlib.sha256(index).hexdigest()
    assert (root / 'nested/payload').read_bytes() == data
    assert not (tmp_path / 'source').exists()
    assert (tmp_path / 'source.tar').read_bytes() == wire


@pytest.mark.parametrize('fault', ['tamper', 'missing', 'extra', 'duplicate', 'traversal', 'symlink', 'hardlink', 'collision', 'bound'])
def test_archive_rejects_invalid_evidence(tmp_path, fault):
    from scripts.performance.linux_native_archive import archive_root
    index = (hashlib.sha256(b'valid').hexdigest() + '  payload\n').encode()
    entries = [('payload', b'valid', tarfile.REGTYPE), ('checksums.sha256', index, tarfile.REGTYPE)]
    options = {}
    if fault == 'tamper':
        entries[0] = ('payload', b'wrong', tarfile.REGTYPE)
    elif fault == 'missing':
        entries.pop(0)
    elif fault == 'extra':
        entries.append(('extra', b'', tarfile.REGTYPE))
    elif fault == 'duplicate':
        entries.append(entries[0])
    elif fault == 'traversal':
        entries.append(('../escape', b'', tarfile.REGTYPE))
    elif fault in ('symlink', 'hardlink'):
        entries.append(('link', b'', tarfile.SYMTYPE if fault == 'symlink' else tarfile.LNKTYPE))
    elif fault == 'collision':
        entries.append(('payload/child', b'', tarfile.REGTYPE))
    else:
        options['maximum_bytes'] = 1
    path = tmp_path / 'evidence.tar'
    path.write_bytes(archive_bytes(entries))
    with pytest.raises(ValueError):
        verify_index(archive_root(path, **options))
    assert path.is_file()
