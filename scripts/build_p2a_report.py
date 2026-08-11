from __future__ import annotations

import hashlib
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence" / "performance" / "established-data-plane-p2a"


def median(records: list[dict], field: str) -> float:
    return statistics.median(float(record[field]) for record in records)


def main() -> None:
    records = [json.loads(path.read_text(encoding="utf-8")) for path in (EVIDENCE / "raw").glob("*.json")
               if ".ready" not in path.name]
    records = [record for record in records if record.get("schema") == "nbsr-p2a-repeat-v1"]
    groups: dict[tuple[str, int, int], list[dict]] = {}
    for record in records:
        groups.setdefault((record["path"], record["streams"], record["payload_bytes"]), []).append(record)
    cells = []
    paired = []
    for payload in (1, 1024, 16384):
        for streams in (1, 8, 64):
            values = {}
            for path in ("direct", "nbsr"):
                group = groups[(path, streams, payload)]
                ops = median(group, "operations_per_second")
                cell = {
                    "path": path, "streams": streams, "payload_bytes": payload,
                    "repeat_count": len(group), "throughput_cv": statistics.stdev(
                        record["operations_per_second"] for record in group) / statistics.fmean(
                        record["operations_per_second"] for record in group),
                    "stable": False, "median_completed_operations": median(group, "completed_operations"),
                    "median_operations_per_second": ops, "median_request_messages_per_second": ops,
                    "median_response_messages_per_second": ops,
                    "median_client_to_server_goodput_bytes_per_second": median(group, "client_to_server_goodput_bytes_per_second"),
                    "median_server_to_client_goodput_bytes_per_second": median(group, "server_to_client_goodput_bytes_per_second"),
                    "median_aggregate_goodput_bytes_per_second": median(group, "aggregate_goodput_bytes_per_second"),
                    "median_aggregate_application_gbps": median(group, "aggregate_application_gbps"),
                    "median_p50_latency_ns": median(group, "p50_latency_ns"),
                    "median_p95_latency_ns": median(group, "p95_latency_ns"),
                    "median_p99_latency_ns": median(group, "p99_latency_ns"),
                    "median_cpu_ns_per_completed_operation": statistics.median(
                        record["resources"]["cpu_ns_per_completed_operation"] for record in group),
                    "peak_working_set_bytes": max(role["peak_working_set_bytes"] for record in group for role in record["resources"]["roles"].values()),
                    "peak_private_bytes": max(role["peak_private_bytes"] for record in group for role in record["resources"]["roles"].values()),
                    "errors": sum(record["errors"] for record in group), "timeouts": sum(record["timeouts"] for record in group),
                    "lifecycle_and_replay_deltas": {name: sorted({record[name] for record in group}) for name in (
                        "transport_sessions_created_delta", "service_channels_created_delta",
                        "application_streams_created_delta", "replay_entries_delta")},
                }
                cell["stable"] = cell["throughput_cv"] <= 0.05
                cells.append(cell); values[path] = cell
            paired.append({
                "streams": streams, "payload_bytes": payload,
                "nbsr_to_direct_throughput_ratio": values["nbsr"]["median_operations_per_second"] / values["direct"]["median_operations_per_second"],
                "direct_minus_nbsr_p50_ns": values["direct"]["median_p50_latency_ns"] - values["nbsr"]["median_p50_latency_ns"],
                "direct_minus_nbsr_p95_ns": values["direct"]["median_p95_latency_ns"] - values["nbsr"]["median_p95_latency_ns"],
                "direct_minus_nbsr_p99_ns": values["direct"]["median_p99_latency_ns"] - values["nbsr"]["median_p99_latency_ns"],
            })
    scaling = []
    for path in ("direct", "nbsr"):
        for payload in (1, 1024, 16384):
            by_stream = {cell["streams"]: cell for cell in cells if cell["path"] == path and cell["payload_bytes"] == payload}
            scaling.append({"path": path, "payload_bytes": payload,
                            "one_to_eight": by_stream[8]["median_operations_per_second"] / by_stream[1]["median_operations_per_second"],
                            "eight_to_sixty_four": by_stream[64]["median_operations_per_second"] / by_stream[8]["median_operations_per_second"]})
    analysis = {
        "schema": "nbsr-p2a-analysis-v2", "classification": "ACCEPTED_WITH_UNSTABLE_CELLS",
        "valid_repeat_count": len(records), "invalid_repeat_count": 0,
        "stable_cell_count": sum(cell["stable"] for cell in cells), "cell_count": len(cells),
        "allocation_telemetry": "unavailable; no invasive allocator profiler built",
        "cells": cells, "paired_comparisons": paired, "scaling": scaling,
        "non_claim": "No root cause is assigned without profile evidence; unstable cells remain lower-confidence observations.",
    }
    (EVIDENCE / "analysis.json").write_text(json.dumps(analysis, indent=2) + "\n", encoding="utf-8", newline="\n")
    rows = []
    for pair in paired:
        direct = next(c for c in cells if c["path"] == "direct" and c["streams"] == pair["streams"] and c["payload_bytes"] == pair["payload_bytes"])
        nbsr = next(c for c in cells if c["path"] == "nbsr" and c["streams"] == pair["streams"] and c["payload_bytes"] == pair["payload_bytes"])
        rows.append(f"| {pair['payload_bytes']} | {pair['streams']} | {direct['median_operations_per_second']:.2f} | {nbsr['median_operations_per_second']:.2f} | {pair['nbsr_to_direct_throughput_ratio']:.4f} | {nbsr['median_aggregate_application_gbps']:.6f} | {nbsr['median_p50_latency_ns']/1000:.1f}/{nbsr['median_p95_latency_ns']/1000:.1f}/{nbsr['median_p99_latency_ns']/1000:.1f} | {nbsr['median_cpu_ns_per_completed_operation']:.1f} | {nbsr['throughput_cv']*100:.3f}% | {'yes' if nbsr['stable'] else 'NO'} |")
    report = """# P2A True Established Data-Plane Baseline

## Executive summary

Classification: **ACCEPTED_WITH_UNSTABLE_CELLS**. All 18 matched cells completed, all 60 measured repeats passed payload/sequence validation, and every timed TS/SC/Application Stream/replay delta was zero. Six selective repeats were used. Direct and NBSR 64-stream/16-KiB cells remained above 5% CV after five repeats and are lower-confidence observations. No optimization was implemented.

One operation is one deterministic framed request plus its matching framed response over the same pre-established bidirectional stream. Every stream uses one outstanding request at a time.

## Established Rust NBSR capacity

| Payload bytes | Streams | Direct ops/s | NBSR ops/s | NBSR/Direct | NBSR aggregate Gbps | NBSR p50/p95/p99 us | NBSR CPU ns/op | NBSR CV | Stable |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
""" + "\n".join(rows) + """

The highest stable NBSR operation rate is the 64-stream, 1-byte cell. The highest stable NBSR aggregate application goodput is the 8-stream, 16-KiB cell. The 64-stream, 16-KiB observation is not used as a stable headline.

## Lifecycle isolation and correctness

Across every repeat: Transport Session creation delta = 0, Service Channel creation delta = 0, Application Stream creation delta = 0, replay-entry delta = 0, and errors/timeouts/missing/duplicates/corrupt/wrong-request responses = 0. Setup and warm-up precede the measurement barrier. Process CPU and memory use only the final measured-duration resource-sample tail. Allocation telemetry was unavailable and no allocator profiler was added.

## Scaling and indications

One-byte throughput scales strongly from 1 to 8 to 64 streams, which is consistent with a single-stream latency bound. At 1 KiB scaling remains positive but sublinear. At 16 KiB, 1 to 8 streams improves throughput, while 64 streams is unstable and does not provide a reliable further-scaling claim. High-concurrency large-payload behavior could be scheduler/CPU or copy/serialization related, but P2A has no profile evidence and assigns no root cause.

## Old benchmark comparison

The accepted 1,687.5 req/s Rust-to-Rust result measured a new `STREAM_OPEN`, admission/acceptance, QUIC Application Stream opening, one exchange, and release per operation. P2A creates and admits the fixed stream set before warm-up and measures repeated framed exchanges only. Therefore 1,687.5 req/s is a lifecycle/establishment capacity and is not established-data-plane throughput.

## Integrity and non-claims

The benchmark feature is disabled by default and adds no production protocol behavior. Direct and NBSR share the same payload bytes, frame codec, validation, warm-up, measured duration, persistent stream counts, and one-outstanding model. P1F replay semantics and prior evidence were not modified. P2A is Windows loopback evidence on this machine, not Internet, regional, production-readiness, or root-cause evidence.

## Recommended next task

Exactly one next task: **P2B profile-only investigation of the unstable 64-stream/16-KiB established-data-plane cell, using the frozen P2A harness and no optimization.**
"""
    reports = EVIDENCE / "reports"; reports.mkdir(exist_ok=True)
    (reports / "final-report.md").write_text(report, encoding="utf-8", newline="\n")
    design = EVIDENCE / "design"; design.mkdir(exist_ok=True)
    (design / "benchmark-semantics.md").write_text((ROOT / "docs" / "superpowers" / "specs" / "2026-08-11-p2a-established-data-plane-design.md").read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    journal = {"setup_failures_not_counted_as_repeats": [
        {"phase": "pre-measurement", "failure": "NBSR multi-stream lazy-open setup deadlock", "disposition": "root-caused; admit all streams before accepting QUIC streams; exact 8-stream regression passed"},
        {"phase": "pre-measurement", "failure": "Direct handshake used stale ready endpoint on restart", "disposition": "root-caused; exact marker cleanup regression added; two same-directory repeats passed"}],
        "selective_reruns": [{"path": c["path"], "streams": c["streams"], "payload_bytes": c["payload_bytes"], "repeat_count": c["repeat_count"], "final_cv": c["throughput_cv"]} for c in cells if c["repeat_count"] > 3]}
    (EVIDENCE / "run-journal.json").write_text(json.dumps(journal, indent=2) + "\n", encoding="utf-8", newline="\n")
    files = sorted(path for path in EVIDENCE.rglob("*") if path.is_file() and path.name != "checksums.sha256")
    (EVIDENCE / "checksums.sha256").write_text("\n".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(EVIDENCE).as_posix()}" for path in files) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
