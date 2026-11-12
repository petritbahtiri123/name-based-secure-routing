"""Bounded source snapshot export; no Docker, fetch, checkout, or private file scan."""
import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path, PurePosixPath

ROOTS = ("client/nbsr-go-client", "interop/nbsr-go-peer", "crates/nbsr-transport",
         "tools/demo-lab", "vectors", "scripts/demo")
EXCLUDED = {".git", ".state", "__pycache__", ".pytest_cache", "target", "test-results",
            ".venv", "node_modules", "runtime", "credentials", "archives", "archive"}
SUFFIXES = {".go", ".rs", ".toml", ".lock", ".mod", ".sum", ".py", ".json", ".html",
            ".js", ".css", ".ps1", ".sh", ".md", ".txt", ".cbor", ".cose", ".bin",
            ".frame", ".hex"}
INVENTORY_SUFFIXES = {".go", ".rs", ".toml", ".lock", ".mod", ".sum", ".py", ".json",
                      ".html", ".js", ".css", ".ps1", ".sh", ".txt", ".cbor", ".cose", ".bin", ".frame", ".hex"}
SPECIAL = {"Dockerfile", "Prepare.Dockerfile", "Dockerfile.dockerignore",
           "Prepare.Dockerfile.dockerignore", "demo-container-worker"}
REQUIRED = {"client/nbsr-go-client/demo/go.mod", "client/nbsr-go-client/demo/go.sum",
            "client/nbsr-go-client/go.mod", "interop/nbsr-go-peer/go.mod",
            "crates/nbsr-transport/Cargo.toml", "crates/nbsr-transport/Cargo.lock",
            "client/nbsr-go-client/demo/testdata/service-a.json",
            "vectors/wp8-local-admission/source.cose",
            "vectors/wp8-local-admission/destination.cose",
            "tools/demo-lab/demo.py", "tools/demo-lab/fixturegen/go.mod",
            "tools/demo-lab/container/Dockerfile",
            "tools/demo-lab/container/demo-container-worker"}
MAX_BYTES = 128 * 1024 * 1024
MAX_FILE = 8 * 1024 * 1024
MAX_FILES = 10000
# Explicit change-owned new source list. Never glob untracked files.
APPROVED_NEW = {
    "tools/demo-lab/" + path for path in (
        "demo.py", "README.md", "fixturegen/go.mod", "fixturegen/main.go",
        "fixturegen/main_test.go", "fixturegen/private_unix.go", "fixturegen/private_windows.go",
        "container/Dockerfile", "container/Prepare.Dockerfile",
        "container/Dockerfile.dockerignore", "container/Prepare.Dockerfile.dockerignore",
        "container/build_image.py", "container/prepare_image.py",
        "container/export_context.py", "container/test_export_context.py",
        "container/test_packaging.py", "container/official-image-pins.json",
        "container/demo-container-worker", "container/README.md",
        "nbsr_demo_lab/__init__.py", "nbsr_demo_lab/container_runner.py",
        "nbsr_demo_lab/coordinator.py", "nbsr_demo_lab/evidence.py", "nbsr_demo_lab/mac.py",
        "nbsr_demo_lab/runner.py", "nbsr_demo_lab/setup.py", "nbsr_demo_lab/supervision.py",
        "nbsr_demo_lab/web.py", "nbsr_demo_lab/worker.py",
        "static/app.js", "static/index.html", "static/style.css",
        "tests/test_app.py", "tests/test_container_runner.py", "tests/test_evidence.py",
        "tests/test_http.py", "tests/test_inventory.py", "tests/test_mac.py",
        "tests/test_runner.py", "tests/test_supervision.py",
    )
} | {"client/nbsr-go-client/demo/internal/config/config_darwin_test.go"} | {"scripts/demo/" + name for name in (
    "setup-demo.ps1", "setup-demo.sh", "start-demo-lab.ps1", "start-demo-lab.sh")}


def selected(name):
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts or str(p) != name or "\\" in name or ":" in name:
        raise ValueError("Noncanonical Git path")
    if not any(name.startswith(root + "/") for root in ROOTS):
        return False
    if any(part.lower() in EXCLUDED for part in p.parts):
        return False
    if p.suffix.lower() in {".pem", ".der", ".key", ".pfx", ".p12", ".zip", ".gz", ".tar", ".exe", ".dll"}:
        return False
    return p.suffix in SUFFIXES or p.name in SPECIAL


def source_entry(name):
    p = PurePosixPath(name)
    return p.suffix in INVENTORY_SUFFIXES or p.name.endswith(("Dockerfile", ".dockerignore")) or p.name == "demo-container-worker"


def safe_path(path):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        try:
            value = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(value.st_mode) or getattr(value, "st_file_attributes", 0) & 0x400:
            raise ValueError("Symlink/reparse path rejected")
    return path


def read_source(path):
    safe_path(path)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_FILE:
        raise ValueError("Source file type/size rejected")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError("Source replaced while opening")
        data = stream.read(MAX_FILE + 1)
        after = os.fstat(stream.fileno())
    safe_path(path)
    if len(data) > MAX_FILE or (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise ValueError("Source changed during export")
    return data


def git(repo, *args):
    env = os.environ.copy()
    env.update(GIT_NO_LAZY_FETCH="1", GIT_OPTIONAL_LOCKS="0")
    result = subprocess.run(["git", *args], cwd=repo, env=env, capture_output=True,
                            timeout=10, check=True)
    if len(result.stdout) > 16 * 1024 * 1024:
        raise ValueError("Git inventory too large")
    return result.stdout


def tracked_sources(repo):
    data = git(repo, "ls-files", "--stage", "-z", "--", *ROOTS)
    names = set()
    for item in data.split(b"\0"):
        if not item:
            continue
        metadata, raw_name = item.split(b"\t", 1)
        mode, _, stage = metadata.decode("ascii").split()
        name = raw_name.decode("utf-8")
        if not selected(name):
            continue
        if stage != "0" or mode not in {"100644", "100755"}:
            raise ValueError("Unmerged, symlink or submodule source rejected")
        names.add(name)
    for name in APPROVED_NEW:
        if (repo / name).exists() or (repo / name).is_symlink():
            names.add(name)
    return names


def export_context(repo, output, *, max_bytes=MAX_BYTES):
    repo, output = safe_path(repo), safe_path(output)
    if not repo.is_dir() or output.exists() or output == repo or output.is_relative_to(repo) or repo.is_relative_to(output):
        raise ValueError("Fresh disjoint output directory required")
    if not output.parent.is_dir():
        raise ValueError("Existing private output parent required")
    names = tracked_sources(repo)
    if len(names) > MAX_FILES or not REQUIRED <= names:
        raise ValueError("Required source missing or inventory too large")
    commit = git(repo, "rev-parse", "HEAD").decode("ascii").strip()
    if not re.fullmatch("[0-9a-f]{40}", commit):
        raise ValueError("Exact commit unavailable")
    # Read before creating output: sparse or deleted tracked inputs fail closed.
    blobs, total = {}, 0
    for name in sorted(names):
        if not selected(name):
            raise ValueError("New source outside allowlist")
        data = read_source(repo / name)
        total += len(data)
        if total > min(max_bytes, MAX_BYTES):
            raise ValueError("Source byte bound exceeded")
        blobs[name] = data
    output.mkdir(mode=0o700)
    files = {}
    for name, data in blobs.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with target.open("xb") as stream:
            stream.write(data)
        files[name] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    # Detect source drift after copying; retain incomplete output on failure.
    for name in names:
        if hashlib.sha256(read_source(repo / name)).hexdigest() != files[name]["sha256"]:
            raise ValueError("Source drift; retained incomplete export must not be built")
    if names != tracked_sources(repo) or commit != git(repo, "rev-parse", "HEAD").decode("ascii").strip():
        raise ValueError("Git source identity changed during export")
    manifest = {"schema": "nbsr-demo-source-export-v1", "source_commit": commit,
                "total_bytes": total, "files": files,
                "source_hashes": {name: item["sha256"] for name, item in files.items() if source_entry(name)}}
    encoded = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    with (output / "source-export.json").open("xb") as stream:
        stream.write(encoded)
    return {"manifest": str(output / "source-export.json"),
            "manifest_sha256": hashlib.sha256(encoded).hexdigest(),
            "files": len(files), "bytes": total}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(export_context(args.repo, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
