from types import SimpleNamespace
from unittest.mock import patch
from scripts import benchmark_evidence_zip as module
import pytest
import hashlib
import pathlib
import tempfile
import unittest
import zipfile
from scripts.benchmark_evidence_zip import create_verified_zip, verify_zip


class EvidenceZipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        (self.root / "evidence").mkdir()
        self.raw = b"actual evidence\n" * 100
        (self.root / "evidence" / "source.json").write_bytes(self.raw)
        self.expected = {
            "evidence/source.json": {
                "bytes": len(self.raw),
                "sha256": hashlib.sha256(self.raw).hexdigest(),
            }
        }

    def test_roundtrip_keeps_original(self):
        result = create_verified_zip(
            self.root, self.root / "archive.zip", self.expected
        )
        self.assertEqual(result["status"], "VERIFIED_ZIP_ORIGINALS_RETAINED")
        self.assertEqual((self.root / "evidence/source.json").read_bytes(), self.raw)
        self.assertEqual(
            verify_zip(self.root / "archive.zip", self.expected), len(self.raw)
        )

    def test_changed_source_rejected(self):
        (self.root / "evidence/source.json").write_bytes(b"changed")
        with self.assertRaises(ValueError):
            create_verified_zip(self.root, self.root / "archive.zip", self.expected)

    def test_existing_archive_never_overwritten(self):
        p = self.root / "archive.zip"
        p.write_bytes(b"old")
        with self.assertRaises(FileExistsError):
            create_verified_zip(self.root, p, self.expected)
        self.assertEqual(p.read_bytes(), b"old")

    def test_unsafe_name_rejected(self):
        for name in (
            "../escape",
            "/absolute",
            "C:/absolute",
            "evidence\\source.json",
            "evidence/../source.json",
        ):
            with self.subTest(name=name), self.assertRaises(ValueError):
                create_verified_zip(
                    self.root,
                    self.root / "archive.zip",
                    {name: next(iter(self.expected.values()))},
                )

    def test_wrong_hash_rejected(self):
        self.expected["evidence/source.json"]["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            create_verified_zip(self.root, self.root / "archive.zip", self.expected)

    def test_archive_budget_enforced(self):
        with self.assertRaises(ValueError):
            create_verified_zip(
                self.root,
                self.root / "archive.zip",
                self.expected,
                maximum_archive_bytes=10,
            )

    def test_extra_member_rejected(self):
        p = self.root / "archive.zip"
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("evidence/source.json", self.raw)
            z.writestr("extra", b"x")
        with self.assertRaises(ValueError):
            verify_zip(p, self.expected)

    def test_duplicate_member_rejected(self):
        import warnings

        p = self.root / "archive.zip"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with zipfile.ZipFile(p, "w") as z:
                z.writestr("evidence/source.json", self.raw)
                z.writestr("evidence/source.json", self.raw)
        with self.assertRaises(ValueError):
            verify_zip(p, self.expected)

    def test_cap_checked_before_parser(self):
        p = self.root / "archive.zip"
        p.write_bytes(b"x" * 100)
        with (
            patch("scripts.benchmark_evidence_zip.zipfile.ZipFile") as parser,
            self.assertRaises(ValueError),
        ):
            verify_zip(p, self.expected, maximum_archive_bytes=99)
        parser.assert_not_called()

    def test_source_symlink_rejected(self):
        path = self.root / "evidence/source.json"
        path.unlink()
        target = self.root / "target"
        target.write_bytes(self.raw)
        try:
            path.symlink_to(target)
        except OSError:
            self.skipTest("symlink unavailable")
        with self.assertRaises(ValueError):
            create_verified_zip(self.root, self.root / "archive.zip", self.expected)

    def test_archive_replacement_during_verify_rejected(self):
        from scripts import benchmark_evidence_zip as evidence_zip

        p = self.root / "archive.zip"
        create_verified_zip(self.root, p, self.expected)
        original = evidence_zip._copy_checked

        def replace(source, row, destination=None):
            original(source, row, destination)
            other = self.root / "replacement"
            other.write_bytes(b"not verified")
            other.replace(p)

        try:
            with (
                patch(
                    "scripts.benchmark_evidence_zip._copy_checked", side_effect=replace
                ),
                self.assertRaises(ValueError),
            ):
                verify_zip(p, self.expected)
        except PermissionError:
            self.skipTest("OS blocks replacement of open file")


if __name__ == "__main__":
    unittest.main()


def stat_copy(info, ctime):
    return SimpleNamespace(
        st_dev=info.st_dev,
        st_ino=info.st_ino,
        st_size=info.st_size,
        st_mtime_ns=info.st_mtime_ns,
        st_ctime_ns=ctime,
        st_mode=info.st_mode,
        st_birthtime_ns=getattr(info, "st_birthtime_ns", None),
    )


def test_cross_api_ctime_difference_preserves_regular_file(tmp_path):
    path = tmp_path / "source"
    path.write_bytes(b"source")
    original = module.os.fstat
    with patch.object(
        module.os,
        "fstat",
        side_effect=lambda fd: stat_copy(original(fd), original(fd).st_ctime_ns + 123),
    ):
        with module._open_regular(path) as stream:
            assert stream.read() == b"source"


def test_fstat_ctime_change_after_open_rejected(tmp_path):
    path = tmp_path / "source"
    path.write_bytes(b"source")
    original = module.os.fstat
    calls = 0

    def changed(fd):
        nonlocal calls
        calls += 1
        info = original(fd)
        return stat_copy(info, info.st_ctime_ns + (123 if calls > 1 else 0))

    with patch.object(module.os, "fstat", side_effect=changed):
        with pytest.raises(ValueError, match="changed"):
            with module._open_regular(path) as stream:
                assert stream.read() == b"source"


def test_lstat_ctime_change_after_open_rejected(tmp_path):
    path = tmp_path / "source"
    path.write_bytes(b"source")
    original = pathlib.Path.lstat
    mutate = False

    def changed(item):
        info = original(item)
        return stat_copy(
            info, info.st_ctime_ns + (123 if item == path and mutate else 0)
        )

    with patch.object(pathlib.Path, "lstat", changed):
        with pytest.raises(ValueError, match="changed"):
            with module._open_regular(path) as stream:
                assert stream.read() == b"source"
                mutate = True
