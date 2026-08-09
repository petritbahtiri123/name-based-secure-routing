from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Iterator


PATHS = ("direct-quic", "rust-rust", "go-rust")


def _records(root: Path) -> Iterator[dict[str, Any]]:
    for path in sorted((root / "raw").rglob("*.ndjson*")):
        opener = gzip.open if path.suffix == ".gz" else Path.open
        with opener(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    yield json.loads(line)


def summarize_completion_root(root: Path) -> dict[str, Any]:
    records = list(_records(root))
    accepted: dict[str, float] = {}
    capacity_ok = True
    for path in PATHS:
        path_records = [record for record in records if record.get("record_type") == "capacity-confirmation" and record.get("path") == path]
        rates = sorted({float(record["offered_rate"]) for record in path_records}, reverse=True)
        accepted_rate = next((rate for rate in rates if len([record for record in path_records if float(record["offered_rate"]) == rate]) >= 3 and all(record.get("passed") is True for record in path_records if float(record["offered_rate"]) == rate)), None)
        if accepted_rate is None:
            capacity_ok = False
        else:
            accepted[path] = int(accepted_rate) if accepted_rate.is_integer() else accepted_rate

    formal_ok = capacity_ok
    for path in PATHS:
        formal = [record for record in records if record.get("record_type") == "formal-load" and record.get("path") == path]
        by_percent = {int(record["percent"]): record for record in formal}
        if set(by_percent) != {25, 50, 75, 90} or path not in accepted:
            formal_ok = False
            continue
        for percent, record in by_percent.items():
            expected = float(accepted[path]) * percent / 100
            if record.get("passed") is not True or float(record.get("accepted_capacity", -1)) != float(accepted[path]) or float(record.get("offered_rate", -1)) != expected:
                formal_ok = False

    memory = {record.get("path"): record.get("status") for record in records if record.get("record_type") == "memory-conclusion"}
    memory_ok = set(memory) == set(PATHS) and all(memory[path] in {"PASS", "FAIL"} for path in PATHS)

    unsupported = [record for record in records if record.get("record_type") == "unsupported-attempt"]
    unsupported_ok = True
    for implementation in ("rust-rust", "go-rust"):
        attempts = [record for record in unsupported if record.get("implementation") == implementation]
        identities = {(record.get("run_id"), record.get("sample_id")) for record in attempts}
        if not attempts or len(identities) != len(attempts) or any(not record.get("error_type") or not record.get("final_result") for record in attempts):
            unsupported_ok = False

    criteria = {
        "capacity_confirmations": capacity_ok,
        "formal_loads": formal_ok,
        "memory_stability": memory_ok,
        "unsupported_evidence_integrity": unsupported_ok,
    }
    return {
        "schema": "nbsr-performance-completion-analysis-v1",
        "raw_records": len(records),
        "accepted_capacities": accepted,
        "memory_conclusions": memory,
        "completion_criteria": criteria,
        "outcome": "COMPLETE_LOOPBACK_BASELINE" if all(criteria.values()) else "PARTIAL_BASELINE",
    }


def write_completion_manifest(root: Path, prior_root: Path) -> None:
    root = root.resolve()
    prior_root = prior_root.resolve()
    summary = summarize_completion_root(root)
    summary_path = root / "summaries/analysis.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    prior_checksums = prior_root / "checksums.json"
    files = sorted(
        {"manifest.json"}
        | {
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file() and path.name not in {"manifest.json", "checksums.json"}
        }
    )
    manifest = {
        "schema": "nbsr-performance-completion-v1",
        "outcome": summary["outcome"],
        "completion_criteria": summary["completion_criteria"],
        "files": files,
        "analysis": "summaries/analysis.json",
        "prior_evidence": {
            "relative_root": prior_root.relative_to(root.parent).as_posix(),
            "checksums_sha256": hashlib.sha256(prior_checksums.read_bytes()).hexdigest(),
        },
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    checksums = {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in files
    }
    (root / "checksums.json").write_text(json.dumps(checksums, indent=2, sort_keys=True) + "\n", encoding="utf-8")
