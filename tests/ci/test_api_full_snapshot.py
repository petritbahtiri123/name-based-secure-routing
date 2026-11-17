"""Full-scope preparation is offline apart from resolving the approved ref."""

import hashlib
import json

import pytest

from scripts.ci import prepare_api_full_snapshot as m


def blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def test_full_snapshot_pins_inventory_and_never_reads_archive_content(tmp_path):
    data = b"code\n"
    sha = blob(data)
    entries = [
        {"path": "nbsr/a.py", "mode": "100644", "sha": sha, "size": len(data)},
        {"path": "evidence/raw.json", "mode": "100644", "sha": "b" * 40, "size": 20},
    ]
    calls = []

    def inventory(repo, commit):
        calls.append((repo, commit))
        return entries, {sha: data}

    out = m.prepare(tmp_path / "out", tmp_path / "repo", resolve=lambda: "a" * 40, inventory=inventory)
    report = json.loads((out / "snapshot.json").read_text())
    assert calls == [(tmp_path / "repo", "a" * 40)]
    assert report["commit"] == "a" * 40 and report["preparation_complete"]
    assert report["openai_api_calls"] == 0 and not report["live_execution_authorized"]
    assert (out / "sources" / sha).read_bytes() == data
    assert not (out / "sources" / ("b" * 40)).exists()
    assert report["files"][1]["status"] == "planned"  # sorted evidence first
    with pytest.raises(FileExistsError):
        m.prepare(tmp_path / "out", tmp_path / "repo", resolve=lambda: "a" * 40, inventory=inventory)


def test_missing_source_is_reported_incomplete_without_old_checkout_fallback(tmp_path):
    e = {"path": "a.py", "mode": "100644", "sha": "b" * 40, "size": 10}
    out = m.prepare(tmp_path / "out", tmp_path / "repo", resolve=lambda: "a" * 40, inventory=lambda *_: ([e], {}))
    r = json.loads((out / "snapshot.json").read_text())
    assert not r["preparation_complete"]
    assert r["files"][0]["status"] == "unavailable"
    assert list((out / "sources").iterdir()) == []


def test_sensitive_file_is_not_written_to_source_cache(tmp_path):
    data = b"sk-proj-" + b"a" * 40
    e = {"path": "config.json", "mode": "100644", "sha": blob(data), "size": len(data)}
    out = m.prepare(tmp_path / "out", tmp_path / "repo", resolve=lambda: "a" * 40, inventory=lambda *_: ([e], {blob(data): data}))
    r = json.loads((out / "snapshot.json").read_text())
    assert r["files"][0]["reason"] == "possible-credential"
    assert list((out / "sources").iterdir()) == []


def test_wrong_blob_never_creates_output(tmp_path):
    e = {"path": "a.py", "mode": "100644", "sha": "b" * 40, "size": 1}
    with pytest.raises(ValueError):
        m.prepare(tmp_path / "out", tmp_path / "repo", resolve=lambda: "a" * 40, inventory=lambda *_: ([e], {"b" * 40: b"x"}))
    assert not (tmp_path / "out").exists()


def test_git_reader_uses_exact_commit_and_bounds_sources(tmp_path, monkeypatch):
    data = b"x\n"
    sha = blob(data)
    seen = []

    def git(repo, *args, data=None):
        seen.append(args)
        if args[:2] == ("remote", "get-url"):
            return f"https://github.com/{m.REPO}.git\n".encode()
        if args[0] == "ls-tree":
            assert args[-1] == "a" * 40
            return f"100644 blob {sha}\ta.py\0".encode()
        if args[1] == "--batch-check":
            return f"{sha} blob 2\n".encode()
        return f"{sha} blob 2\n".encode() + b"x\n\n"

    monkeypatch.setattr(m, "git_bytes", git)
    entries, blobs = m.read_inventory(tmp_path, "a" * 40)
    assert blobs[sha] == data and entries[0]["size"] == 2
    assert not any("HEAD" in arg for args in seen for arg in args)


def test_git_reader_rejects_oversized_blob_before_content_read(tmp_path, monkeypatch):
    sha = "b" * 40

    def git(repo, *args, data=None):
        if args[0] == "remote":
            return f"https://github.com/{m.REPO}.git".encode()
        if args[0] == "ls-tree":
            return f"100644 blob {sha}\ta.py\0".encode()
        assert args[1] == "--batch-check"
        return f"{sha} blob {m.MAX_FILE + 1}\n".encode()

    monkeypatch.setattr(m, "git_bytes", git)
    with pytest.raises(ValueError):
        m.read_inventory(tmp_path, "a" * 40)


def test_git_child_has_no_api_key_or_implicit_network(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-only")

    def run(argv, **kwargs):
        assert kwargs["env"]["GIT_NO_LAZY_FETCH"] == "1"
        assert kwargs["env"]["GIT_TERMINAL_PROMPT"] == "0"
        assert "OPENAI_API_KEY" not in kwargs["env"]
        assert kwargs["timeout"] == 30
        return type("Result", (), {"returncode": 0, "stdout": b"ok"})()

    monkeypatch.setattr(m.subprocess, "run", run)
    assert m.git_bytes(tmp_path, "ls-tree", "a" * 40) == b"ok"
