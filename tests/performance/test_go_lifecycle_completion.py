"""Go lifecycle completion is explicit and cannot enter the fanout path."""

import json
from pathlib import Path
import pytest
from scripts.run_b3_session_lifecycle import completion_environment, client_command


@pytest.mark.parametrize(
    "path,spec",
    [
        ("rust-rust", {"sessions": 1, "destination_completion": True}),
        ("go-rust", {"sessions": 2, "destination_completion": True}),
        ("go-rust", {"sessions": 1, "destination_completion": 1}),
    ],
)
def test_completion_rejects_other_modes(path, spec):
    with pytest.raises(ValueError):
        completion_environment(path, spec)


def test_completion_default_and_explicit_mode(monkeypatch):
    assert completion_environment("go-rust", {"sessions": 1}) == {}
    assert completion_environment("go-rust", {"sessions": 1, "destination_completion": True}) == {
        "NBSR_PERF_LIFECYCLE_COMPLETION_MARKERS": "1"
    }
    monkeypatch.setenv("NBSR_PERF_LIFECYCLE_COMPLETION_MARKERS", "1")
    with pytest.raises(ValueError):
        completion_environment("go-rust", {"sessions": 1})


@pytest.mark.parametrize("enabled", [False, True])
def test_go_configuration_records_completion(tmp_path, enabled):
    _, _ = client_command(
        "go-rust",
        {"go": Path("go.exe")},
        tmp_path / "ready",
        tmp_path / "authority",
        tmp_path,
        connections=50,
        services=2,
        streams=4,
        offset=0,
        runtime_path=tmp_path / "runtime",
        destination_completion=enabled,
    )
    config = json.loads((tmp_path / "go-0.json").read_text())
    assert config.get("lifecycle_wait_destination_complete", False) is enabled
    assert config["lifecycle_connections"] == 50 and config["lifecycle_streams_per_service"] == 4


def test_collected_completion_requires_every_exact_marker(tmp_path):
    from scripts.run_b3_session_lifecycle import completed_destination_markers

    (tmp_path / "destination-0.complete").write_bytes(b"complete\n")
    with pytest.raises(FileNotFoundError):
        completed_destination_markers(tmp_path, 2)
    (tmp_path / "destination-1.complete").write_bytes(b"wrong\n")
    with pytest.raises(ValueError):
        completed_destination_markers(tmp_path, 2)
    (tmp_path / "destination-1.complete").write_bytes(b"complete\n")
    assert completed_destination_markers(tmp_path, 2) == [0, 1]
