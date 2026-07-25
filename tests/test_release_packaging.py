from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGER = ROOT / "scripts" / "package_release.py"
PYTHON_IMAGE = "python:3.13.14-slim-bookworm@sha256:9d7f287598e1a5a978c015ee176d8216435aaf335ed69ac3c38dd1bbb10e8d64"


def load_packager():
    assert PACKAGER.is_file()
    spec = importlib.util.spec_from_file_location("nbsr_package_release", PACKAGER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runtime_support_and_container_are_bounded_and_pinned():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert 'requires-python = ">=3.12,<3.14"' in pyproject
    assert 'target-version = "py313"' in pyproject
    assert "error::DeprecationWarning:nbsr" in pyproject
    assert "error::PendingDeprecationWarning:nbsr" in pyproject
    assert "[build-system]" in pyproject
    assert "[tool.setuptools.packages.find]" in pyproject
    assert f"FROM {PYTHON_IMAGE}" in dockerfile
    assert "COPY constraints/runtime.txt" in dockerfile
    assert "--constraint constraints/runtime.txt" in dockerfile


def test_constraints_are_exact_and_cover_runtime_and_dev():
    runtime = (ROOT / "constraints" / "runtime.txt").read_text(encoding="utf-8").splitlines()
    dev = (ROOT / "constraints" / "dev.txt").read_text(encoding="utf-8").splitlines()

    for lines in (runtime, dev):
        requirements = [line for line in lines if line and not line.startswith("#")]
        assert requirements
        assert all(re.fullmatch(r"[A-Za-z0-9_.-]+==[A-Za-z0-9_.+!-]+", line) for line in requirements)
        assert requirements == sorted(requirements, key=str.casefold)
    assert set(runtime) <= set(dev)
    assert any(line.startswith("pytest==") for line in dev)
    assert any(line.startswith("ruff==") for line in dev)


def test_release_wrappers_require_an_explicit_ref_and_delegate_to_shared_packager():
    powershell = (ROOT / "scripts" / "package-release.ps1").read_text(encoding="utf-8")
    shell = (ROOT / "scripts" / "package-release.sh").read_text(encoding="utf-8")

    assert "[Parameter(Mandatory = $true)]" in powershell
    assert "package_release.py" in powershell
    assert "${1:?" in shell
    assert "package_release.py" in shell
    assert "command -v cygpath" in shell
    assert 'ROOT="$(cygpath -w "$ROOT")"' in shell


def test_packager_rejects_prohibited_paths_and_secret_like_content_without_echoing_values():
    packager = load_packager()

    for path in (
        ".git/config",
        "secrets/demo.pem",
        "tokens/client.jwt",
        ".venv/lib/site.py",
        "dist/old.zip",
        "pkg/__pycache__/module.pyc",
        "generated/client-cert.pem",
    ):
        assert packager.prohibited_path_reason(path)
    assert packager.prohibited_path_reason("docs/security-model.md") is None
    assert packager.prohibited_path_reason(".env.example") is None
    assert packager.prohibited_path_reason(".env.local")

    finding = packager.secret_like_reason(b"prefix\n-----BEGIN " + b"PRIVATE KEY-----\nvalue")
    assert finding == "private-key material"
    assert "value" not in finding


def test_packager_builds_sorted_inventory_and_byte_stable_zip(tmp_path: Path):
    packager = load_packager()
    source = tmp_path / "source"
    source.mkdir()
    (source / "z.txt").write_text("last\n", encoding="utf-8")
    (source / "a.txt").write_text("first\n", encoding="utf-8")

    inventory = packager.build_inventory(source)
    assert [entry.path for entry in inventory] == ["a.txt", "z.txt"]

    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    modes = {"a.txt": "100644", "z.txt": "100644"}
    packager.write_deterministic_zip(source, inventory, modes, first)
    packager.write_deterministic_zip(source, inventory, modes, second)
    assert first.read_bytes() == second.read_bytes()


def test_ignore_files_exclude_release_and_sensitive_local_output():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    for entry in ("dist/", "secrets/", "tokens/", "*.zip", "*.pem", "*.key"):
        assert entry in gitignore
    for entry in ("dist", "secrets", "tokens", "*.zip", "*.pem", "*.key"):
        assert entry in dockerignore
