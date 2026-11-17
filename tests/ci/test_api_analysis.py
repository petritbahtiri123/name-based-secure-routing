"""Offline contracts only: no credentials or API requests."""
import importlib.util
import json
from pathlib import Path

import pytest


def module():
    assert importlib.util.find_spec("scripts.ci.api_analysis") is not None
    from scripts.ci import api_analysis
    return api_analysis


def test_dry_run_manifest_does_not_include_source(tmp_path):
    m = module()
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/CI.md").write_text("hello\nworld\n")
    bundle = m.collect(tmp_path, ["docs/CI.md"])
    report = m.dry_report(bundle)
    assert report["mode"] == "dry-run"
    assert report["files"][0]["lines"] == 2
    assert "hello" not in json.dumps(report)
    assert "1: hello" in bundle["input"]


@pytest.mark.parametrize("path", ["../x", "secrets.txt", ".env", "docs/../README.md", "C:/x"])
def test_unapproved_paths_rejected(tmp_path, path):
    with pytest.raises(ValueError):
        module().collect(tmp_path, [path])


@pytest.mark.parametrize("data", [b"sk-proj-" + b"x" * 45, b"-----BEGIN PRIVATE KEY-----", b"a\x00b", b"a" * 98305], ids=["key", "pem", "binary", "oversize"])
def test_sensitive_binary_or_oversize_content_rejected(tmp_path, data):
    (tmp_path / "README.md").write_bytes(data)
    with pytest.raises(ValueError):
        module().collect(tmp_path, ["README.md"])


def test_budget_and_payload_are_bounded():
    m = module()
    b = {"input": "1: data", "files": []}
    p = m.payload(b, "chosen-model")
    assert p["store"] is False and p["tools"] == []
    assert p["max_output_tokens"] == 2000
    assert m.estimate(p, "1", "2") > 0
    for bad in ("NaN", "Infinity", "-1", "0"):
        with pytest.raises(ValueError):
            m.estimate(p, bad, "2")


def test_incomplete_response_never_becomes_completed_report():
    m = module()
    with pytest.raises(ValueError):
        m.result({"status": "incomplete"})
    r = m.result({"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "hypothesis docs/CI.md:1"}]}], "usage": {"input_tokens": 4, "output_tokens": 5}})
    assert r["unverified_model_analysis"] == "hypothesis docs/CI.md:1"


def test_manual_workflow_is_read_only_and_dry_by_default():
    module()
    p = Path(".github/workflows/api-analysis.yml")
    assert p.exists()
    w = json.loads(p.read_text())
    assert set(w["on"]) == {"workflow_dispatch", "push"}
    assert w["on"]["push"]["branches"] == ["codex/nbsr-v3-wp0-wp1"]
    steps = w["jobs"]["analysis"]["steps"]
    live = next(s for s in steps if s.get("name") == "Explicit bounded API analysis")
    assert live["if"] == "github.event_name == 'workflow_dispatch' && inputs.live"
    dry = next(s for s in steps if s.get("name") == "Dry-run inventory")
    assert dry["if"] == "github.event_name != 'workflow_dispatch' || !inputs.live"
    assert "OPENAI_API_KEY" not in dry["env"]
    assert w["permissions"] == {"contents": "read"}
    assert w["on"]["workflow_dispatch"]["inputs"]["live"]["default"] is False
    assert w["jobs"]["analysis"]["timeout-minutes"] == 5
    from scripts.ci.check import validate_workflow
    validate_workflow(w)


@pytest.mark.parametrize("status,size", [(302, 0), (429, 0), (200, 131073)])
def test_http_rejection_never_retries_or_follows_redirect(monkeypatch, status, size):
    m = module()
    calls = []
    class Connection:
        def __init__(self, host, timeout):
            assert host == "api.openai.com" and timeout == 60
        def request(self, method, path, data, headers):
            calls.append((method, path))
            assert json.loads(data)["store"] is False
        def getresponse(self):
            self.status = status
            return self
        def read(self, maximum):
            assert maximum == 131073
            return b"x" * size
        def close(self):
            calls.append("closed")
    monkeypatch.setattr(m.http.client, "HTTPSConnection", Connection)
    with pytest.raises(ValueError):
        m.send(m.payload({"input": "synthetic"}, "chosen-model"), "synthetic-key")
    assert calls == [("POST", "/v1/responses"), "closed"]


def test_live_budget_rejects_before_http(monkeypatch):
    m = module()
    monkeypatch.setattr(m, "collect", lambda *_: {"input": "x", "files": []})
    monkeypatch.setattr("sys.argv", ["api_analysis", "--live"])
    for key, value in {"NBSR_ANALYSIS_MODEL": "chosen-model", "NBSR_INPUT_RATE": "100", "NBSR_OUTPUT_RATE": "100", "NBSR_MAX_USD": "0.001"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(m, "send", lambda *_: pytest.fail("budget must stop network"))
    assert m.main() == 1


def test_selection_collects_offline_contract_before_push():
    from scripts.ci.check import command_groups
    core = next(c for c in command_groups("python-core") if c.name == "python-core")
    assert "tests/ci" in core.argv


def test_empty_and_duplicate_selection_rejected(tmp_path):
    for paths in ([], ["README.md", "README.md"]):
        with pytest.raises(ValueError):
            module().collect(tmp_path, paths)
