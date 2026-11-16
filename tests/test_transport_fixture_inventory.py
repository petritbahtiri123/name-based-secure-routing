from pathlib import Path
import runpy
import subprocess

import pytest


MODULE = Path(__file__).with_name("test_wp3_rust_transport_isolation.py")


def subject():
    return runpy.run_path(str(MODULE))


def fake_inventory(monkeypatch, data):
    def run(args, **kwargs):
        assert args == ["git", "ls-files", "-z", "--", "crates/nbsr-transport"]
        assert kwargs == {"cwd": MODULE.resolve().parents[1], "check": True,
                          "capture_output": True, "timeout": 10}
        return subprocess.CompletedProcess(args, 0, stdout=data)
    monkeypatch.setattr(subprocess, "run", run)


@pytest.mark.parametrize("suffix", [".cer", ".crt", ".der", ".key", ".p12", ".pem", ".pfx"])
def test_tracked_forbidden_suffix_is_reported_without_reading_content(monkeypatch, suffix):
    data = ("crates/nbsr-transport/tests/fixture" + suffix.upper() + "\0").encode()
    fake_inventory(monkeypatch, b"crates/nbsr-transport/Cargo.toml\0" + data)
    assert subject()["_tracked_certificate_fixtures"]() == ["tests/fixture" + suffix.upper()]


def test_untracked_build_output_is_not_treated_as_indexed_fixture(monkeypatch, tmp_path):
    (tmp_path / "target").mkdir()
    (tmp_path / "target" / "generated.pem").write_text("dummy", encoding="utf-8")
    ns = subject()
    ns["test_no_certificate_or_private_key_fixture_is_committed"].__globals__["CRATE"] = tmp_path
    fake_inventory(monkeypatch, b"crates/nbsr-transport/Cargo.toml\0crates/nbsr-transport/src/lib.rs\0")
    ns["test_no_certificate_or_private_key_fixture_is_committed"]()


@pytest.mark.parametrize("error", [FileNotFoundError("git"),
                                  subprocess.CalledProcessError(1, ["git"]),
                                  subprocess.TimeoutExpired(["git"], 10)])
def test_git_inventory_failure_propagates(monkeypatch, error):
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(type(error)):
        subject()["_tracked_certificate_fixtures"]()


@pytest.mark.parametrize("data", [b"", b"crates/nbsr-transport/a.pem", b"outside/a.pem\0",
    b"crates/nbsr-transport/Cargo.toml\0\0", b"\xff\0",
    b"/crates/nbsr-transport/a.pem\0", b"crates\\nbsr-transport\\a.pem\0",
    b"crates/nbsr-transport/../outside.pem\0", b"crates/nbsr-transport-other/a.pem\0",
    b"crates/nbsr-transport/\0", b"crates/nbsr-transport/src/lib.rs\0"])
def test_malformed_inventory_fails_closed(monkeypatch, data):
    fake_inventory(monkeypatch, data)
    with pytest.raises(ValueError):
        subject()["_tracked_certificate_fixtures"]()
