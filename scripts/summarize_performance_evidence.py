from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.performance.statistics import summarize  # noqa: E402


def read_raw(path: Path) -> list[dict[str, Any]]:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            records = [json.loads(line) for line in handle]
    else:
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    ids = [record["sample_id"] for record in records]
    if len(ids) != len(set(ids)) or ids != list(range(len(ids))):
        raise ValueError(f"invalid sample sequence in {path}")
    if any(not record["success"] for record in records):
        raise ValueError(f"failed request retained in {path}; formal headline is not complete")
    return records


def ms(value: int | None) -> str:
    return "INCONCLUSIVE" if value is None else f"{value / 1_000_000:.3f} ms"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    root = args.evidence.resolve()
    raw_paths = sorted((root / "raw").glob("*.ndjson*"))
    if not raw_paths:
        raise SystemExit("no raw evidence")
    summaries: dict[str, Any] = {}
    for path in raw_paths:
        records = read_raw(path)
        run_id = records[0]["run_id"]
        summaries[run_id] = {
            "request_latency_ns": summarize([record["request_latency_ns"] for record in records]),
            "total_scenario_ns": summarize([record["total_scenario_ns"] for record in records]),
            "success": len(records),
            "failure": 0,
        }
    direct = summaries["direct-quic-warm-existing-1024-idle"]["request_latency_ns"]
    overhead: dict[str, dict[str, int]] = {}
    for implementation in ("rust-rust", "go-rust"):
        observed = summaries[f"{implementation}-warm-existing-1024-idle"]["request_latency_ns"]
        overhead[implementation] = {name: observed[name] - direct[name] for name in ("p50", "p95", "p99")}
    budgets = {
        implementation: {
            "p50": "PASS" if values["p50"] <= 5_000_000 else "FAIL",
            "p95": "PASS" if values["p95"] <= 10_000_000 else "FAIL",
            "p99": "PASS" if values["p99"] <= 20_000_000 else "FAIL",
        }
        for implementation, values in overhead.items()
    }
    summary = {
        "schema": "nbsr-performance-summary-v1",
        "runs": summaries,
        "matched_warm_existing_overhead_ns": overhead,
        "budgets": budgets,
    }
    (root / "summaries").mkdir(exist_ok=True)
    (root / "summaries/latency.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    environment = json.loads((root / "environment.json").read_text(encoding="utf-8"))
    report = f"""# NBSR Latency and Performance Validation

## Environment

Repository `{environment["repository_sha"]}` on `{environment["os"]}`; {environment["cpu"]}, {environment["cores"]} cores/{environment["logical_processors"]} logical processors, {environment["memory_bytes"]} bytes RAM. Power plan: `{environment["power_plan"]}`. Rust `{environment["rustc"]}`; Go `{environment["go"]}`; Python `{environment["python"]}`. Release builds, Windows loopback, inherited affinity.

## Methodology

This initial unoptimized headline cell used 1 KiB payloads and an existing accepted Service Channel. Direct QUIC used equivalent QUIC v1/TLS 1.3 mTLS and echo behavior without NBSR control. Rust-Rust and Go-Rust used the real frozen Federation/F75/channel/stream gates. Per-process monotonic durations were never subtracted across processes.

## Integrity controls

0-RTT remained disabled. Peer observations were buffered until after measurement. Failed samples remain schema fields; this formal cell contains zero failures. Matched cells share repository, environment digest, topology, build profile, payload, load, lifecycle, and run ordinal.

## Direct QUIC results

Warm request latency: p50 {ms(direct["p50"])}, p95 {ms(direct["p95"])}, p99 {ms(direct["p99"])}, p99.9 {ms(direct["p99_9"])}; count {direct["count"]}.

## Rust -> Rust NBSR results

Warm-existing request latency: p50 {ms(summaries["rust-rust-warm-existing-1024-idle"]["request_latency_ns"]["p50"])}, p95 {ms(summaries["rust-rust-warm-existing-1024-idle"]["request_latency_ns"]["p95"])}, p99 {ms(summaries["rust-rust-warm-existing-1024-idle"]["request_latency_ns"]["p99"])}.

## Go -> Rust results

Warm-existing request latency: p50 {ms(summaries["go-rust-warm-existing-1024-idle"]["request_latency_ns"]["p50"])}, p95 {ms(summaries["go-rust-warm-existing-1024-idle"]["request_latency_ns"]["p95"])}, p99 {ms(summaries["go-rust-warm-existing-1024-idle"]["request_latency_ns"]["p99"])}.

## Multi-service reuse

INCONCLUSIVE in this baseline tranche. The real peers prove repeated streams on one accepted channel; the required 20 distinct signed service authorities were not executed.

## Stream scaling

Sequential stream reuse is measured by the headline cell. Concurrent stream scaling is INCONCLUSIVE.

## Capacity

INCONCLUSIVE. Open-loop capacity discovery and 25/50/75/90% load cells were not executed.

## Resource consumption

INCONCLUSIVE. Native Windows resource-sampling primitives are validated, but formal resource time series were not captured for this headline tranche.

## NBSR incremental overhead

Rust-Rust minus direct: p50 {ms(overhead["rust-rust"]["p50"])}, p95 {ms(overhead["rust-rust"]["p95"])}, p99 {ms(overhead["rust-rust"]["p99"])}.

Go-Rust minus direct: p50 {ms(overhead["go-rust"]["p50"])}, p95 {ms(overhead["go-rust"]["p95"])}, p99 {ms(overhead["go-rust"]["p99"])}.

## Budget evaluation

| Implementation | p50 +5 ms | p95 +10 ms | p99 +20 ms |
|---|---:|---:|---:|
| Rust-Rust | {budgets["rust-rust"]["p50"]} | {budgets["rust-rust"]["p95"]} | {budgets["rust-rust"]["p99"]} |
| Go-Rust | {budgets["go-rust"]["p50"]} | {budgets["go-rust"]["p95"]} | {budgets["go-rust"]["p99"]} |

Cold, warm-new-service, throughput, capacity, error-rate-under-load, and memory-growth budgets are INCONCLUSIVE.

## Known limitations

Loopback only; no same-region or cross-region claim. This tranche covers the full primary warm-existing headline cell only. It does not establish cold, warm-new-service, multi-service, concurrency, capacity, load, or resource conclusions. HTTP/3 is NOT SUPPORTED BY CURRENT TEST SURFACE.

## Raw evidence references

See `raw/*.ndjson.gz`, `summaries/latency.json`, and `checksums.json`.

## Candidate optimization opportunities — NOT IMPLEMENTED

None are implemented or recommended from this baseline alone.

## Conclusions

Only the matched warm-existing 1 KiB loopback results and their incremental overhead are supported. These results do not establish production readiness or Internet-scale performance.
"""
    (root / "reports").mkdir(exist_ok=True)
    (root / "reports/latency-and-performance-validation.md").write_text(report, encoding="utf-8")
    (root / "exclusions.json").write_text("[]\n", encoding="utf-8")
    inventory = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file() and item.name not in {"checksums.json", "manifest.json"}):
        inventory[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    (root / "checksums.json").write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "schema": "nbsr-performance-evidence-manifest-v1",
        "repository_sha": environment["repository_sha"],
        "environment_digest": hashlib.sha256(json.dumps(environment, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "files": sorted(inventory),
        "outcome": "PARTIAL_BASELINE",
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
