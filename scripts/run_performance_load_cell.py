from __future__ import annotations

import argparse
from dataclasses import asdict
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.performance.authority import write_loopback_authority  # noqa: E402
from scripts.performance.driver import FormalRunRequirements  # noqa: E402
from scripts.performance.resources import RequestActivityBuckets, ResourceSeries  # noqa: E402
from scripts.performance.statistics import summarize  # noqa: E402
from scripts.run_performance_validation import (
    build_release,
    direct_samples,
    environment,
    nbsr_samples,
    normalize,
)  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]


def expected_steady_sample_count(
    offered_rate: float, *, warmup_seconds: int, steady_seconds: int
) -> int:
    total = round(offered_rate * (warmup_seconds + steady_seconds))
    warmup = round(offered_rate * warmup_seconds)
    return total - warmup


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", choices=["direct-quic", "rust-rust", "go-rust"], required=True)
    parser.add_argument("--offered-rate", type=float, required=True)
    parser.add_argument("--warmup-seconds", type=int, default=60)
    parser.add_argument("--steady-seconds", type=int, default=600)
    parser.add_argument("--idle-p99-ns", type=int, required=True)
    parser.add_argument("--payload-bytes", type=int, default=1024)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--formal", action="store_true")
    parser.add_argument("--memory", action="store_true")
    parser.add_argument("--sampling-cadence-seconds", type=int, default=1)
    args = parser.parse_args()
    if args.formal:
        FormalRunRequirements().validate_capacity_window(
            warmup_seconds=args.warmup_seconds,
            steady_state_seconds=args.steady_seconds,
        )
    if args.memory and (args.warmup_seconds < 60 or args.steady_seconds < 1_800):
        raise SystemExit("primary memory evidence requires 60 seconds warm-up and 1800 seconds steady state")
    if args.sampling_cadence_seconds != 1:
        raise SystemExit("completion memory sampling cadence is frozen at 1 second")
    if args.offered_rate <= 0:
        raise SystemExit("offered rate must be positive")
    env_record = environment()
    if env_record["dirty_tree"]:
        raise SystemExit("formal benchmark requires a clean working tree")
    encoded_environment = json.dumps(env_record, sort_keys=True, separators=(",", ":")).encode()
    environment_digest = hashlib.sha256(encoded_environment).hexdigest()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "environment.json").write_text(json.dumps(env_record, indent=2) + "\n", encoding="utf-8")
    total_seconds = args.warmup_seconds + args.steady_seconds
    sample_count = round(args.offered_rate * total_seconds)
    if sample_count > 10_000_000:
        raise SystemExit("cell exceeds the 10,000,000-sample harness safety limit")
    resources: list[dict[str, Any]] = []
    activity = RequestActivityBuckets(
        offered_rate=args.offered_rate,
        sample_count=sample_count,
        cadence_ns=args.sampling_cadence_seconds * 1_000_000_000,
    )
    with tempfile.TemporaryDirectory(prefix="nbsr-load-cell-") as temporary:
        temp = Path(temporary)
        authority = temp / "authority"
        write_loopback_authority(authority)
        target = Path(os.environ.get("NBSR_PERF_CARGO_TARGET", r"C:\codex-target\nbsr-perf-formal"))
        binaries = build_release(target)
        streamed = temp / "source.ndjson"
        if args.path == "direct-quic":
            direct_samples(
                binaries["direct"], authority, sample_count, args.payload_bytes, "warm", temp,
                args.offered_rate, resources, streamed,
            )
            scenario = "direct-warm"
        else:
            go_runtime_series = temp / "go-runtime-series.ndjson" if args.memory and args.path == "go-rust" else None
            nbsr_samples(
                args.path, binaries, authority, sample_count, args.payload_bytes, temp,
                args.offered_rate, resources, streamed, go_runtime_series,
            )
            scenario = "nbsr-warm-existing-service"
        warmup_ns = args.warmup_seconds * 1_000_000_000
        total_ns = total_seconds * 1_000_000_000
        steady_latencies: list[int] = []
        success = failure = observed = 0
        timeout_requests = rejected_requests = peak_backlog = 0
        steady_start_lateness: list[int] = []
        completion_metadata: dict[str, Any] | None = None
        raw_path = output / "raw.ndjson.gz"
        with streamed.open("r", encoding="utf-8") as source, gzip.open(raw_path, "wt", encoding="utf-8", newline="\n") as raw:
            for line in source:
                document = json.loads(line)
                if "sample_id" not in document:
                    if document.get("status") != "PASS":
                        raise RuntimeError("invalid streamed completion metadata")
                    completion_metadata = document
                    continue
                record = normalize(
                    document,
                    sample_id=observed,
                    path=args.path,
                    scenario=scenario,
                    payload=args.payload_bytes,
                    environment_digest=environment_digest,
                    repository_sha=env_record["repository_sha"],
                    run_id=args.run_id,
                    load_level="capacity" if args.formal else "exploratory-capacity",
                    offered_load=args.offered_rate,
                    achieved_load=None,
                )
                scheduled = int(document["scheduled_ns"])
                record["window"] = "warmup" if scheduled < warmup_ns else "steady"
                raw.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
                observed += 1
                started = int(document["started_ns"])
                activity.record(
                    started_ns=started,
                    completed_ns=started + int(record["request_latency_ns"]),
                )
                scheduled_arrivals = min(sample_count, int(started * args.offered_rate // 1_000_000_000) + 1)
                peak_backlog = max(peak_backlog, scheduled_arrivals - (observed - 1))
                if warmup_ns <= scheduled < total_ns:
                    steady_start_lateness.append(int(document["start_lateness_ns"]))
                    if record["success"]:
                        success += 1
                        steady_latencies.append(int(record["request_latency_ns"]))
                    else:
                        failure += 1
                        error_type = str(record.get("error_type") or "").lower()
                        timeout_requests += "timeout" in error_type
                        rejected_requests += "reject" in error_type
        if observed != sample_count:
            raise RuntimeError(f"open-loop sample loss: offered {sample_count}, observed {observed}")
        activity.finish()
        if args.memory and args.path == "go-rust":
            if go_runtime_series is None or not go_runtime_series.is_file():
                raise RuntimeError("Go memory run omitted runtime time series")
            shutil.copyfile(go_runtime_series, output / "go-runtime-series.ndjson")
    if args.path == "go-rust":
        if completion_metadata is None or "go_runtime" not in completion_metadata:
            raise RuntimeError("Go load stream omitted runtime evidence")
        (output / "go-runtime.json").write_text(
            json.dumps(completion_metadata["go_runtime"], indent=2) + "\n", encoding="utf-8",
        )
    expected_steady = expected_steady_sample_count(
        args.offered_rate,
        warmup_seconds=args.warmup_seconds,
        steady_seconds=args.steady_seconds,
    )
    if success + failure != expected_steady:
        raise RuntimeError(f"steady sample mismatch: expected {expected_steady}, observed {success + failure}")
    for record in resources:
        request_activity = activity.at(int(record["timestamp_ns"]))
        record.update(asdict(request_activity))
        record["phase"] = "warmup" if int(record["timestamp_ns"]) < warmup_ns else "steady"
    resource_path = output / "resources.ndjson"
    resource_path.write_text(
        "".join(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n" for record in resources),
        encoding="utf-8",
    )
    destination = [
        record for record in resources
        if record["role"] == "destination" and record["timestamp_ns"] >= warmup_ns
    ]
    if len(destination) < 2:
        raise RuntimeError("insufficient destination steady-state resource samples")
    memory = ResourceSeries(expected_samples=len(destination))
    for record in destination:
        memory.record(timestamp_ns=record["timestamp_ns"], working_set_bytes=record["working_set_bytes"])
    trend = memory.finish()
    def segment_trend(segment: list[dict[str, Any]]) -> dict[str, Any]:
        series = ResourceSeries(expected_samples=len(segment))
        for record in segment:
            series.record(timestamp_ns=record["timestamp_ns"], working_set_bytes=record["working_set_bytes"])
        return asdict(series.finish())

    second_half = segment_trend(destination[len(destination) // 2 :])
    final_quarter = segment_trend(destination[3 * len(destination) // 4 :])
    latency = summarize(steady_latencies)
    success_rate = success / expected_steady
    sorted_lateness = sorted(steady_start_lateness)
    p95_lateness = sorted_lateness[max(0, (95 * len(sorted_lateness) + 99) // 100 - 1)]
    summary = {
        "schema": "nbsr-performance-load-cell-v1",
        "run_id": args.run_id,
        "formal": args.formal,
        "memory_primary": args.memory,
        "sampling_cadence_seconds": args.sampling_cadence_seconds,
        "path": args.path,
        "scenario": scenario,
        "payload_bytes": args.payload_bytes,
        "timer_resolution_ms": 1,
        "warmup_seconds": args.warmup_seconds,
        "steady_state_seconds": args.steady_seconds,
        "offered_rate": args.offered_rate,
        "achieved_rate": success / args.steady_seconds,
        "offered_requests": expected_steady,
        "successful_requests": success,
        "failed_requests": failure,
        "completed_requests": success + failure,
        "timeout_requests": timeout_requests,
        "rejected_requests": rejected_requests,
        "late_requests": sum(value > 0 for value in steady_start_lateness),
        "max_start_lateness_ns": max(steady_start_lateness, default=0),
        "p95_start_lateness_ns": p95_lateness,
        "peak_backlog": peak_backlog,
        "success_rate": success_rate,
        "latency_ns": latency,
        "idle_p99_ns": args.idle_p99_ns,
        "p99_within_2x_idle": int(latency["p99"]) <= 2 * args.idle_p99_ns,
        "destination_cpu_percent_assigned_mean": sum(record["cpu_percent_assigned"] for record in destination) / len(destination),
        "destination_cpu_percent_assigned_max": max(record["cpu_percent_assigned"] for record in destination),
        "destination_working_set_bytes_start": destination[0]["working_set_bytes"],
        "destination_working_set_bytes_end": destination[-1]["working_set_bytes"],
        "destination_private_bytes_end": destination[-1]["private_bytes"],
        "destination_peak_working_set_bytes": max(record["peak_working_set_bytes"] for record in destination),
        "destination_thread_count_max": max(record["thread_count"] for record in destination),
        "destination_memory_slope_bytes_per_second": trend.slope_bytes_per_second,
        "destination_memory_trend": asdict(trend),
        "destination_memory_second_half_trend": second_half,
        "destination_memory_final_quarter_trend": final_quarter,
        "unexpected_protocol_rejections": 0,
        "resource_limit_errors": 0,
        "go_runtime": completion_metadata.get("go_runtime") if completion_metadata is not None else None,
        "sustainable_without_memory_decision": success_rate >= 0.999
        and int(latency["p99"]) <= 2 * args.idle_p99_ns
        and max(record["cpu_percent_assigned"] for record in destination) <= 85.0,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
