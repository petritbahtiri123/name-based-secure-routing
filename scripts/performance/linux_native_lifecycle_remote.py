"""Bounded private management transport; no credential or host-key changes."""

from pathlib import PurePosixPath
import re
import shlex
import subprocess
import tarfile
import time

from scripts.performance.linux_b5_ceiling import require
from scripts.performance.linux_loopback import digest
from scripts.performance.process_cancellation import not_cancelled


def remote_path(value):
    require(isinstance(value, str) and value and not any(c in value for c in '\0\r\n\\'), 'invalid remote path')
    path = PurePosixPath(value)
    require(path.is_absolute() and '..' not in path.parts and path.as_posix() == value, 'absolute canonical remote path required')
    return value


def remote_command(target, argv):
    require(isinstance(argv, list) and argv and all(isinstance(a, str) and not any(c in a for c in '\0\r\n') for a in argv),
            'invalid remote arguments')
    checkout = remote_path(target['checkout'])
    transport, host = target['transport'], target['host']
    require(isinstance(host, str), 'invalid management host')
    command = 'cd ' + shlex.quote(checkout) + ' && exec ' + shlex.join(argv)
    if transport == 'ssh':
        require(re.fullmatch(r'(?:[A-Za-z0-9_][A-Za-z0-9_.-]*@)?[A-Za-z0-9][A-Za-z0-9_.-]*', host),
                'invalid SSH host; use a configured alias for IPv6/ports')
        return ['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                '-o', 'ConnectTimeout=10', '--', host, command]
    require(transport == 'docker' and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', host),
            'invalid Docker fixture target')
    return ['docker', 'exec', '-i', '--user', '65532', host, 'sh', '-c', command]


def extract_public_archive(archive, output, *, maximum_bytes=536870912, maximum_entries=10000):
    require(type(maximum_entries) is int and 0 < maximum_entries <= 40000, "invalid archive entry bound")
    require(not output.exists() and not output.is_symlink(), 'fresh collection directory required')
    require(type(maximum_bytes) is int and 0 < maximum_bytes <= 536870912, 'invalid archive bound')
    seen, members, total = set(), [], 0
    with tarfile.open(archive, 'r:') as stream:
        for index, member in enumerate(stream):
            require(index < maximum_entries, 'archive entry count exceeded')
            require((member.isfile() or member.isdir()) and member.sparse is None, 'archive links/special entries rejected')
            name = member.name
            while name.startswith('./'):
                name = name[2:]
            if name in ('', '.') and member.isdir():
                continue
            path = PurePosixPath(name)
            require(name and not path.is_absolute() and '..' not in path.parts and path.as_posix() == name
                    and not any(c in name for c in '\\:\0\r\n'), 'unsafe archive path')
            require(name not in seen, 'duplicate archive path')
            seen.add(name)
            require(member.size >= 0 and (not member.isdir() or member.size == 0), 'invalid archive size')
            total += member.size
            require(total <= maximum_bytes, 'archive size bound exceeded')
            members.append((member, path))
        output.mkdir()
        root = output.resolve()
        for member, relative in members:
            destination = root.joinpath(*relative.parts)
            require(destination.resolve().is_relative_to(root), 'archive escaped collection root')
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            source = stream.extractfile(member)
            require(source is not None, 'missing archive content')
            with source, destination.open('xb') as target:
                remaining = member.size
                while remaining:
                    chunk = source.read(min(65536, remaining))
                    require(chunk, 'truncated archive content')
                    target.write(chunk)
                    remaining -= len(chunk)


def download_archive(command, archive, stderr, *, timeout=60, maximum_bytes=536870912, check_cancelled=not_cancelled):
    """Bound a transfer after measurement, including an uncooperative local relay."""
    require(0 < timeout <= 60 and type(maximum_bytes) is int and 0 < maximum_bytes <= 536870912,
            'invalid transfer limits')
    child = None
    try:
        with archive.open('xb') as wire, stderr.open('xb') as errors:
            check_cancelled()
            child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=wire, stderr=errors)
            deadline = time.monotonic() + timeout
            while True:
                check_cancelled()
                require(archive.stat().st_size <= maximum_bytes, 'archive transfer size exceeded')
                code = child.poll()
                if code is not None:
                    require(code == 0, 'archive relay failed')
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError('archive transfer deadline')
                time.sleep(.02)
        return dict(archive_sha256=digest(archive), archive_bytes=archive.stat().st_size, command=command)
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
