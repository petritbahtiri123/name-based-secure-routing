from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Iterator


def records(path: Path) -> Iterator[dict[str, Any]]:
    opener = gzip.open if path.suffix == ".gz" else Path.open
    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            yield json.loads(line)


def verify_evidence(root: Path) -> tuple[int, int]:
    root = root.resolve()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    checksums = json.loads((root / "checksums.json").read_text(encoding="utf-8"))
    version_two = manifest["schema"] == "nbsr-performance-evidence-manifest-v2"
    external_index = manifest["schema"] == "nbsr-performance-external-index-manifest-v1"
    completion = manifest["schema"] == "nbsr-performance-completion-v1"
    memory_closure = manifest["schema"] == "nbsr-performance-memory-closure-v1"
    excluded = {"checksums.json"} if version_two or external_index or completion or memory_closure else {"checksums.json", "manifest.json"}
    nested_roots = {path.parent.resolve() for path in root.glob("*/manifest.json") if path.parent.resolve() != root}
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and path.relative_to(root).as_posix() not in excluded
        and (version_two or external_index or not any(parent in path.resolve().parents for parent in nested_roots))
    }
    if actual != set(checksums):
        raise ValueError(f"evidence inventory mismatch missing={set(checksums) - actual} extra={actual - set(checksums)}")
    for name, expected in checksums.items():
        observed = hashlib.sha256((root / name).read_bytes()).hexdigest()
        if observed != expected:
            raise ValueError(f"evidence digest mismatch: {name}")
    if not external_index and manifest["files"] != sorted(checksums):
        raise ValueError("manifest inventory differs from checksums")
    if external_index:
        if manifest["outcome"] != "PARTIAL_BASELINE":
            raise ValueError("external index may not claim complete evidence")
        raw_count = sum(1 for path in root.rglob("raw.ndjson.gz") for _ in records(path))
        return len(checksums), raw_count
    if memory_closure:
        try:
            from scripts.performance.memory_closure import verify_source_bindings
        except ModuleNotFoundError:
            from performance.memory_closure import verify_source_bindings

        analysis = json.loads((root / manifest["analysis"]).read_text(encoding="utf-8"))
        if manifest["outcome"] != analysis["classification"]["baseline"]:
            raise ValueError("memory closure classification mismatch")
        if manifest["classifications"] != {key: analysis["classification"][key] for key in ("direct-quic", "rust-rust", "go-rust")}:
            raise ValueError("memory path classification mismatch")
        verify_source_bindings(Path.cwd(), root / manifest["source_bindings"])
        return len(checksums), 0
    if completion:
        try:
            from scripts.performance.completion_evidence import summarize_completion_root
        except ModuleNotFoundError:
            from performance.completion_evidence import summarize_completion_root

        prior = (root.parent / manifest["prior_evidence"]["relative_root"]).resolve()
        observed_prior = hashlib.sha256((prior / "checksums.json").read_bytes()).hexdigest()
        if observed_prior != manifest["prior_evidence"]["checksums_sha256"]:
            raise ValueError("prior evidence checksum binding mismatch")
        regenerated = summarize_completion_root(root)
        stored = json.loads((root / manifest["analysis"]).read_text(encoding="utf-8"))
        if regenerated != stored:
            raise ValueError("completion analysis does not regenerate from raw evidence")
        if manifest["outcome"] != regenerated["outcome"] or manifest["completion_criteria"] != regenerated["completion_criteria"]:
            raise ValueError("completion manifest classification mismatch")
        raw_count = regenerated["raw_records"]
        return len(checksums), raw_count
    if not version_two:
        raw_count = sum(1 for path in (root / "raw").glob("*.ndjson*") for _ in records(path))
        return len(checksums), raw_count

    run_ids: set[str] = set()
    raw_count = 0
    for run in manifest.get("runs", []):
        run_id = run["run_id"]
        if run_id in run_ids:
            raise ValueError(f"duplicate run ID {run_id}")
        run_ids.add(run_id)
        raw_path = root / run["raw"]
        summary = json.loads((root / run["summary"]).read_text(encoding="utf-8"))
        if summary["run_id"] != run_id:
            raise ValueError(f"summary run ID mismatch for {run_id}")
        observed_ids: set[int] = set()
        success = failure = 0
        for record in records(raw_path):
            raw_count += 1
            if record.get("schema") != "nbsr-performance-sample-v1" or record.get("run_id") != run_id:
                raise ValueError(f"raw scenario binding mismatch for {run_id}")
            if record.get("environment_digest") != run["environment_digest"]:
                raise ValueError(f"raw environment binding mismatch for {run_id}")
            sample_id = record.get("sample_id")
            if not isinstance(sample_id, int) or sample_id in observed_ids:
                raise ValueError(f"invalid or duplicate sample ID for {run_id}")
            observed_ids.add(sample_id)
            for field in ("request_latency_ns", "total_scenario_ns", "start_lateness_ns"):
                if record.get(field) is not None and record[field] < 0:
                    raise ValueError(f"negative duration {field} for {run_id}")
            if record.get("success"):
                success += 1
            else:
                failure += 1
                if not record.get("error_type"):
                    raise ValueError(f"untyped failure for {run_id}")
        if len(observed_ids) != run["raw_samples"]:
            raise ValueError(f"raw sample count mismatch for {run_id}")
        if success != summary["success"] or failure != summary["failure"]:
            raise ValueError(f"summary success/failure mismatch for {run_id}")
        if run.get("formal"):
            scenario = run["scenario"]
            required = 2_000 if scenario.endswith("cold") else 100_000
            if run.get("kind") == "load":
                if summary["warmup_seconds"] < 60 or summary["steady_state_seconds"] < 600:
                    raise ValueError(f"short formal load window for {run_id}")
                if summary["offered_requests"] != summary["successful_requests"] + summary["failed_requests"]:
                    raise ValueError(f"load count inconsistency for {run_id}")
            elif success < required:
                raise ValueError(f"insufficient formal samples for {run_id}")
    confidence = json.loads((root / manifest["confidence_summary"]).read_text(encoding="utf-8"))
    for cell, intervals in confidence["cells"].items():
        for percentile, interval in intervals.items():
            if interval["method"] != "independent-run-bootstrap-mean-v1" or interval["run_count"] < 5:
                raise ValueError(f"invalid bootstrap confidence interval {cell}/{percentile}")
            if not interval["lower"] <= interval["estimate"] <= interval["upper"]:
                raise ValueError(f"inverted confidence interval {cell}/{percentile}")
    if manifest["outcome"] == "COMPLETE_LOOPBACK_BASELINE" and not all(manifest["completion_criteria"].values()):
        raise ValueError("complete outcome has unsatisfied completion criteria")
    return len(checksums), raw_count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    root = parser.parse_args().evidence
    try:
        files, raw_count = verify_evidence(root)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(str(error)) from error
    print(f"NBSR performance evidence: PASS ({files} files, {raw_count} raw samples)")


if __name__ == "__main__":
    main()
