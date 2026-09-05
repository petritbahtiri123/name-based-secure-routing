from pathlib import Path

import pytest

from scripts import run_b4b_task4l as profile


def test_matched_diagnostic_keeps_task4k_workload(monkeypatch, tmp_path):
    calls = []

    def measured(*args, **kwargs):
        calls.append((args, kwargs))
        return {"valid": True, "cleanup": {"all_zero": True}}

    monkeypatch.setattr(profile.v2, "run_measured_cell", measured)
    profile.run_one(tmp_path, {}, 250, 2, "none")
    args, kwargs = calls[0]
    assert args[:3] == (512, 1, 2)
    assert kwargs["source_shards"] == 2
    assert kwargs["release_rate"] == 250
    assert kwargs["duration"] == 30
    assert kwargs["warmup"] == 2
    assert kwargs["timeline"] is False
    assert kwargs["packet_capture"] is None


def test_refuses_existing_evidence_before_build(monkeypatch, tmp_path):
    monkeypatch.setattr(profile.v2, "build", lambda *_: pytest.fail("must not build"))
    with pytest.raises(FileExistsError):
        profile.execute(tmp_path, Path("target"), "paired")


def test_rejects_unknown_observer_before_workload(tmp_path):
    with pytest.raises(ValueError, match="observer"):
        profile.run_one(tmp_path, {}, 200, 1, "unknown")


def test_exception_is_preserved_as_failed_repeat(monkeypatch, tmp_path):
    import json

    def measured(*args, **kwargs):
        raise RuntimeError("capture failed")

    monkeypatch.setattr(profile.v2, "run_measured_cell", measured)
    result = profile.run_one(tmp_path, {}, 200, 1, "none")
    assert result["valid"] is False
    stored = json.loads((tmp_path / "raw/none/rate-200/r1.json").read_text())
    assert stored["failure"] == "RuntimeError: capture failed"
    assert stored["offered_admission_rate"] == 200
    assert stored["repeat"] == 1


def test_etw_gate_rejects_unmatched_binaries(tmp_path):
    import json

    for mode in ("none", "etw"):
        directory = tmp_path / mode
        directory.mkdir()
        (directory / "environment.json").write_text(json.dumps({"binary_sha256": {"source": mode}}))
    with pytest.raises(ValueError, match="binary"):
        profile.compare_etw(tmp_path)
