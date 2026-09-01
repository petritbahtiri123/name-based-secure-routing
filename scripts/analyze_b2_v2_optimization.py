from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import statistics


def summarize_cell(records: list[dict]) -> dict:
    if not records:
        raise ValueError("cell requires at least one record")
    first = records[0]
    outstanding = int(first.get("outstanding_per_stream", 1))
    configured = int(first.get("configured_total_outstanding", int(first["streams"]) * outstanding))

    def median(path):
        return statistics.median(path(record) for record in records)

    goodputs = [float(record["aggregate_application_gbps"]) for record in records]
    mean = statistics.fmean(goodputs)
    cv = statistics.stdev(goodputs) / mean if len(goodputs) > 1 and mean else 0.0
    conserved = all(
        int(record.get("configured_total_outstanding", int(record["streams"]) * outstanding))
        == int(record["streams"]) * int(record.get("outstanding_per_stream", 1))
        and int(record.get("max_outstanding_per_stream_observed", outstanding)) <= outstanding
        for record in records
    )
    valid = conserved and all(
        bool(record.get("valid"))
        and int(record.get("errors", -1)) == 0
        and int(record.get("timeouts", -1)) == 0
        for record in records
    )
    roles = {}
    for role in ("source", "destination"):
        roles[f"median_{role}_effective_cores"] = median(
            lambda record: float(record["resources"]["roles"][role]["cpu_ns"])
            / float(record["measured_ns"])
        )
    return {
        "path": first["path"],
        "payload_bytes": int(first["payload_bytes"]),
        "streams": int(first["streams"]),
        "outstanding_per_stream": outstanding,
        "configured_total_outstanding": configured,
        "max_outstanding_per_stream_observed": max(
            int(record.get("max_outstanding_per_stream_observed", outstanding)) for record in records
        ),
        "repeat_count": len(records),
        "valid": valid,
        "median_gbps": median(lambda record: float(record["aggregate_application_gbps"])),
        "throughput_cv": cv,
        "median_operations_per_second": median(lambda record: float(record["operations_per_second"])),
        "median_effective_cores": median(
            lambda record: float(record["resources"]["total_cpu_ns"]) / float(record["measured_ns"])
        ),
        "median_cpu_ns_per_operation": median(
            lambda record: float(record["resources"]["cpu_ns_per_completed_operation"])
        ),
        "median_p50_latency_ns": median(lambda record: float(record["p50_latency_ns"])),
        "median_p95_latency_ns": median(lambda record: float(record["p95_latency_ns"])),
        "median_p99_latency_ns": median(lambda record: float(record["p99_latency_ns"])),
        "errors": sum(int(record.get("errors", 0)) for record in records),
        "timeouts": sum(int(record.get("timeouts", 0)) for record in records),
        **roles,
    }


def stable_ceiling(summaries: list[dict], *, payload_bytes: int) -> dict:
    candidates = [
        summary
        for summary in summaries
        if summary["path"] == "nbsr"
        and summary["payload_bytes"] == payload_bytes
        and summary["valid"]
        and summary["repeat_count"] >= 3
        and summary["throughput_cv"] <= 0.05
    ]
    if not candidates:
        raise ValueError(f"no stable NBSR ceiling candidate for payload {payload_bytes}")
    return max(candidates, key=lambda summary: summary["median_gbps"])


def load_summaries(root: Path) -> list[dict]:
    grouped: dict[tuple, list[dict]] = {}
    for path in root.rglob("*-a*-s*-r*.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        key = (
            record["path"],
            int(record["payload_bytes"]),
            int(record["streams"]),
            int(record.get("outstanding_per_stream", 1)),
        )
        grouped.setdefault(key, []).append(record)
    return [summarize_cell(records) for _, records in sorted(grouped.items())]


def _write_checksums(root: Path) -> None:
    lines = []
    for path in sorted(item for item in root.rglob("*") if item.is_file() and item.name != "checksums.sha256"):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(root).as_posix()}")
    (root / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--historical-root", type=Path, action="append", default=[])
    args = parser.parse_args()
    authoritative = load_summaries(args.evidence_root / "authoritative")
    historical = []
    for root in args.historical_root:
        historical.extend(load_summaries(root))
    ceilings = {str(payload): stable_ceiling(authoritative, payload_bytes=payload) for payload in (1024, 16384)}
    comparisons = []
    for payload, streams in ((1024, 64), (16384, 8)):
        for path in ("direct", "nbsr"):
            before = next(
                (
                    item
                    for item in historical
                    if item["payload_bytes"] == payload
                    and item["streams"] == streams
                    and item["path"] == path
                    and item["outstanding_per_stream"] == 1
                ),
                None,
            )
            after = next(
                item
                for item in authoritative
                if item["payload_bytes"] == payload
                and item["streams"] == streams
                and item["path"] == path
                and item["outstanding_per_stream"] == 1
            )
            if before is not None:
                comparisons.append(
                    {
                        "payload_bytes": payload,
                        "streams": streams,
                        "path": path,
                        "before": before,
                        "after": after,
                        "throughput_delta_fraction": after["median_gbps"] / before["median_gbps"] - 1.0,
                        "cpu_ns_per_operation_delta_fraction": after["median_cpu_ns_per_operation"]
                        / before["median_cpu_ns_per_operation"]
                        - 1.0,
                    }
                )
    analysis = {
        "schema": "nbsr-b2-v2-harness-optimization-analysis-v1",
        "classification": {"evidence": "PASS", "system": "HARNESS-LIMITED:single-thread-benchmark-runtimes"},
        "claim_boundary": "Benchmark interference was removed; this is not a production NBSR speedup claim.",
        "baseline_transition": {
            "historical": "full SHA-256 on every timed operation",
            "current": "full SHA-256 pre/postflight plus every 1024th timed operation; eight bounded probes otherwise",
        },
        "ceilings": ceilings,
        "authoritative_cells": authoritative,
        "historical_comparisons": comparisons,
        "next_bottleneck_evidence": {
            "configuration": "All three benchmark binaries use Tokio current_thread runtimes.",
            "observation": "At stable peaks, each source/destination role consumes approximately 0.9 effective core despite mask 0x55.",
        },
    }
    (args.evidence_root / "analysis.json").write_text(
        json.dumps(analysis, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    lines = [
        "# B2-v2 Harness Optimization",
        "",
        "Classification: **Evidence PASS / HARNESS-LIMITED: single-thread benchmark runtimes**",
        "",
        "The per-operation benchmark SHA-256 interference was removed without changing production NBSR. "
        "Full integrity checks run before and after timing and every 1024th timed operation; other operations use eight bounded probes.",
        "",
        "| Payload | Stable NBSR Gbit/s | Streams | Outstanding/stream | CV | p99 ms | Effective cores |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for payload in (1024, 16384):
        cell = ceilings[str(payload)]
        lines.append(
            f"| {payload} | {cell['median_gbps']:.3f} | {cell['streams']} | {cell['outstanding_per_stream']} | "
            f"{cell['throughput_cv']:.3f} | {cell['median_p99_latency_ns']/1e6:.3f} | {cell['median_effective_cores']:.3f} |"
        )
    lines += [
        "",
        "This result demonstrates removal of benchmark interference only. It does not establish a production speedup or a host hardware ceiling.",
        "",
    ]
    (args.evidence_root / "summary.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    _write_checksums(args.evidence_root)


if __name__ == "__main__":
    main()
