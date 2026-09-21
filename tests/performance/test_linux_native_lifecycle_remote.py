import io
import shlex
import tarfile
import sys

import pytest

from scripts.performance.linux_native_lifecycle_remote import extract_public_archive, remote_command
from scripts.performance import linux_native_lifecycle_remote as remote


def test_ssh_uses_existing_authentication_and_quotes_each_argument():
    target = dict(transport='ssh', host='bench@server-a', checkout='/srv/repo with spaces')
    command = remote_command(target, ['python3', '-m', 'module', '--output', '/tmp/a;touch nope'])
    assert command[:8] == ['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                           '-o', 'ConnectTimeout=10']
    assert command[-2] == target['host']
    tokens = shlex.split(command[-1])
    assert tokens == ['cd', target['checkout'], '&&', 'exec', 'python3', '-m', 'module',
                      '--output', '/tmp/a;touch nope']
    assert 'StrictHostKeyChecking=no' not in command


def test_docker_exec_uses_one_existing_nonroot_container():
    command = remote_command(dict(transport='docker', host='owned-benchmark-source', checkout='/tmp/source'),
                             ['python', '-B', '-m', 'module'])
    assert command[:7] == ['docker', 'exec', '-i', '--user', '65532', 'owned-benchmark-source', 'sh']
    assert command[7] == '-c' and shlex.split(command[8])[-4:] == ['python', '-B', '-m', 'module']


@pytest.mark.parametrize('change', [dict(host='-oProxyCommand=bad'), dict(host='host;touch bad'),
    dict(host='host name'), dict(checkout='relative'), dict(checkout='/srv/../etc'),
    dict(checkout='/srv/line\nbreak'), dict(transport='local-shell')])
def test_invalid_targets_reject(change):
    with pytest.raises(ValueError):
        remote_command(dict(transport='ssh', host='server-a', checkout='/srv/repo') | change, ['true'])


def archive(tmp_path, entries):
    path = tmp_path / 'input.tar'
    with tarfile.open(path, 'w') as stream:
        for name, kind, value in entries:
            entry = tarfile.TarInfo(name)
            if kind == 'file':
                entry.size = len(value)
                stream.addfile(entry, io.BytesIO(value))
            else:
                entry.type = tarfile.SYMTYPE if kind == 'symlink' else tarfile.LNKTYPE
                entry.linkname = value
                stream.addfile(entry)
    return path


def test_plain_archive_preserves_exact_public_bytes(tmp_path):
    path = archive(tmp_path, [('./peer/rows.json', 'file', b'{"ok":true}\n'),
                              ('./checksums.sha256', 'file', b'index\n')])
    out = tmp_path / 'output'
    extract_public_archive(path, out)
    assert (out / 'peer' / 'rows.json').read_bytes() == b'{"ok":true}\n'
    assert (out / 'checksums.sha256').read_bytes() == b'index\n'


@pytest.mark.parametrize('name', ['../outside', '/absolute', 'C:/outside', 'peer\\outside', './peer/../../outside'])
def test_archive_traversal_rejects(tmp_path, name):
    path = archive(tmp_path, [(name, 'file', b'x')])
    with pytest.raises(ValueError):
        extract_public_archive(path, tmp_path / 'output')
    assert not (tmp_path / 'outside').exists()


@pytest.mark.parametrize('kind', ['symlink', 'hardlink'])
def test_archive_links_reject(tmp_path, kind):
    path = archive(tmp_path, [('peer/link', kind, '../../outside')])
    with pytest.raises(ValueError):
        extract_public_archive(path, tmp_path / 'output')


def test_archive_duplicate_names_and_size_limits_reject(tmp_path):
    path = archive(tmp_path, [('./peer/file', 'file', b'a'), ('peer/file', 'file', b'b')])
    with pytest.raises(ValueError, match='duplicate'):
        extract_public_archive(path, tmp_path / 'output')
    path = archive(tmp_path, [('peer/large', 'file', b'01234567890')])
    with pytest.raises(ValueError, match='size'):
        extract_public_archive(path, tmp_path / 'bounded', maximum_bytes=10)


@pytest.mark.parametrize('oversized', [False, True], ids=['deadline', 'size'])
def test_download_is_bounded_and_reaps_only_its_owned_relay(tmp_path, monkeypatch, oversized):
    children = []
    popen = remote.subprocess.Popen

    def launch(*args, **kwargs):
        child = popen(*args, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(remote.subprocess, 'Popen', launch)
    script = 'import sys; sys.stdout.buffer.write(b"x"*128); sys.stdout.flush()' if oversized else 'import time; time.sleep(60)'
    with pytest.raises(ValueError if oversized else TimeoutError):
        remote.download_archive([sys.executable, '-c', script], tmp_path / 'partial.tar', tmp_path / 'stderr',
                                timeout=5 if oversized else .1, maximum_bytes=64)
    assert len(children) == 1 and children[0].poll() is not None
