from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.performance.evidence import EvidenceOverflow, EvidenceWriter


def test_failed_requests_are_retained_as_raw_samples(tmp_path: Path) -> None:
    path = tmp_path / "raw.ndjson"
    with EvidenceWriter(path, capacity=4) as writer:
        writer.submit({"sample_id": 0, "success": True})
        writer.submit({"sample_id": 1, "success": False, "error_type": "timeout"})
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert records == [
        {"sample_id": 0, "success": True},
        {"error_type": "timeout", "sample_id": 1, "success": False},
    ]


def test_bounded_writer_fails_explicitly_on_overflow(tmp_path: Path) -> None:
    writer = EvidenceWriter(tmp_path / "raw.ndjson", capacity=1, start_worker=False)
    writer.submit({"sample_id": 0})
    with pytest.raises(EvidenceOverflow, match="capacity 1"):
        writer.submit({"sample_id": 1})
    writer.abort()


def test_writer_rejects_duplicate_sample_ids(tmp_path: Path) -> None:
    path = tmp_path / "raw.ndjson"
    with pytest.raises(ValueError, match="duplicate sample_id"):
        with EvidenceWriter(path, capacity=4) as writer:
            writer.submit({"sample_id": 7})
            writer.submit({"sample_id": 7})
