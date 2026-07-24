from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


_WINDOWS_BROAD_SIDS = ("*S-1-1-0", "*S-1-5-11", "*S-1-5-32-545")
_WINDOWS_SYSTEM_SID = "*S-1-5-18"
_WINDOWS_ADMINISTRATORS_SID = "*S-1-5-32-544"


def ensure_private_directory(path: Path | str) -> Path:
    directory = Path(path)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == "nt":
        _harden_windows_acl(directory, directory=True)
    else:
        directory.chmod(0o700)
    return directory


def secure_write_private(path: Path | str, data: bytes) -> None:
    if not isinstance(data, bytes):
        raise TypeError("Private file data must be bytes")
    target = Path(path)
    ensure_private_directory(target.parent)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
    )
    temporary = Path(temporary_name)
    try:
        if os.name == "nt":
            os.close(file_descriptor)
            file_descriptor = -1
            _harden_windows_acl(temporary, directory=False)
            with temporary.open("wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        else:
            os.fchmod(file_descriptor, 0o600)
            with os.fdopen(file_descriptor, "wb") as stream:
                file_descriptor = -1
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        os.replace(temporary, target)
        if os.name == "nt":
            _harden_windows_acl(target, directory=False)
        else:
            target.chmod(0o600)
    finally:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        temporary.unlink(missing_ok=True)


def secure_write_text(path: Path | str, text: str) -> None:
    if not isinstance(text, str):
        raise TypeError("Private text must be a string")
    secure_write_private(path, text.encode("utf-8"))


def _harden_windows_acl(path: Path, *, directory: bool) -> None:
    principal = _windows_principal()
    permission = "(OI)(CI)(F)" if directory else "(F)"
    _run_icacls(
        path,
        "/inheritance:r",
        "/grant:r",
        f"{principal}:{permission}",
        f"{_WINDOWS_SYSTEM_SID}:{permission}",
        f"{_WINDOWS_ADMINISTRATORS_SID}:{permission}",
    )
    _run_icacls(path, "/remove:g", *_WINDOWS_BROAD_SIDS)


def _windows_principal() -> str:
    completed = subprocess.run(
        ["whoami"],
        capture_output=True,
        check=False,
        text=True,
        shell=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    principal = completed.stdout.strip()
    if completed.returncode != 0 or not principal:
        raise OSError("Could not identify the current Windows principal")
    return principal


def _run_icacls(path: Path, *arguments: str) -> None:
    completed = subprocess.run(
        ["icacls", str(path), *arguments],
        capture_output=True,
        check=False,
        text=True,
        shell=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise OSError(f"Could not protect private path: {detail}")
