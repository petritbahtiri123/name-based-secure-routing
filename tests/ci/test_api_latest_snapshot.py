"""No-network/no-API contracts for weekly immutable source preparation."""

import hashlib
import json

import pytest

from scripts.ci import prepare_api_snapshot as m


def controls(tmp_path, monkeypatch):
    root = tmp_path / "trusted"
    hashes = {}
    for name in m.CONTROLS:
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"# approved test control\n")
        hashes[name] = hashlib.sha256(p.read_bytes()).hexdigest()
    monkeypatch.setattr(m, "CONTROLS", hashes)
    return root


def test_uses_fresh_remote_sha_and_records_source_identity(tmp_path, monkeypatch):
    root = controls(tmp_path, monkeypatch)
    calls = []

    def fetch(host, path, limit):
        calls.append((host, path))
        if host == "api.github.com":
            return json.dumps({"ref": m.REF, "object": {"type": "commit", "sha": "a" * 40}}).encode()
        assert "/" + "a" * 40 + "/" in path
        return b"current source\n"

    output = m.prepare(tmp_path / "snapshots", root, fetch=fetch)
    manifest = json.loads((output / "snapshot.json").read_text())
    assert manifest["commit"] == "a" * 40
    assert manifest["openai_api_calls"] == 0
    assert len(calls) == 3
    assert [f["path"] for f in manifest["files"]] == m.PATHS
    assert all(f["sha256"] == hashlib.sha256(b"current source\n").hexdigest() for f in manifest["files"])
    assert "current source" not in (output / "snapshot.json").read_text()
    assert (output / "scripts/ci/run_api_analysis.ps1").is_file()
    with pytest.raises(FileExistsError):
        m.prepare(tmp_path / "snapshots", root, fetch=fetch)


@pytest.mark.parametrize(
    "ref",
    [
        None,
        {"ref": "refs/heads/main", "object": {"type": "commit", "sha": "a" * 40}},
        {"ref": m.REF, "object": {"type": "commit", "sha": "not-sha"}},
        {"ref": m.REF, "object": {"type": "tree", "sha": "a" * 40}},
    ],
)
def test_ref_failure_has_no_local_head_fallback(tmp_path, monkeypatch, ref):
    root = controls(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        m.prepare(tmp_path / "snapshots", root, fetch=lambda *_: json.dumps(ref).encode())
    assert not (tmp_path / "snapshots").exists()


@pytest.mark.parametrize(
    "data", [b"a\0b", b"\xff", b"x" * 98305, b"sk-proj-" + b"a" * 40],
    ids=["nul", "invalid-utf8", "oversized", "credential-like"],
)
def test_bad_source_rejected_before_snapshot_creation(tmp_path, monkeypatch, data):
    root = controls(tmp_path, monkeypatch)

    def fetch(host, *_):
        return json.dumps({"ref": m.REF, "object": {"type": "commit", "sha": "a" * 40}}).encode() if host == "api.github.com" else data

    with pytest.raises(ValueError):
        m.prepare(tmp_path / "snapshots", root, fetch=fetch)
    assert not (tmp_path / "snapshots").exists()


def test_changed_control_refused_before_network(tmp_path, monkeypatch):
    root = controls(tmp_path, monkeypatch)
    (root / "scripts/ci/api_analysis.py").write_bytes(b"changed")
    with pytest.raises(ValueError):
        m.prepare(tmp_path / "snapshots", root, fetch=lambda *_: pytest.fail("network"))


def test_network_failure_never_uses_stale_source(tmp_path, monkeypatch):
    root = controls(tmp_path, monkeypatch)

    def fail(*_):
        raise OSError("unavailable")

    with pytest.raises(OSError):
        m.prepare(tmp_path / "snapshots", root, fetch=fail)
    assert not (tmp_path / "snapshots").exists()


def test_resolve_only_refreshes_remote_without_source_or_local_checkout():
    commits = iter(["a" * 40, "b" * 40])

    def fetch(host, path, limit):
        assert host == "api.github.com"
        return json.dumps({"ref": m.REF, "object": {"type": "commit", "sha": next(commits)}}).encode()

    assert m.resolve_latest(fetch=fetch) == "a" * 40
    assert m.resolve_latest(fetch=fetch) == "b" * 40


def test_second_source_failure_leaves_no_runnable_partial_snapshot(tmp_path, monkeypatch):
    root = controls(tmp_path, monkeypatch)

    def fetch(host, path, limit):
        if host == "api.github.com":
            return json.dumps({"ref": m.REF, "object": {"type": "commit", "sha": "a" * 40}}).encode()
        if path.endswith("docs/CI.md"):
            return b"first source"
        raise OSError("second source unavailable")

    with pytest.raises(OSError):
        m.prepare(tmp_path / "snapshots", root, fetch=fetch)
    assert not (tmp_path / "snapshots").exists()


@pytest.mark.parametrize("status,data", [(302, b""), (403, b""), (200, b"12345")])
def test_transport_rejects_redirect_error_or_oversize_and_closes(monkeypatch, status, data):
    calls = []

    class Response:
        def read(self, limit):
            return data[:limit]

    response = Response()
    response.status = status

    class Connection:
        def __init__(self, host, timeout):
            calls.append(("host", host))

        def request(self, *args, **kwargs):
            calls.append(("request", args, kwargs))

        def getresponse(self):
            return response

        def close(self):
            calls.append(("closed",))

    monkeypatch.setattr(m.http.client, "HTTPSConnection", Connection)
    with pytest.raises(ValueError):
        m.fetch_bytes("api.github.com", "/fixed", 4)
    assert len([x for x in calls if x[0] == "request"]) == 1
    assert calls[-1] == ("closed",)
    assert "Authorization" not in str(calls)


def test_bad_source_parameter_ids_are_bounded():
    """Windows exports each node ID through a bounded environment variable."""
    marker = next(mark for mark in test_bad_source_rejected_before_snapshot_creation.pytestmark if mark.name == "parametrize")
    ids = marker.kwargs.get("ids")
    assert ids is not None and len(ids) == len(marker.args[1])
    assert len(set(ids)) == len(ids)
    assert all(isinstance(value, str) and 0 < len(value) <= 32 for value in ids)
