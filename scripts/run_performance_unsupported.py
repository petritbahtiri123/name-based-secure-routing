from __future__ import annotations

import argparse
from dataclasses import asdict
import gzip
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.performance.authority import write_loopback_authority  # noqa: E402
from scripts.performance.failure_evidence import (  # noqa: E402
    classify_unsupported_error,
    reconcile_attempt_records,
    terminal_failure_record,
    unsupported_attempts,
)
from scripts.run_performance_validation import (  # noqa: E402
    build_release,
    environment,
    go_lifecycle_samples,
    rust_lifecycle_samples,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", choices=["rust-rust", "go-rust"], required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    env_record = environment()
    if env_record["dirty_tree"]:
        raise SystemExit("unsupported evidence requires a clean working tree")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    attempts = unsupported_attempts(
        run_id=args.run_id,
        implementation=args.path,
        requested_concurrency=640,
        configured_limit=320,
        services=20,
        admission_phase="post-admission",
    )
    records: list[dict[str, object]] = []
    detail = ""
    with tempfile.TemporaryDirectory(prefix="nbsr-unsupported-640-") as temporary:
        temp = Path(temporary)
        authority = temp / "authority"
        write_loopback_authority(authority)
        target = Path(os.environ.get("NBSR_PERF_CARGO_TARGET", r"C:\codex-target\nbsr-perf-completion"))
        binaries = build_release(target)
        try:
            if args.path == "rust-rust":
                observed = rust_lifecycle_samples(
                    binaries, authority, 20, 1_024, "nbsr-warm-new-service", temp,
                    streams_per_service=32, concurrent=True, services_per_session=20,
                )
            else:
                observed = go_lifecycle_samples(
                    binaries, authority, 20, 1_024, "nbsr-warm-new-service", temp,
                    streams_per_service=32, concurrent=True, services_per_session=20,
                )
        except RuntimeError as error:
            detail = str(error)
            error_type, timeout_category = classify_unsupported_error(args.path, detail)
            records = [
                {
                    **terminal_failure_record(
                        attempt,
                        error_type=error_type,
                        timeout_category=timeout_category,
                        detail=detail,
                    ),
                    "record_type": "unsupported-attempt",
                    "supported_benchmark_limit": 320,
                    "protocol_configured_stream_limit": 1_280,
                }
                for attempt in attempts
            ]
        else:
            if len(observed) != len(attempts):
                raise RuntimeError(f"unexpected 640-stream success cardinality: {len(observed)}")
            records = [
                {
                    **asdict(attempt),
                    "schema": "nbsr-performance-unsupported-attempt-v1",
                    "record_type": "unsupported-attempt",
                    "final_result": "success",
                    "error_type": None,
                    "timeout_category": None,
                    "failure_class": None,
                    "supported_benchmark_limit": 320,
                    "protocol_configured_stream_limit": 1_280,
                }
                for attempt in attempts
            ]
    reconcile_attempt_records(attempts, records)
    with gzip.open(output / "raw.ndjson.gz", "wt", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    summary = {
        "schema": "nbsr-performance-unsupported-summary-v1",
        "run_id": args.run_id,
        "implementation": args.path,
        "requested_concurrency": 640,
        "supported_benchmark_limit": 320,
        "protocol_configured_stream_limit": 1_280,
        "attempts": len(attempts),
        "terminal_records": len(records),
        "all_fail_closed": all(record["failure_class"] == "unsupported-limit-fail-closed" for record in records),
        "observed_detail": detail,
    }
    (output / "environment.json").write_text(json.dumps(env_record, indent=2) + "\n", encoding="utf-8")
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
