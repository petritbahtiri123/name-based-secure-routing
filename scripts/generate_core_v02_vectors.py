from __future__ import annotations

import argparse
import shutil
import sys
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.core_v02_vectors.generate import GeneratedPackage, build_package
from scripts.core_v02_vectors.manifest import (
    dump_manifest,
    load_manifest,
    validate_package,
)


def _validate_target(output: Path) -> Path:
    if output.name != "core-v0.2":
        raise ValueError("output directory must be named exactly core-v0.2")
    if output.is_symlink():
        raise ValueError("core-v0.2 output cannot be a symlink")
    parent = output.parent.resolve()
    resolved = output.resolve()
    if resolved.parent != parent:
        raise ValueError("core-v0.2 output escapes its parent")
    return resolved


def _expected_files(package: GeneratedPackage) -> dict[str, bytes]:
    files = dict(package.file_map())
    files["manifest.json"] = dump_manifest(package.manifest)
    return files


def _actual_files(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def _validate_owned_existing(output: Path) -> None:
    if not output.exists():
        return
    if not output.is_dir() or not (output / "manifest.json").is_file():
        raise ValueError("existing target is not an owned package")
    try:
        manifest = load_manifest(output / "manifest.json")
        validate_package(output, manifest)
    except ValueError as exc:
        raise ValueError("existing target is not an owned package") from exc


def _write_files(root: Path, files: dict[str, bytes]) -> None:
    for relative, payload in sorted(files.items()):
        target = root / Path(*relative.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)


def _sync_files(root: Path, files: dict[str, bytes]) -> None:
    existing = {path.relative_to(root).as_posix(): path for path in root.rglob("*") if path.is_file()}
    for relative, path in existing.items():
        if relative not in files:
            path.unlink()
    _write_files(root, files)
    for directory in sorted(
        (path for path in root.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        try:
            directory.rmdir()
        except OSError:
            pass


def write_package(output: Path, package: GeneratedPackage) -> None:
    target = _validate_target(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    _validate_owned_existing(target)
    expected = _expected_files(package)
    preserved = (
        {path: payload for path, payload in _actual_files(target).items() if path.startswith("wp4-exporter/")}
        if target.exists()
        else {}
    )
    written = expected | preserved
    temporary = target.parent / f".core-v0.2-write-{uuid4().hex}"
    temporary.mkdir()
    try:
        _write_files(temporary, expected)
        manifest = load_manifest(temporary / "manifest.json")
        validate_package(temporary, manifest)
        if _actual_files(temporary) != expected:
            raise ValueError("generated package file set is incomplete")
        previous = _actual_files(target) if target.exists() else None
        if not target.exists():
            target.mkdir()
        try:
            _sync_files(target, written)
            validate_package(target, load_manifest(target / "manifest.json"))
            if _actual_files(target) != written:
                raise ValueError("written package differs from validated staging")
        except BaseException:
            if previous is None:
                shutil.rmtree(target)
            else:
                _sync_files(target, previous)
            raise
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def check_package(committed: Path, package: GeneratedPackage) -> None:
    target = _validate_target(committed)
    if not target.is_dir():
        raise ValueError("package drift: committed directory is missing")
    expected = _expected_files(package)
    actual = {path: payload for path, payload in _actual_files(target).items() if not path.startswith("wp4-exporter/")}
    differences: list[str] = []
    for path in sorted(set(expected) | set(actual)):
        old = actual.get(path)
        new = expected.get(path)
        if old == new:
            continue
        old_hash = "missing" if old is None else sha256(old).hexdigest()
        new_hash = "missing" if new is None else sha256(new).hexdigest()
        differences.append(f"{path}: {old_hash} -> {new_hash}")
    if differences:
        raise ValueError("package drift:\n" + "\n".join(differences))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate or verify NBSR Core v0.2 deterministic vectors.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", type=Path, metavar="DIRECTORY")
    mode.add_argument("--check", type=Path, metavar="DIRECTORY")
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    package = build_package()
    try:
        if arguments.write is not None:
            write_package(arguments.write, package)
            print(f"wrote {arguments.write}")
        else:
            check_package(arguments.check, package)
            print(f"verified {arguments.check}")
    except ValueError as exc:
        print(str(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
