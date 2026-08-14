from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tomllib


ORIGINAL_DEPENDENCY_FILES = {
    "crates/nbsr-transport/Cargo.lock",
    "crates/nbsr-transport/Cargo.toml",
    "pyproject.toml",
    "tools/core-v02-node-verifier/package.json",
    "verifiers/federation-go/go.mod",
    "verifiers/federation-node/package.json",
}
TASK10B_DEPENDENCY_FILES = {"interop/nbsr-go-peer/go.mod", "interop/nbsr-go-peer/go.sum"}
DEPENDENCY_NAMES = {"Cargo.lock", "Cargo.toml", "go.mod", "go.sum", "package.json", "package-lock.json", "pyproject.toml"}
PRIVATE_SUFFIXES = {".env", ".key", ".p12", ".pfx", ".pkcs8"}
BINARY_SUFFIXES = {".bin", ".cbor", ".cose", ".pcapng"}
SECRET_MARKERS = (
    b"-----BEGIN PRIVATE KEY-----",
    b"-----BEGIN RSA PRIVATE KEY-----",
    b"-----BEGIN EC PRIVATE KEY-----",
    b"AKIA",
)
TEXT_SECRET = re.compile(r"(?im)^\s*(?:password|api[_-]?key|client[_-]?secret)\s*[:=]\s*\S+")
IPV4 = re.compile(rb"(?<![0-9])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9])")


def _relative(root: Path, path: Path) -> str:
    resolved = path.resolve(strict=True)
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(f"path escapes repository: {path}") from exc


def dependency_inspection(root: Path) -> str:
    found = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and path.name in DEPENDENCY_NAMES
        and ".git" not in path.parts
        and ".worktrees" not in path.relative_to(root).parts
    }
    expected = ORIGINAL_DEPENDENCY_FILES | TASK10B_DEPENDENCY_FILES
    if found != expected:
        raise ValueError(f"dependency manifest inventory differs: {sorted(found ^ expected)}")
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--", *sorted(ORIGINAL_DEPENDENCY_FILES)],
        cwd=root,
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    if status.strip():
        raise ValueError(f"Task 10 changed dependency authority:\n{status}")
    lock = json.loads((root / "interop/nbsr-go-peer/dependency-lock.json").read_text(encoding="utf-8"))
    if set(lock) != {"schema", "reason", "files"} or lock["schema"] != "nbsr-wp8-task10b-isolated-go-dependencies-v1":
        raise ValueError("Task 10B dependency lock schema differs")
    entries = {entry["path"]: entry for entry in lock["files"]}
    if set(entries) != TASK10B_DEPENDENCY_FILES or len(lock["files"]) != len(entries):
        raise ValueError("Task 10B dependency lock paths differ")
    for relative, entry in entries.items():
        if set(entry) != {"path", "length", "sha256"}:
            raise ValueError(f"Task 10B dependency entry differs: {relative}")
        wire = (root / relative).read_bytes()
        if len(wire) != entry["length"] or hashlib.sha256(wire).hexdigest() != entry["sha256"]:
            raise ValueError(f"Task 10B dependency digest differs: {relative}")

    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    python_count = len(pyproject["project"].get("dependencies", []))
    cargo = tomllib.loads((root / "crates/nbsr-transport/Cargo.lock").read_text(encoding="utf-8"))
    cargo_count = len(cargo.get("package", []))
    node_count = 0
    for relative in (
        "tools/core-v02-node-verifier/package.json",
        "verifiers/federation-node/package.json",
    ):
        package = json.loads((root / relative).read_text(encoding="utf-8"))
        node_count += sum(len(package.get(key, {})) for key in ("dependencies", "devDependencies"))
    go_text = (root / "verifiers/federation-go/go.mod").read_text(encoding="utf-8")
    go_count = len(re.findall(r"(?m)^\s*[A-Za-z0-9_.~/-]+\s+v[0-9]", go_text))
    peer_go = (root / "interop/nbsr-go-peer/go.mod").read_text(encoding="utf-8")
    peer_go_count = len(re.findall(r"(?m)^\s*[A-Za-z0-9_.~/-]+\s+v[0-9]", peer_go))
    return f"dependency inspection: PASS (python={python_count}, cargo-lock={cargo_count}, node={node_count}, task9-go={go_count}, task10b-go={peer_go_count}; original manifests unchanged, isolated overlay locked)"


def _privacy_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for relative in (
        "crates/nbsr-transport/src",
        "nbsr/federation",
        "evidence/wp8-task10",
        "evidence/wp8-task10b",
        "interop/nbsr-go-peer",
        "scripts/capture_wp8_task10b_interop.ps1",
        "scripts/verify_wp8_task10b.py",
        "vectors/wp8-f75-route-open",
        "vectors/wp8-local-admission",
    ):
        base = root / relative
        if base.exists():
            if base.is_file() or base.is_symlink():
                paths.append(base)
                continue
            paths.extend(path for path in base.rglob("*") if "__pycache__" not in path.parts and (path.is_file() or path.is_symlink()))
    return paths


def privacy_scan(root: Path) -> str:
    scanned = 0
    for path in _privacy_paths(root):
        relative = _relative(root, path)
        if path.is_symlink():
            raise ValueError(f"privacy scope contains symlink: {relative}")
        if path.suffix.lower() in PRIVATE_SUFFIXES:
            raise ValueError(f"credential-like file is forbidden: {relative}")
        wire = path.read_bytes()
        scanned += 1
        if any(marker in wire for marker in SECRET_MARKERS):
            raise ValueError(f"private credential marker in {relative}")
        if path.suffix.lower() not in BINARY_SUFFIXES:
            text = wire.decode("utf-8", errors="strict")
            if TEXT_SECRET.search(text):
                raise ValueError(f"credential assignment in {relative}")
        if relative.startswith(("evidence/wp8-task10/", "evidence/wp8-task10b/")):
            for match in IPV4.findall(wire):
                if match != b"127.0.0.1":
                    raise ValueError(f"non-loopback address in public evidence {relative}: {match.decode()}")
            for forbidden in (b"subscriber", b"origin.internal", b"NBSR-WP8-TASK10-LIVE-v1", b"NBSR-WP8-TASK10B-INDEPENDENT-WIRE"):
                if forbidden in wire:
                    raise ValueError(f"privacy marker in public evidence {relative}: {forbidden!r}")
    return f"repository privacy/secret scan: PASS ({scanned} scoped files)"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("dependencies", "privacy"))
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    try:
        result = dependency_inspection(root) if args.mode == "dependencies" else privacy_scan(root)
    except (OSError, UnicodeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"{args.mode} inspection: FAIL: {exc}", file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
