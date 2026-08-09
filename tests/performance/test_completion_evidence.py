from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.performance.completion_evidence import summarize_completion_root, write_completion_manifest
from scripts.verify_performance_evidence import verify_evidence


PATHS = ("direct-quic", "rust-rust", "go-rust")


def write_records(root: Path) -> None:
    (root / "raw").mkdir(parents=True)
    records: list[dict[str, object]] = []
    for path in PATHS:
        for ordinal in (1, 2, 3):
            records.append({
                "record_type": "capacity-confirmation", "path": path, "offered_rate": 100,
                "run_id": f"{path}-confirm-r{ordinal}", "passed": True,
            })
        for percent in (25, 50, 75, 90):
            records.append({
                "record_type": "formal-load", "path": path, "percent": percent,
                "accepted_capacity": 100, "offered_rate": percent, "passed": True,
            })
        records.append({"record_type": "memory-conclusion", "path": path, "status": "PASS"})
    for implementation in ("rust-rust", "go-rust"):
        for sample_id in range(2):
            records.append({
                "record_type": "unsupported-attempt", "implementation": implementation,
                "run_id": f"{implementation}-640", "sample_id": sample_id,
                "final_result": "failure", "error_type": "typed", "operating_point": "unsupported",
            })
    (root / "raw/completion.ndjson").write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records), encoding="utf-8",
    )


def write_prior(root: Path) -> None:
    root.mkdir()
    (root / "checksums.json").write_text('{"frozen":"digest"}\n', encoding="utf-8")


def test_completion_summary_regenerates_from_raw_records(tmp_path: Path) -> None:
    root = tmp_path / "completion"
    write_records(root)
    summary = summarize_completion_root(root)
    assert summary["raw_records"] == 28
    assert summary["accepted_capacities"] == {path: 100 for path in PATHS}
    assert summary["completion_criteria"] == {
        "capacity_confirmations": True,
        "formal_loads": True,
        "memory_stability": True,
        "unsupported_evidence_integrity": True,
    }
    assert summary["outcome"] == "COMPLETE_LOOPBACK_BASELINE"


def test_failing_confirmation_prevents_complete_classification(tmp_path: Path) -> None:
    root = tmp_path / "completion"
    write_records(root)
    path = root / "raw/completion.ndjson"
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    records[1]["passed"] = False
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    summary = summarize_completion_root(root)
    assert summary["outcome"] == "PARTIAL_BASELINE"
    assert summary["completion_criteria"]["capacity_confirmations"] is False


def test_completion_manifest_binds_prior_and_detects_mutation(tmp_path: Path) -> None:
    prior = tmp_path / "prior"
    root = tmp_path / "completion"
    write_prior(prior)
    write_records(root)
    write_completion_manifest(root, prior)
    files, raw_count = verify_evidence(root)
    assert files >= 3
    assert raw_count == 28

    (prior / "checksums.json").write_text('{"frozen":"mutated"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="prior evidence checksum binding mismatch"):
        verify_evidence(root)


def test_completion_manifest_checksums_retained_time_series(tmp_path: Path) -> None:
    prior = tmp_path / "prior"
    root = tmp_path / "completion"
    write_prior(prior)
    write_records(root)
    series = root / "memory/direct/resources.ndjson"
    series.parent.mkdir(parents=True)
    series.write_text('{"working_set_bytes":1}\n', encoding="utf-8")

    write_completion_manifest(root, prior)

    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert "memory/direct/resources.ndjson" in manifest["files"]
    verify_evidence(root)
