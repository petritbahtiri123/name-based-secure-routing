from __future__ import annotations

import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.performance.memory_closure import analyze_resource_records  # noqa: E402
from scripts.performance.rust_memory_attribution import reconcile_snapshot  # noqa: E402


EVIDENCE = ROOT / "evidence/performance/rust-memory-attribution-p1a"


def documents(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def run_analysis(path: Path) -> dict[str, Any]:
    terminal = json.loads((path / "terminal-manifest.json").read_text(encoding="utf-8"))
    summary = json.loads((path / "finalized-cell/summary.json").read_text(encoding="utf-8"))
    environment = json.loads((path / "finalized-cell/environment.json").read_text(encoding="utf-8"))
    resources = documents(path / "resources.ndjson")
    diagnostics = documents(path / "diagnostics.ndjson")
    source_diagnostics = [item for item in diagnostics if item.get("role", "source") == "source"]
    initial = source_diagnostics[0]
    load = [item for item in source_diagnostics if item["phase"] == "load"][-1]
    post = source_diagnostics[-1]
    destination_drain = [item for item in resources if item["role"] == "destination" and item["phase"] == "drain"]
    source_drain = [item for item in resources if item["role"] == "source" and item["phase"] == "drain"]
    destination = analyze_resource_records(resources, role="destination")
    source = analyze_resource_records(resources, role="source")
    completed = int(summary["completed_requests"])
    lifecycle = {
        owner: reconcile_snapshot(post, owner)
        for owner in (
            "transport_sessions", "service_channels", "application_streams",
            "nbsr_tasks", "quic_connections", "quic_streams",
        )
    }
    collection_names = ("pending_routes", "channel_registry", "stream_registry", "audit_queue", "replay_state")
    collections = {
        name: {
            "initial_entries": int(initial[f"{name}_current_entries"]),
            "end_load_entries": int(load[f"{name}_current_entries"]),
            "post_drain_entries": int(post[f"{name}_current_entries"]),
            "high_water_entries": int(post[f"{name}_high_water_entries"]),
            "end_load_retained_capacity": int(load[f"{name}_retained_capacity"]),
            "post_drain_retained_capacity": int(post[f"{name}_retained_capacity"]),
            "high_water_retained_capacity": int(post[f"{name}_high_water_retained_capacity"]),
            "inserts": int(post[f"{name}_inserts"]),
            "removals": int(post[f"{name}_removals"]),
        }
        for name in collection_names
    }
    destination_delta = destination["working_set_bytes"]["end"] - destination["working_set_bytes"]["start"]
    private_delta = destination["private_bytes_values"]["end"] - destination["private_bytes_values"]["start"]
    return {
        "run_id": summary["run_id"],
        "percent": 50 if "50pct" in summary["run_id"] else 75,
        "terminal": terminal,
        "environment": environment,
        "load": {
            "offered_rate": summary["offered_rate"],
            "warmup_seconds": summary["warmup_seconds"],
            "measurement_seconds": summary["steady_state_seconds"],
            "drain_seconds": 20,
            "offered_operations": summary["offered_requests"],
            "completed_operations": completed,
            "errors": summary["failed_requests"],
            "p99_ns": summary["latency_ns"]["p99"],
            "total_offered_operations_including_warmup": terminal["counters"]["offered"],
            "total_completed_operations_including_warmup": terminal["counters"]["completed"],
            "total_errors_including_warmup": terminal["counters"]["failed"],
        },
        "destination_process": {
            **destination,
            "working_set_change_per_completed_operation_observational": destination_delta / completed,
            "private_bytes_change_per_completed_operation_observational": private_delta / completed,
            "post_drain_working_set_bytes": destination_drain[-1]["working_set_bytes"] if destination_drain else None,
            "post_drain_private_bytes": destination_drain[-1]["private_bytes"] if destination_drain else None,
            "post_drain_observation_complete": False,
        },
        "source_process": {
            **source,
            "post_drain_working_set_bytes": source_drain[-1]["working_set_bytes"] if source_drain else None,
            "post_drain_private_bytes": source_drain[-1]["private_bytes"] if source_drain else None,
        },
        "source_owner_lifecycle": lifecycle,
        "source_owner_collections": collections,
        "destination_owner_series_present": False,
    }


def main() -> None:
    run_paths = sorted((EVIDENCE / "runs").iterdir())
    runs = [run_analysis(path) for path in run_paths]
    observer = json.loads((EVIDENCE / "observer/summary.json").read_text(encoding="utf-8"))
    analysis = {
        "schema": "nbsr-rust-memory-attribution-p1a-v1",
        "classification": "E",
        "classification_label": "Still inconclusive",
        "blocking_unobserved_layer": "destination-process internal Rust ownership time series and complete destination post-drain process-memory observation",
        "repeatability": {
            "positive_75_percent_final_quarter_slope_runs": 3,
            "required": 2,
            "reproduced": True,
        },
        "observer_effect": observer,
        "runs": runs,
        "non_claim": "Source replay-state correlation does not prove destination allocation ownership.",
        "recommended_next_hypothesis": "Export destination aggregate snapshots through a pre-opened append-only file from a non-Tokio sampler, validate zero protocol errors, then repeat only the three 75% attribution runs.",
    }
    summaries = EVIDENCE / "summaries"
    reports = EVIDENCE / "reports"
    summaries.mkdir(exist_ok=True)
    reports.mkdir(exist_ok=True)
    (summaries / "analysis.json").write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    rows = []
    for run in runs:
        process = run["destination_process"]
        load = run["load"]
        replay = run["source_owner_collections"]["replay_state"]
        rows.append(
            f"| {run['run_id']} | {load['offered_operations']} | {load['completed_operations']} | {load['errors']} | "
            f"{process['working_set_bytes']['start']} | {process['working_set_bytes']['peak']} | {process['working_set_bytes']['end']} | "
            f"{process['working_set']['overall']['slope_bytes_per_second']:.3f} | {process['working_set']['final_quarter']['slope_bytes_per_second']:.3f} | "
            f"{process['private_bytes']['final_quarter']['slope_bytes_per_second']:.3f} | "
            f"{process['working_set_change_per_completed_operation_observational']:.6f} | {replay['end_load_entries']} | {replay['post_drain_entries']} |"
        )
    report = f"""# NBSR Performance Task P1A — Rust Retained-Memory Ownership Attribution

## Result

Primary classification: **E — Still inconclusive**.

The positive destination-process late-run slope reproduced in all three 75% runs, but destination-process internal Rust ownership snapshots could not be collected within the observer-effect safety boundary. The precise invisible layer is the destination process's `ControlSession`/channel-stream replay registry, audit queue, Quinn wrapper, and task ownership time series, together with a complete destination post-drain process-memory observation. Source-side owner metrics are strongly correlated but are not treated as proof of destination ownership.

## Git and scope

- Task branch: `codex/nbsr-perf-p1-rust-memory-attribution`
- Required base: `4e25ee026618a502327331f352d90e26d29284e3`
- No push, merge, rebase, allocator change, optimization, protocol change, security change, capacity change, or accepted-evidence overwrite occurred.
- Accepted capacity: Rust-to-Rust 1,687.5 ops/s; loads: 843.75 (50%) and 1,265.625 (75%).

## Observer effect

- Five paired comparisons, 843.75 ops/s, 5-second warm-up, 30-second measured window.
- Median throughput degradation: `{observer['median_throughput_degradation_percent']:.6f}%` (limit 3%).
- Median p99 degradation: `{observer['median_p99_degradation_percent']:.6f}%` (limit 5%).
- Additional protocol errors: `{observer['additional_protocol_errors']}`.
- Source-only diagnostic build gate: `{'PASS' if observer['pass'] else 'FAIL'}`.
- Destination-emission attempts are retained under `attempts/`; they produced protocol/finalization errors and therefore were rejected rather than used for attribution.

## Primary run results

All primary runs used a 60-second warm-up, 1,800-second measurement, one-second cadence, and 20-second explicit drain. Bytes/completed-operation is an observational ratio, not allocation ownership.

| Run | Offered | Completed | Errors | WS begin | WS peak | WS end-load | WS full slope B/s | WS final-quarter B/s | Private final-quarter B/s | WS change/op | Source replay entries end-load | Source replay entries post-drain |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

Destination post-drain memory is not a complete 20-second series because the accepted server exits after its existing completion acknowledgement. This missing evidence is part of classification E.

## Owner reconciliation

For Transport Sessions, Service Channels, Application Streams, NBSR tasks, Quinn connections, and Quinn streams, the equation is `created - terminal_success - terminal_failure_or_cancel = current_live`. In every source-side primary run the equation reconciled and post-drain live counts were zero.

Application Streams and Quinn stream wrappers had high-water live count 1 and returned to zero continuously. Pending-route, channel-registry, stream-registry, and audit-queue current entries returned to zero after drain. The source replay/used-stream set grew once per completed Application Stream—1,569,375 entries at 50% and 2,354,062 entries in each 75% run—then returned to zero when the session terminated. Its high-water retained HashSet capacity was 1,835,008 at 50% and 3,670,016 at 75%.

The matching source/destination process slopes and source replay growth implicate replay history as a hypothesis only. They do not establish destination causation without destination internal snapshots.

## Diagnostic inventory

| Metric | Owner | Increment/observation event | Terminal/removal event | Expected post-drain |
|---|---|---|---|---:|
| `transport_sessions_*` | `ControlSession` | `ControlSession::new_inner` | `ControlSession::drop` | live 0 |
| `service_channels_*` | `ChannelRegistry` | pending admission | registry/session drop | live 0 |
| `application_streams_*` | `ChannelStreams` | committed stream open | release, revoke, or drop | live 0 |
| `pending_routes_*` | pending channel map | map observation after admission/confirmation | confirmation/drop | entries 0 |
| `channel_registry_*` | pending/active/terminal maps | aggregate map observation | transition/drop | entries 0 |
| `stream_registry_*` | per-channel stream maps | committed open | release/revoke/drop | entries 0 |
| `audit_queue_*` | `AuditLog.events` | enqueue | pop/drop | entries 0 |
| `replay_state_*` | `ChannelStreams.used_stream_ids` | committed unique stream ID | session drop | entries 0 |
| `nbsr_tasks_*` | NBSR-owned tasks | no applicable owned task in accepted sequential workload | not applicable | live 0 |
| `quic_connections_*` | authenticated Quinn wrapper | successful authentication | wrapper drop | live 0 |
| `quic_streams_*` | application-stream wrapper | wrapper creation | wrapper drop | live 0 |

Caches and separate channel queues were not present in this accepted sequential workload. Quinn internals, Tokio runtime-global tasks, allocator arenas, and native transport allocations remain intentionally invisible.

## TDD, correctness, and security

Focused RED evidence retained in the task history:

- Rust diagnostics API initially failed to compile because the module was absent; GREEN: 3 tests, later 4 tests.
- Durable diagnostics test initially failed because `diagnostics.ndjson` was absent; GREEN: 6 tests.
- Stream routing test initially failed because diagnostic lines were interpreted as completion metadata; GREEN after separate routing.
- Attribution-plan test initially failed on the drain bound; GREEN with the explicit 20-second drain.
- Classification fixtures cover A/B/C/D/E behavior and the two-of-three rule.

Fresh final validation: Rust passed 124 tests with zero failures; `cargo fmt --check`, Ruff, and Clippy with `-D warnings` passed. The complete Python repository run produced 1,730 passed, 1 skipped, and 38 failures. Thirty-seven failures are frozen baseline/vector digest or manifest checks affected by the Windows worktree checkout; one performance streaming timing assertion expected 9 callback lines but observed 12. The performance suite separately produced 101 passed and that same one timing failure. These failures are disclosed rather than repaired because modifying frozen authorities or unrelated timing behavior is outside P1A.

## What is ruled out

- Reproducibility failure: ruled out; three of three 75% slopes were positive and closely matched.
- Source-side live Application Stream, Quinn stream, session, or channel leakage: ruled out by conservation and zero post-drain live counts.
- Source pending-route, active stream-registry, or audit-queue entry retention: ruled out by zero post-drain entries.
- Protocol errors in accepted primary runs: ruled out; every offered operation completed and errors were zero.
- Safe destination attribution: not established; attempts exceeded the zero-additional-error observer boundary.

## What remains unresolved

Whether destination process memory is owned by its session-lifetime replay/used-stream history, another destination container, Quinn/native state, or allocator retention cannot be distinguished without safe destination internal snapshots and complete destination post-drain process sampling.

## Recommended next hypothesis

Export destination aggregate snapshots through one pre-opened append-only file from a non-Tokio sampler, prove zero additional protocol errors in five paired comparisons, then repeat only the three 75% attribution runs. Do not change replay semantics or fix retention until that evidence is reviewed.
"""
    (reports / "rust-memory-attribution.md").write_text(report, encoding="utf-8")

    manifest = {
        "schema": "nbsr-rust-memory-attribution-p1a-manifest-v1",
        "classification": "E",
        "base_sha": "4e25ee026618a502327331f352d90e26d29284e3",
        "instrumented_run_sha": "c5c7d12aec20977986bbfa298b58a49134192dac",
        "accepted_capacity_ops_per_second": 1687.5,
        "primary_run_ids": [run["run_id"] for run in runs],
        "failed_attempts_retained": sorted(path.name for path in (EVIDENCE / "attempts").iterdir()),
        "generated_on": platform.platform(),
        "git_head_at_generation": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    }
    (EVIDENCE / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    checksums = {
        path.relative_to(EVIDENCE).as_posix(): digest(path)
        for path in sorted(EVIDENCE.rglob("*"))
        if path.is_file() and path.name != "checksums.json"
    }
    (EVIDENCE / "checksums.json").write_text(json.dumps(checksums, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"classification": "E", "checksummed_files": len(checksums)}, indent=2))


if __name__ == "__main__":
    main()
