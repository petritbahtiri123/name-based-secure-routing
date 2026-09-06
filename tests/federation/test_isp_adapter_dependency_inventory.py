"""The approved ISP adapter adds one manifest, never dependency authority."""

from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from scripts import verify_wp8_repository_safety as safety


ROOT = Path(__file__).resolve().parents[2]
ADAPTER = "deploy/isp-federation-poc/adapter/go.mod"
APPROVED = "module nbsr.local/isp-federation-poc/adapter\n\ngo 1.26.5\n"


@pytest.fixture
def repository(tmp_path, monkeypatch):
    paths = (
        safety.ORIGINAL_DEPENDENCY_FILES | safety.TASK10B_DEPENDENCY_FILES
        | safety.TRANCHE2B_DEPENDENCY_FILES | safety.DEMO_DEPENDENCY_FILES
        | {ADAPTER, "interop/nbsr-go-peer/dependency-lock.json"}
    )
    for relative in paths:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)

    def clean_status(command, **kwargs):
        assert command == [
            "git", "status", "--porcelain=v1", "--",
            *sorted(safety.ORIGINAL_DEPENDENCY_FILES),
        ]
        assert kwargs["cwd"] == tmp_path
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(safety.subprocess, "run", clean_status)
    return tmp_path


def test_approved_stdlib_adapter_is_accepted(repository):
    assert "PASS" in safety.dependency_inspection(repository)


@pytest.mark.parametrize("text", [
    APPROVED.replace("nbsr.local/isp-federation-poc/adapter", "example.invalid/other"),
    APPROVED.replace("1.26.5", "1.26.6"),
    APPROVED + "require example.invalid/dependency v1.0.0\n",
    APPROVED + "require (\nexample.invalid/dependency v1.0.0\n)\n",
    APPROVED + "replace example.invalid/dependency => ../dependency\n",
    APPROVED + "toolchain go1.26.5\n",
])
def test_adapter_declarations_cannot_expand(repository, text):
    (repository / ADAPTER).write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="ISP adapter declarations differ"):
        safety.dependency_inspection(repository)


@pytest.mark.parametrize("relative", [
    "deploy/isp-federation-poc/adapter/go.sum",
    "deploy/isp-federation-poc/unapproved/go.mod",
])
def test_unexpected_manifest_still_rejected(repository, relative):
    path = repository / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="manifest inventory differs"):
        safety.dependency_inspection(repository)


def test_missing_adapter_still_rejected(repository):
    (repository / ADAPTER).unlink()
    with pytest.raises(ValueError, match="manifest inventory differs"):
        safety.dependency_inspection(repository)


def test_existing_lock_digest_check_preserved(repository):
    with (repository / "interop/nbsr-go-peer/go.sum").open("a") as stream:
        stream.write("\nchanged\n")
    with pytest.raises(ValueError, match="dependency digest differs"):
        safety.dependency_inspection(repository)


def test_original_manifest_status_check_preserved(repository, monkeypatch):
    monkeypatch.setattr(safety.subprocess, "run", lambda *a, **k: SimpleNamespace(
        stdout=" M pyproject.toml\n"))
    with pytest.raises(ValueError, match="changed dependency authority"):
        safety.dependency_inspection(repository)
