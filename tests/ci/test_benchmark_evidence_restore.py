import hashlib
import zipfile

import pytest
from scripts import benchmark_evidence_zip as evidence


def fixture(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    data = b"original evidence\n" * 20
    (root / "closed.log").write_bytes(data)
    expected = {
        "closed.log": {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    }
    archive = root / "evidence.zip"
    receipt = evidence.create_verified_zip(
        root, archive, expected, maximum_archive_bytes=4096
    )
    return root, archive, expected, receipt


def test_independent_disk_restore_retains_originals(tmp_path):
    root, archive, expected, receipt = fixture(tmp_path)
    assert hasattr(evidence, "restore_verified_zip"), (
        "independent on-disk restore is missing"
    )
    result = evidence.restore_verified_zip(
        archive,
        tmp_path / "restore",
        expected,
        archive_sha256=receipt["archive_sha256"],
        maximum_archive_bytes=4096,
        maximum_restore_bytes=4096,
    )
    assert result["status"] == "RESTORED_VERIFIED_ORIGINALS_RETAINED"
    assert (tmp_path / "restore/closed.log").read_bytes() == (
        root / "closed.log"
    ).read_bytes()
    assert archive.exists()


@pytest.mark.parametrize("failure", ["digest", "budget", "existing", "redirect"])
def test_restore_fails_closed_without_touching_sources(tmp_path, failure):
    root, archive, expected, receipt = fixture(tmp_path)
    target = tmp_path / "restore"
    digest = receipt["archive_sha256"]
    bound = 4096
    if failure == "digest":
        digest = "0" * 64
    elif failure == "budget":
        bound = 1
    elif failure == "existing":
        target.mkdir()
        (target / "keep").write_bytes(b"keep")
    else:
        try:
            target.symlink_to(root, target_is_directory=True)
        except OSError:
            pytest.skip("OS does not permit test symlink creation")
    with pytest.raises((ValueError, FileExistsError)):
        evidence.restore_verified_zip(
            archive,
            target,
            expected,
            archive_sha256=digest,
            maximum_archive_bytes=4096,
            maximum_restore_bytes=bound,
        )
    assert (root / "closed.log").exists()
    if failure == "existing":
        assert (target / "keep").read_bytes() == b"keep"


def test_restore_rejects_unexpected_archive_member(tmp_path):
    root, archive, expected, receipt = fixture(tmp_path)
    with zipfile.ZipFile(archive, "a") as z:
        z.writestr("../escape", b"bad")
    with pytest.raises(ValueError):
        evidence.restore_verified_zip(
            archive,
            tmp_path / "restore",
            expected,
            archive_sha256=receipt["archive_sha256"],
            maximum_archive_bytes=4096,
            maximum_restore_bytes=4096,
        )
    assert not (tmp_path / "escape").exists()


def test_nested_restore_and_zero_length_members(tmp_path):
    root = tmp_path / "source"
    (root / "nested").mkdir(parents=True)
    (root / "nested/empty.txt").write_bytes(b"")
    expected = {
        "nested/empty.txt": {"bytes": 0, "sha256": hashlib.sha256(b"").hexdigest()}
    }
    archive = root / "evidence.zip"
    receipt = evidence.create_verified_zip(
        root, archive, expected, maximum_archive_bytes=4096
    )
    result = evidence.restore_verified_zip(
        archive,
        tmp_path / "restore",
        expected,
        archive_sha256=receipt["archive_sha256"],
        maximum_archive_bytes=4096,
        maximum_restore_bytes=0,
    )
    assert result["restored_bytes"] == 0
    assert (tmp_path / "restore/nested/empty.txt").read_bytes() == b""


def test_restore_rejects_changed_member_even_with_correct_archive_hash(tmp_path):
    root, archive, expected, _ = fixture(tmp_path)
    # This is a test fixture archive, not user evidence.
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("closed.log", b"wrong bytes")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        evidence.restore_verified_zip(
            archive,
            tmp_path / "restore",
            expected,
            archive_sha256=digest,
            maximum_archive_bytes=4096,
            maximum_restore_bytes=4096,
        )
    assert not (tmp_path / "restore").exists()
    assert (root / "closed.log").exists()


def test_archive_replaced_before_restore_reopen_creates_no_destination(
    tmp_path, monkeypatch
):
    _, archive, expected, receipt = fixture(tmp_path)
    verify = evidence._verify_zip

    def replace_after_verification(*args):
        result = verify(*args)
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("closed.log", b"changed")
        return result

    monkeypatch.setattr(evidence, "_verify_zip", replace_after_verification)
    with pytest.raises(ValueError, match="archive changed before restore"):
        evidence.restore_verified_zip(
            archive,
            tmp_path / "restore",
            expected,
            archive_sha256=receipt["archive_sha256"],
            maximum_archive_bytes=4096,
            maximum_restore_bytes=4096,
        )
    assert not (tmp_path / "restore").exists()


def test_corrupt_restored_file_cannot_receive_success_receipt(tmp_path, monkeypatch):
    root, archive, expected, receipt = fixture(tmp_path)
    target = tmp_path / "restore/closed.log"
    open_regular = evidence._open_regular

    def corrupt_before_independent_read(path):
        if path == target:
            path.write_bytes(b"bad")
        return open_regular(path)

    monkeypatch.setattr(evidence, "_open_regular", corrupt_before_independent_read)
    with pytest.raises(ValueError, match="member identity mismatch"):
        evidence.restore_verified_zip(
            archive,
            target.parent,
            expected,
            archive_sha256=receipt["archive_sha256"],
            maximum_archive_bytes=4096,
            maximum_restore_bytes=4096,
        )
    assert target.read_bytes() == b"bad"
    assert (root / "closed.log").read_bytes().startswith(b"original evidence")
