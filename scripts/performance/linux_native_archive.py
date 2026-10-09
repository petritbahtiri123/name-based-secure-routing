"""Bounded read-only TAR paths for existing native evidence validators."""

import io
from pathlib import PurePosixPath
import tarfile

from scripts.performance.linux_b5_ceiling import require


def archive_root(archive, *, maximum_bytes=536870912, maximum_entries=10000):
    require(type(maximum_entries) is int and 0 < maximum_entries <= 40000, 'invalid archive entry bound')
    require(type(maximum_bytes) is int and 0 < maximum_bytes <= 536870912, 'invalid archive bound')
    files, directories, seen, total = {}, {PurePosixPath('.')}, set(), 0
    with tarfile.open(archive, 'r:') as stream:
        for index, member in enumerate(stream):
            require(index < maximum_entries, 'archive entry count exceeded')
            require((member.isfile() or member.isdir()) and member.sparse is None,
                    'archive links/special entries rejected')
            name = member.name
            while name.startswith('./'):
                name = name[2:]
            if name in ('', '.') and member.isdir():
                require(member.size == 0, 'invalid archive size')
                continue
            path = PurePosixPath(name)
            require(name and not path.is_absolute() and '..' not in path.parts and path.as_posix() == name
                    and not any(c in name for c in '\\:\0\r\n'), 'unsafe archive path')
            require(path not in seen, 'duplicate archive path')
            seen.add(path)
            require(member.size >= 0 and (not member.isdir() or member.size == 0), 'invalid archive size')
            total += member.size
            require(total <= maximum_bytes, 'archive size bound exceeded')
            directories.update(path.parents)
            if member.isdir():
                directories.add(path)
            else:
                source = stream.extractfile(member)
                require(source is not None, 'missing archive content')
                with source:
                    data = source.read(member.size)
                require(len(data) == member.size, 'truncated archive content')
                files[path] = data
    require(not (files.keys() & directories), 'archive file/directory collision')
    return ArchivePath(files, directories, PurePosixPath('.'))


class ArchivePath:
    """Minimal path interface; all bytes are a bounded immutable snapshot.

    No filesystem fallback, writes, symlinks or special entries are supported.
    Identity is tied to the archive inventory, not its member path alone.
    """

    def __init__(self, files, directories, path):
        self._files, self._directories, self._path = files, directories, path

    def _at(self, path):
        return ArchivePath(self._files, self._directories, path)

    def __truediv__(self, name):
        return self._at(self._path / name)

    def __eq__(self, other):
        return isinstance(other, ArchivePath) and self._files is other._files and self._path == other._path

    @property
    def name(self):
        return self._path.name

    @property
    def parent(self):
        return self._at(self._path.parent)

    def resolve(self):
        require(not self._path.is_absolute() and '..' not in self._path.parts, 'unsafe archive path')
        return self

    def relative_to(self, other):
        require(self._files is other._files, 'distinct archives')
        return self._path.relative_to(other._path)

    def is_relative_to(self, other):
        return self._files is other._files and self._path.is_relative_to(other._path)

    def is_symlink(self):
        return False  # Loader rejects every link and special entry.

    def is_file(self):
        return self._path in self._files

    def exists(self):
        return self.is_file() or self._path in self._directories

    def rglob(self, pattern):
        require(pattern == '*', 'unsupported archive glob')
        return (self._at(path) for path in self._files.keys() | self._directories
                if path != self._path and path.is_relative_to(self._path))

    def iterdir(self):
        return (path for path in self.rglob('*') if path._path.parent == self._path)

    def read_bytes(self):
        return self._files[self._path]

    def read_text(self):
        return self.read_bytes().decode('utf-8')

    def open(self, mode='r'):
        require(mode in ('r', 'rb'), 'archive is read-only')
        return io.BytesIO(self.read_bytes()) if mode == 'rb' else io.StringIO(self.read_text())
