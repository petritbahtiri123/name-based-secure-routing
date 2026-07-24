from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from nbsr import secure_files
from nbsr.secure_files import ensure_private_directory, secure_write_private, secure_write_text


def test_private_write_is_atomic_when_replacement_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    target = tmp_path / "private" / "token.txt"
    ensure_private_directory(target.parent)
    target.write_text("old-value", encoding="utf-8")

    def fail_replace(_source, _target):
        raise OSError("replacement denied")

    monkeypatch.setattr(secure_files.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replacement denied"):
        secure_write_text(target, "new-value")

    assert target.read_text(encoding="utf-8") == "old-value"
    assert list(target.parent.glob(f".{target.name}.*.tmp")) == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode check")
def test_private_write_enforces_posix_directory_and_file_modes(tmp_path: Path):
    target = tmp_path / "private" / "key.pem"

    secure_write_private(target, b"private-key")

    assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name != "nt", reason="Windows DACL check")
def test_private_write_removes_broad_windows_read_access(tmp_path: Path):
    parent = tmp_path / "permissive"
    parent.mkdir()
    grant = subprocess.run(
        ["icacls", str(parent), "/grant", "*S-1-5-32-545:(OI)(CI)(RX)"],
        capture_output=True,
        check=False,
        text=True,
    )
    assert grant.returncode == 0, grant.stdout + grant.stderr
    target = parent / "token.txt"

    secure_write_text(target, "private-token")

    acl = subprocess.run(["icacls", str(target)], capture_output=True, check=False, text=True)
    assert acl.returncode == 0, acl.stdout + acl.stderr
    normalized = acl.stdout.casefold()
    assert "builtin\\users" not in normalized
    assert "everyone" not in normalized
    assert "authenticated users" not in normalized


def test_bootstrap_protects_every_private_key_and_token(tmp_path: Path):
    root = Path(__file__).parents[1]
    output = tmp_path / "bootstrap-output"
    output.mkdir()
    if os.name == "nt":
        grant = subprocess.run(
            ["icacls", str(output), "/grant", "*S-1-5-32-545:(OI)(CI)(RX)"],
            capture_output=True,
            check=False,
            text=True,
        )
        assert grant.returncode == 0, grant.stdout + grant.stderr
    completed = subprocess.run(
        [sys.executable, str(root / "scripts" / "bootstrap.py"), "--output-root", str(output)],
        cwd=root,
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    private_files = [
        output / "secrets" / "identity-private.pem",
        output / "secrets" / "ticket-private.pem",
        output / "secrets" / "name-binding-private.pem",
        output / "secrets" / "demo-ca-private.pem",
        output / "secrets" / "enterprise-control-plane-key.pem",
        output / "secrets" / "enterprise-gateway-key.pem",
        output / "secrets" / "isp-ca-private.pem",
        output / "secrets" / "isp-control-key.pem",
        output / "secrets" / "isp-relay-key.pem",
        output / "secrets" / "isp-origin-key.pem",
        output / "tokens" / "client-allowed.jwt",
        output / "tokens" / "client-denied.jwt",
    ]
    assert all(path.is_file() for path in private_files)
    if os.name == "nt":
        for path in private_files:
            acl = subprocess.run(["icacls", str(path)], capture_output=True, check=False, text=True)
            assert acl.returncode == 0, acl.stdout + acl.stderr
            normalized = acl.stdout.casefold()
            assert "builtin\\users" not in normalized
            assert "everyone" not in normalized
            assert "authenticated users" not in normalized
    else:
        assert stat.S_IMODE((output / "secrets").stat().st_mode) == 0o700
        assert stat.S_IMODE((output / "tokens").stat().st_mode) == 0o700
        assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in private_files)
