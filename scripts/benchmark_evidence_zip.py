"""Bounded ZIP creation for explicitly inventoried, quiescent evidence.

Caller establishes closed writers and reserves construction/output space. This
helper never removes sources and never declares a benchmark valid. A failed ZIP
is retained as partial evidence; no success receipt is returned.
"""

from contextlib import contextmanager
import hashlib
import os
from pathlib import Path, PurePosixPath
import stat
import zipfile


def _inventory(expected):
    if not isinstance(expected, dict) or not 0 < len(expected) <= 10000:
        raise ValueError("explicit bounded inventory required")
    for name, row in expected.items():
        p = PurePosixPath(name)
        if (
            not name
            or p.is_absolute()
            or p.as_posix() != name
            or any(x in ("", ".", "..") for x in name.split("/"))
            or any(x in name for x in ("\\", ":", "\0", "\r", "\n"))
        ):
            raise ValueError("unsafe member name")
        if (
            type(row["bytes"]) is not int
            or row["bytes"] < 0
            or len(row["sha256"]) != 64
            or any(c not in "0123456789abcdef" for c in row["sha256"])
        ):
            raise ValueError("invalid member identity")


def _plain(path):
    for part in (path, *path.parents):
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise ValueError("redirected evidence path")


def _cross_api_identity(info):
    # Windows lstat/fstat can represent ctime differently. Compare stable file
    # identity across APIs; retain each API's own ctime baseline below.
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        stat.S_IFMT(info.st_mode),
        getattr(info, "st_birthtime_ns", None),
    )


def _identity(info):
    return _cross_api_identity(info), info.st_ctime_ns


@contextmanager
def _open_regular(path):
    _plain(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("regular file required")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as raw:
        opened = os.fstat(raw.fileno())
        if _cross_api_identity(opened) != _cross_api_identity(before):
            raise ValueError("file replaced during open")
        yield raw
        _plain(path)
        if _identity(os.fstat(raw.fileno())) != _identity(opened) or _identity(
            path.lstat()
        ) != _identity(before):
            raise ValueError("file changed during verification")


def _copy_checked(source, row, destination=None):
    total, digest = 0, hashlib.sha256()
    while chunk := source.read(65536):
        total += len(chunk)
        if total > row["bytes"]:
            raise ValueError("member size exceeded")
        digest.update(chunk)
        if destination is not None:
            destination.write(chunk)
    if total != row["bytes"] or digest.hexdigest() != row["sha256"]:
        raise ValueError("member identity mismatch")


class _BoundedFile:
    def __init__(self, raw, maximum):
        self.raw, self.maximum = raw, maximum

    def write(self, data):
        if self.raw.tell() + len(data) > self.maximum:
            raise ValueError("archive budget exceeded")
        return self.raw.write(data)

    def tell(self):
        return self.raw.tell()

    def seek(self, *args):
        return self.raw.seek(*args)

    def flush(self):
        return self.raw.flush()


def _verify_zip(archive, expected, maximum_archive_bytes):
    _inventory(expected)
    if type(maximum_archive_bytes) is not int or maximum_archive_bytes <= 0:
        raise ValueError("positive archive bound required")
    with _open_regular(Path(archive)) as raw:
        size = os.fstat(raw.fileno()).st_size
        if size > maximum_archive_bytes:
            raise ValueError("archive budget exceeded before parsing")
        digest = hashlib.sha256()
        while chunk := raw.read(65536):
            digest.update(chunk)
        raw.seek(0)
        with zipfile.ZipFile(raw) as z:
            infos = z.infolist()
            if len(infos) != len(expected) or {i.filename for i in infos} != set(
                expected
            ):
                raise ValueError("archive inventory mismatch")
            for info in infos:
                mode = info.external_attr >> 16
                if (
                    info.flag_bits & 1
                    or info.is_dir()
                    or stat.S_IFMT(mode) not in (0, stat.S_IFREG)
                    or info.file_size != expected[info.filename]["bytes"]
                ):
                    raise ValueError("unexpected member type or size")
                with z.open(info) as source:
                    _copy_checked(source, expected[info.filename])
    return size, digest.hexdigest()


def verify_zip(archive, expected, *, maximum_archive_bytes=16 * 1024**2):
    """Bounded same-descriptor decompress/hash pass; no source deletion."""
    _verify_zip(archive, expected, maximum_archive_bytes)
    return sum(row["bytes"] for row in expected.values())


def create_verified_zip(root, archive, expected, *, maximum_archive_bytes=16 * 1024**2):
    _inventory(expected)
    if type(maximum_archive_bytes) is not int or maximum_archive_bytes <= 0:
        raise ValueError("positive reserved archive budget required")
    root, archive = Path(root).absolute(), Path(archive).absolute()
    _plain(root)
    _plain(archive)
    if not archive.is_relative_to(root) or archive in [root / n for n in expected]:
        raise ValueError("separate archive inside evidence root required")
    for name, row in expected.items():
        path = root / name
        _plain(path)
        with _open_regular(path) as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise ValueError("regular source required")
            _copy_checked(source, row)
    with archive.open("xb") as raw:
        with zipfile.ZipFile(
            _BoundedFile(raw, maximum_archive_bytes),
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as z:
            for name, row in sorted(expected.items()):
                path = root / name
                _plain(path)
                info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100600 << 16
                with _open_regular(path) as source, z.open(info, "w") as destination:
                    if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                        raise ValueError("regular source required")
                    _copy_checked(source, row, destination)
        raw.flush()
        os.fsync(raw.fileno())
    size, digest = _verify_zip(archive, expected, maximum_archive_bytes)
    return dict(
        status="VERIFIED_ZIP_ORIGINALS_RETAINED",
        archive_bytes=size,
        archive_sha256=digest,
        source_bytes=sum(r["bytes"] for r in expected.values()),
        members=expected,
    )


def restore_verified_zip(
    archive,
    destination,
    expected,
    *,
    archive_sha256,
    maximum_archive_bytes,
    maximum_restore_bytes,
):
    """Independently restore and reread bytes; never delete original evidence.

    Caller reserves archive + full restore + metadata capacity and establishes
    quiescence. Destination must not exist. Failure retains partial restoration
    for diagnosis; neither a partial restore nor this receipt authorizes pruning.
    """
    _inventory(expected)
    total = sum(row["bytes"] for row in expected.values())
    if (
        type(maximum_restore_bytes) is not int
        or not 0 <= total <= maximum_restore_bytes
    ):
        raise ValueError("restore budget exceeded")
    if (
        type(archive_sha256) is not str
        or len(archive_sha256) != 64
        or any(c not in "0123456789abcdef" for c in archive_sha256)
    ):
        raise ValueError("explicit archive digest required")
    _, digest = _verify_zip(archive, expected, maximum_archive_bytes)
    if digest != archive_sha256:
        raise ValueError("archive receipt digest mismatch")
    destination = Path(destination).absolute()
    _plain(destination)
    # Reopen under the same-descriptor guard, and rehash before parsing or writing.
    with _open_regular(Path(archive)) as raw:
        if os.fstat(raw.fileno()).st_size > maximum_archive_bytes:
            raise ValueError("archive budget exceeded")
        digest = hashlib.sha256()
        while chunk := raw.read(65536):
            digest.update(chunk)
        if digest.hexdigest() != archive_sha256:
            raise ValueError("archive changed before restore")
        raw.seek(0)
        destination.mkdir(exist_ok=False)
        with zipfile.ZipFile(raw) as z:
            for name, row in sorted(expected.items()):
                target = destination / name
                target.parent.mkdir(parents=True, exist_ok=True)
                _plain(target)
                with target.open("xb") as output, z.open(name) as source:
                    _copy_checked(source, row, output)
                    output.flush()
                    os.fsync(output.fileno())
        # Read the persisted files independently rather than trusting write results.
        for name, row in sorted(expected.items()):
            with _open_regular(destination / name) as restored:
                _copy_checked(restored, row)
    return dict(
        status="RESTORED_VERIFIED_ORIGINALS_RETAINED",
        archive_sha256=archive_sha256,
        restored_bytes=total,
        members=expected,
    )
