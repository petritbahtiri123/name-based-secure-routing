from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import pytest

from scripts.verify_performance_evidence import verify_evidence


def write_v2_fixture(root: Path) -> None:
    (root / "raw").mkdir(parents=True)
    (root / "summaries").mkdir()
    run_id = "direct-run-r1"
    environment_digest = "e" * 64
    record = {
        "schema": "nbsr-performance-sample-v1", "run_id": run_id, "sample_id": 0,
        "environment_digest": environment_digest, "success": True,
        "request_latency_ns": 1, "total_scenario_ns": 2,
    }
    with gzip.open(root / "raw/run.ndjson.gz", "wt", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    (root / "summaries/run.json").write_text(
        json.dumps({"run_id": run_id, "success": 1, "failure": 0}) + "\n", encoding="utf-8",
    )
    (root / "summaries/confidence.json").write_text(
        json.dumps({"cells": {"direct": {"p50": {"method": "independent-run-bootstrap-mean-v1", "run_count": 5, "lower": 1, "estimate": 1, "upper": 1}}}}) + "\n",
        encoding="utf-8",
    )
    files = ["manifest.json", "raw/run.ndjson.gz", "summaries/confidence.json", "summaries/run.json"]
    manifest = {
        "schema": "nbsr-performance-evidence-manifest-v2", "files": files,
        "outcome": "PARTIAL_BASELINE", "completion_criteria": {"formal_cells": False},
        "confidence_summary": "summaries/confidence.json",
        "runs": [{
            "run_id": run_id, "raw": "raw/run.ndjson.gz", "summary": "summaries/run.json",
            "environment_digest": environment_digest, "raw_samples": 1, "formal": False,
            "scenario": "direct-warm", "kind": "headline",
        }],
    }
    (root / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    checksums = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in files}
    (root / "checksums.json").write_text(json.dumps(checksums) + "\n", encoding="utf-8")


def test_v2_verifier_reconciles_raw_summary_and_bootstrap_evidence(tmp_path: Path) -> None:
    write_v2_fixture(tmp_path)
    assert verify_evidence(tmp_path) == (4, 1)


def test_v2_verifier_detects_raw_evidence_mutation(tmp_path: Path) -> None:
    write_v2_fixture(tmp_path)
    with (tmp_path / "raw/run.ndjson.gz").open("ab") as handle:
        handle.write(b"mutation")
    with pytest.raises(ValueError, match="evidence digest mismatch"):
        verify_evidence(tmp_path)
