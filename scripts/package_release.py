from __future__ import annotations

import argparse
import hashlib
import io
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import NamedTuple

PYTHON_VALIDATION_IMAGE = "python:3.13.14-slim-bookworm@sha256:9d7f287598e1a5a978c015ee176d8216435aaf335ed69ac3c38dd1bbb10e8d64"
FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
PROHIBITED_DIRECTORY_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "dist",
    "secrets",
    "test-results",
    "tokens",
    "venv",
}
PROHIBITED_FILE_SUFFIXES = {
    ".cer",
    ".crt",
    ".key",
    ".log",
    ".p12",
    ".pem",
    ".pfx",
    ".pyc",
    ".pyo",
    ".tar",
    ".tgz",
    ".zip",
}
SECRET_PATTERNS = (
    (re.compile(rb"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"), "private-key material"),
    (re.compile(rb"\bAKIA[0-9A-Z]{16}\b"), "AWS access-key material"),
    (re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "GitHub token material"),
    (re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{16,}\b"), "Slack token material"),
)


class ReleaseError(RuntimeError):
    pass


class InventoryEntry(NamedTuple):
    path: str
    sha256: str
    size: int


def _run(
    args: list[str],
    *,
    cwd: Path,
    capture_output: bool = True,
    text: bool = True,
) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            args,
            cwd=cwd,
            check=True,
            capture_output=capture_output,
            text=text,
        )
    except FileNotFoundError as exc:
        raise ReleaseError(f"Required command is unavailable: {args[0]}") from exc
    except subprocess.CalledProcessError as exc:
        raise ReleaseError(f"Command failed without producing a release: {args[0]}") from exc


def _git(repo: Path, *args: str, text: bool = True) -> str | bytes:
    git_executable = os.environ.get("NBSR_GIT_EXECUTABLE") or "git"
    return _run([git_executable, *args], cwd=repo, text=text).stdout


def resolve_commit(repo: Path, ref: str) -> str:
    commit = str(_git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")).strip()
    if not re.fullmatch(r"[0-9a-f]{40,64}", commit):
        raise ReleaseError("Git returned an invalid commit identifier.")
    return commit


def ensure_tracked_source_clean(repo: Path) -> None:
    dirty = str(_git(repo, "status", "--porcelain=v1", "--untracked-files=no"))
    if dirty:
        raise ReleaseError("Tracked source is dirty; refusing to package uncommitted content.")


def prohibited_path_reason(path: str) -> str | None:
    if "\\" in path:
        return "non-portable path separator"
    pure = PurePosixPath(path)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        return "unsafe archive path"
    lowered_parts = tuple(part.casefold() for part in pure.parts)
    if any(part in PROHIBITED_DIRECTORY_NAMES or part.startswith(".pytest-") for part in lowered_parts):
        return "prohibited local or generated directory"
    name = lowered_parts[-1]
    if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
        return "local environment configuration"
    lowered_path = path.casefold()
    if lowered_path.endswith(".tar.gz"):
        return "previous archive"
    if any(name.endswith(suffix) for suffix in PROHIBITED_FILE_SUFFIXES):
        return "prohibited generated, credential, cache, log, or archive file"
    return None


def secret_like_reason(content: bytes) -> str | None:
    for pattern, reason in SECRET_PATTERNS:
        if pattern.search(content):
            return reason
    return None


def git_modes(repo: Path, commit: str) -> dict[str, str]:
    raw = bytes(_git(repo, "ls-tree", "-r", "-z", commit, text=False))
    modes: dict[str, str] = {}
    for record in raw.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode, object_type, _object_id = metadata.split(b" ", 2)
        if object_type != b"blob":
            raise ReleaseError("Submodules and non-blob Git entries are not release-packaged.")
        try:
            path = raw_path.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ReleaseError("A Git path is not valid UTF-8.") from exc
        reason = prohibited_path_reason(path)
        if reason:
            raise ReleaseError(f"Prohibited release path ({reason}): {path}")
        modes[path] = mode.decode("ascii")
    return modes


def extract_git_archive(repo: Path, commit: str, destination: Path) -> None:
    archive = bytes(_git(repo, "archive", "--format=tar", commit, text=False))
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as source:
        for member in source.getmembers():
            path = member.name.rstrip("/")
            if not path:
                continue
            reason = prohibited_path_reason(path)
            if reason:
                raise ReleaseError(f"Prohibited release path ({reason}): {path}")
            target = destination.joinpath(*PurePosixPath(path).parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise ReleaseError(f"Unsupported Git archive entry type: {path}")
            target.parent.mkdir(parents=True, exist_ok=True)
            extracted = source.extractfile(member)
            if extracted is None:
                raise ReleaseError(f"Unable to read Git archive entry: {path}")
            target.write_bytes(extracted.read())


def build_inventory(root: Path) -> list[InventoryEntry]:
    entries: list[InventoryEntry] = []
    for path in sorted((path for path in root.rglob("*") if path.is_file()), key=lambda item: item.as_posix().casefold()):
        if path.is_symlink():
            raise ReleaseError("Symbolic links are not release-packaged.")
        relative = path.relative_to(root).as_posix()
        reason = prohibited_path_reason(relative)
        if reason:
            raise ReleaseError(f"Prohibited release path ({reason}): {relative}")
        content = path.read_bytes()
        secret_reason = secret_like_reason(content)
        if secret_reason:
            raise ReleaseError(f"Suspected {secret_reason} in release path: {relative}")
        entries.append(InventoryEntry(relative, hashlib.sha256(content).hexdigest(), len(content)))
    return entries


def write_deterministic_zip(
    source: Path,
    inventory: list[InventoryEntry],
    modes: dict[str, str],
    output: Path,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
            for entry in inventory:
                info = zipfile.ZipInfo(entry.path, FIXED_ZIP_TIMESTAMP)
                info.create_system = 3
                permissions = 0o755 if modes.get(entry.path) == "100755" else 0o644
                info.external_attr = permissions << 16
                info.compress_type = zipfile.ZIP_STORED
                archive.writestr(info, (source / entry.path).read_bytes(), compress_type=zipfile.ZIP_STORED)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def extract_and_verify_zip(
    archive_path: Path,
    destination: Path,
    intended_inventory: list[InventoryEntry],
) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            reason = prohibited_path_reason(info.filename)
            if reason:
                raise ReleaseError(f"Prohibited extracted path ({reason}): {info.filename}")
            if info.is_dir():
                continue
            target = destination.joinpath(*PurePosixPath(info.filename).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(info))
    extracted_inventory = build_inventory(destination)
    if extracted_inventory != intended_inventory:
        raise ReleaseError("Extracted ZIP inventory differs from the intended Git source inventory.")


def write_inventory(inventory: list[InventoryEntry], path: Path) -> None:
    content = "".join(f"{entry.sha256}  {entry.path}\n" for entry in inventory)
    path.write_text(content, encoding="utf-8", newline="\n")


def write_sha256_sidecar(archive_path: Path, path: Path) -> str:
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    path.write_text(f"{digest}  {archive_path.name}\n", encoding="utf-8", newline="\n")
    return digest


def validate_extracted_source(source: Path) -> None:
    mount = f"type=bind,source={source.resolve()},target=/source,readonly"
    command = " && ".join(
        (
            "cp -a /source /tmp/src",
            "cd /tmp/src",
            "python -m pip install --disable-pip-version-check --no-cache-dir --constraint constraints/dev.txt '.[dev]'",
            "python -m pytest -q -p no:cacheprovider --basetemp /tmp/nbsr-pytest",
            "python -m ruff check --no-cache .",
            "python -m ruff format --check --no-cache .",
        )
    )
    _run(
        [
            "docker",
            "run",
            "--rm",
            "--mount",
            mount,
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            PYTHON_VALIDATION_IMAGE,
            "sh",
            "-ceu",
            command,
        ],
        cwd=source,
        capture_output=False,
    )


def build_release(repo: Path, ref: str) -> tuple[Path, Path, Path, str]:
    repo = repo.resolve()
    if not (repo / ".git").exists():
        raise ReleaseError("Repository root does not contain .git metadata.")
    ensure_tracked_source_clean(repo)
    commit = resolve_commit(repo, ref)
    print(f"Resolved release commit: {commit}")
    modes = git_modes(repo, commit)

    output_dir = repo / "dist"
    archive_path = output_dir / f"nbsr-{commit[:12]}.zip"
    inventory_path = output_dir / f"nbsr-{commit[:12]}.inventory.sha256"
    sha256_path = output_dir / f"nbsr-{commit[:12]}.zip.sha256"

    with tempfile.TemporaryDirectory(prefix="nbsr-release-") as temporary:
        temporary_root = Path(temporary)
        source = temporary_root / "source"
        extracted = temporary_root / "extracted"
        extract_git_archive(repo, commit, source)
        inventory = build_inventory(source)
        if set(modes) != {entry.path for entry in inventory}:
            raise ReleaseError("Git tree and release source inventory differ.")
        write_deterministic_zip(source, inventory, modes, archive_path)
        extract_and_verify_zip(archive_path, extracted, inventory)
        validate_extracted_source(extracted)

    output_dir.mkdir(parents=True, exist_ok=True)
    write_inventory(inventory, inventory_path)
    digest = write_sha256_sidecar(archive_path, sha256_path)
    print(f"Verified release ZIP: {archive_path}")
    print(f"Content inventory: {inventory_path}")
    print(f"SHA-256: {digest}")
    return archive_path, inventory_path, sha256_path, digest


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and validate a deterministic NBSR release ZIP from an explicit Git ref.")
    parser.add_argument("ref", help="Explicit Git commit or ref to package.")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        build_release(args.repo_root, args.ref)
    except ReleaseError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
